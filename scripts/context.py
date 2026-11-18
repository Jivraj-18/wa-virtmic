"""E1: load a "call center" context folder and turn it into realtime-agent settings.

Context folder format (shared with E2 and E5; keep it stable):
  <context>/
    instructions.md   free text from the owner (availability, how to treat callers, ...)
    config.yaml       voice, language, max_call_seconds, greeting, owner_name, answer_only (optional caller-name filter)
    knowledge/        .md / .txt / .pdf about projects people call about (phase 1: stuffed into the instructions)
    media/            used by E5; ignored here

  ctx = load_context("callcenter")      # re-read it on every call: edits take effect on the next call
  print(build_instructions(ctx))
  agent = make_agent(ctx, transcript=..., in_device=..., out_device=...)   # realtime_agent.Agent
"""
import shutil, subprocess, time
from pathlib import Path

import yaml

DEFAULTS = {
    "owner_name": "the owner",
    "voice": "marin",              # OpenAI realtime voice
    "language": "English",         # default reply language
    "max_call_seconds": 600,
    "greeting": None,              # exact sentence to open with (None = a generic call-center greeting)
    "answer_only": [],             # caller names (substring, case-insensitive); empty = answer everyone
}
KNOWLEDGE_EXT = {".md", ".txt", ".pdf"}
MAX_KNOWLEDGE_CHARS = 24000        # total knowledge budget inside the session instructions (~6k tokens)
MAX_FILE_CHARS = 12000             # per file


def pdf_text(path: Path) -> str:
    """Text of a PDF: poppler's pdftotext if installed, else pypdf (pip), else a placeholder."""
    if shutil.which("pdftotext"):
        r = subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True, timeout=60)
        if r.returncode == 0:
            return r.stdout
    try:
        from pypdf import PdfReader
        return "\n".join(p.extract_text() or "" for p in PdfReader(str(path)).pages)
    except ImportError:
        return f"<could not read {path.name}: install poppler-utils (apt) or pypdf (pip)>"


def load_context(path) -> dict:
    """Read instructions.md, config.yaml and knowledge/ from a context folder. Missing pieces fall back to defaults."""
    root = Path(path).expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"context folder not found: {root}")
    cfg = dict(DEFAULTS)
    cfg_file = root / "config.yaml"
    if cfg_file.exists():
        cfg.update({k: v for k, v in (yaml.safe_load(cfg_file.read_text()) or {}).items() if v is not None})
    if isinstance(cfg.get("answer_only"), str):
        cfg["answer_only"] = [cfg["answer_only"]]
    ins = root / "instructions.md"
    knowledge, warnings = [], []
    kdir = root / "knowledge"
    if kdir.is_dir():
        for f in sorted(p for p in kdir.rglob("*") if p.is_file()):
            if f.suffix.lower() not in KNOWLEDGE_EXT:
                warnings.append(f"skipped {f.relative_to(root)} (only .md/.txt/.pdf)")
                continue
            try:
                text = pdf_text(f) if f.suffix.lower() == ".pdf" else f.read_text(errors="replace")
            except Exception as e:
                text, _ = "", warnings.append(f"could not read {f.relative_to(root)}: {e}")
            knowledge.append({"name": str(f.relative_to(kdir)), "text": text.strip()})
    if not ins.exists():
        warnings.append("instructions.md missing")
    return {"path": str(root), "instructions": ins.read_text().strip() if ins.exists() else "",
            "config": cfg, "knowledge": knowledge, "warnings": warnings, "loaded_at": time.time()}


def _knowledge_block(items) -> tuple[str, list]:
    out, used, notes = [], 0, []
    for k in items:
        t = k["text"]
        if len(t) > MAX_FILE_CHARS:
            t, _ = t[:MAX_FILE_CHARS] + "\n[...truncated]", notes.append(f"{k['name']} truncated to {MAX_FILE_CHARS} chars")
        if used + len(t) > MAX_KNOWLEDGE_CHARS:
            notes.append(f"{k['name']} left out (knowledge budget {MAX_KNOWLEDGE_CHARS} chars reached)")
            continue
        out.append(f"### {k['name']}\n{t}")
        used += len(t)
    return "\n\n".join(out), notes


def build_instructions(ctx: dict, caller: str | None = None) -> str:
    """Session instructions for gpt-realtime: persona + owner's instructions + config + knowledge (size-capped)."""
    c = ctx["config"]
    owner, lang = c["owner_name"], c["language"]
    know, notes = _knowledge_block(ctx["knowledge"])
    ctx.setdefault("warnings", []).extend(n for n in notes if n not in ctx["warnings"])
    now = time.strftime("%A %d %B %Y, %H:%M %Z")
    parts = [f"""You are the AI phone assistant of {owner}, answering {owner}'s WhatsApp voice calls like a small call center.
{owner} is not on this call. You speak for {owner} but you are not {owner}; if asked, say you are {owner}'s AI assistant.
Speak naturally and keep every reply short: one or two sentences, then let the caller talk.
Speak {lang}. Only switch language if the caller clearly speaks another language to you first.
Answer only from the owner's instructions and the knowledge notes below. If something is not covered, say you don't know
and offer to pass a message to {owner}. Never invent dates, prices, phone numbers or promises.
When a caller wants to leave a message, get their name, the message and how/when to reach them back, then read it back briefly.
Before the caller hangs up, briefly confirm what you will pass on to {owner}.
Current local date and time: {now}."""]
    if caller:
        parts.append(f"WhatsApp shows the caller as: {caller}.")
    parts.append(f"## Instructions from {owner}\n{ctx['instructions'] or '(none)'}")
    if know:
        parts.append(f"## Knowledge notes (facts you may share with callers)\n{know}")
    return "\n\n".join(parts)


def greeting_instruction(ctx: dict) -> str:
    c = ctx["config"]
    if c.get("greeting"):
        return f'Start the call by saying exactly this, in a warm voice: "{c["greeting"]}"'
    return (f"In {c['language']}, greet the caller in one short sentence: say you are {c['owner_name']}'s AI assistant "
            f"and ask how you can help.")


def agent_kwargs(ctx: dict, caller: str | None = None) -> dict:
    """kwargs for realtime_agent.Agent(...). Extension point: other experiments (E2) merge 'tools'/'on_tool'/
    'on_event'/'session_extra' into the dict this returns (they start empty)."""
    return {"instructions": build_instructions(ctx, caller), "greeting": greeting_instruction(ctx),
            "tools": [], "on_tool": None, "on_event": None, "session_extra": {}}


def make_agent(ctx: dict, caller: str | None = None, extra: dict | None = None, **agent_args):
    """Build a realtime_agent.Agent from a context. agent_args: transcript, log, in_device, out_device."""
    import realtime_agent
    # Agent reads the voice from the module global at run time; set it per call without touching realtime_agent.py.
    realtime_agent.VOICE = ctx["config"].get("voice") or realtime_agent.VOICE
    kw = agent_kwargs(ctx, caller)
    kw.update(extra or {})
    kw.update(agent_args)
    return realtime_agent.Agent(**kw)


def caller_allowed(ctx: dict, caller: str | None) -> bool:
    """answer_only filter: empty list = everyone; otherwise the caller name must contain one of the entries."""
    only = [str(x).lower() for x in ctx["config"].get("answer_only") or []]
    return not only or bool(caller and any(o in caller.lower() for o in only))


UI_WORDS = {"accept", "decline", "answer", "reject", "ignore", "incoming voice call", "incoming video call",
            "incoming call", "whatsapp voice call", "whatsapp video call", "voice call", "video call", "calling…",
            "calling...", "ringing", "whatsapp", "end-to-end encrypted"}


def caller_from_text(text: str | None) -> str | None:
    """Best guess at the caller's display name/number from the incoming-call popup's innerText."""
    for line in (text or "").splitlines():
        s = line.strip()
        if s and s.lower() not in UI_WORDS and len(s) < 60:
            return s
    return None
