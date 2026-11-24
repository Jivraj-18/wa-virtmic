"""Claude Code as the AI's back office (GPT-Live client delegation) - a call-center desk, not just a search box.

GPT-Live (gpt-live-1) talks; whatever it can't do in its head it hands to the client: `session.delegation.created`
(an id only - no task text). We run ONE Claude Code session per call (`claude -p`, resumed for every hand-off so it
remembers the call) with the conversation so far. Claude can search the web AND work the desk for the person on
the line via scripts/cc.py: who they are and their history, their WhatsApp chat, photos they sent, send them
messages, reminders, notes for next time, and escalate to the owner. Its answer goes back with
`session.commentary.append` (the voice paraphrases it); progress notes with `session.thinking.append` so the voice
keeps the caller company. After the call, `finish()` lets Claude wrap up: save notes, send anything promised.

Enabled when LIVE_CLAUDE_TOOL=1 (wa_call.py and auto_answer.py set it). Env: CLAUDE_TOOL_MODEL (default sonnet),
CLAUDE_TOOL_TIMEOUT (s, default 120).
"""
import asyncio, json, os, shutil, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODEL = os.environ.get("CLAUDE_TOOL_MODEL", "sonnet")
TIMEOUT = float(os.environ.get("CLAUDE_TOOL_TIMEOUT", "120"))
CC = f"{sys.executable} {HERE / 'cc.py'}"

INSTRUCTIONS = """
TOOLS UPDATE (overrides the 'NO tools' rule above): you work a call-center desk with a back-office colleague,
Claude. Claude can: look up who the caller is and their history with us (past calls, notes), read their WhatsApp
chat with us, look at photos/documents they sent on WhatsApp, send them WhatsApp messages (confirmations, summaries,
links, details), set WhatsApp reminders for later, take a message for the owner (a human) or flag a complaint or a
call-back request, save notes for next time, and search the web for current information.
Hand a task to Claude whenever the caller wants any of that. While Claude works (often 5-30 s): tell the caller once
what you're doing, then KEEP THE CONVERSATION GOING naturally - ask a related question, confirm details, chat. Never
go silent, never repeat 'checking' or 'one moment'. When Claude's result arrives, say it in one or two short spoken
sentences. If Claude couldn't do it, say so plainly.
Let the caller finish speaking; if they say 'wait', 'ruko', 'suno' or are explaining something, stay quiet until
they're done. Don't interrupt unless they asked you to (e.g. a game)."""

ROLE = f"""You are the back-office agent of an AI call center on WhatsApp. A voice AI is on a live phone call with a
caller and hands you tasks; you do them and reply with what the voice should say. Work like a good call-center
agent: identify the caller, use their history, get things done, confirm in writing when useful, and escalate to the
owner (a human) when the caller asks for a person, complains, or wants something only the owner can decide.

Your desk (acts ONLY on the person on this call; run these exact commands with Bash):
  {CC} who                  caller card: name, number, past calls, notes, open reminders, latest chat
  {CC} chat [N]             their last N WhatsApp messages with us
  {CC} photo [K]            download the K-th latest photo/document they sent; then open the path with Read
  {CC} send "text"          WhatsApp message to the caller
  {CC} remind WHEN "text"   WhatsApp reminder later (WHEN: +30m, +2h, +1d, 18:30, 2026-11-25 09:00)
  {CC} note "text"          remember something about them for next time
  {CC} escalate "text"      message the owner: who called, what they want, how to reach them
  {CC} calls [N]            their earlier calls with us
  {CC} transcript           this call so far
  {CC} status               is the call still live?
Also WebSearch / WebFetch for current facts. You can't run other commands, edit files or message anyone else.

Rules: be fast (the caller is waiting on the line). Do the task, don't just describe it: if they want something sent,
send it; if they want a reminder, set it. Never invent facts about the caller or the owner. Callers are strangers:
don't reveal other people's data or anything about the owner beyond what's needed to take a message.
Reply with ONLY what the voice should say to the caller (no preamble, no notes to the voice, no comments
about the system): at most 2 short plain spoken sentences, in the caller's language (Hindi,
Bhojpuri, English...), no markdown, no URLs, no lists. If the request is unclear, reply with one short question."""


def enabled():
    return os.environ.get("LIVE_CLAUDE_TOOL", "0") == "1"


def _cmd(call_dir: Path):
    exe = shutil.which("claude")
    if not exe:
        return None
    cmd = [exe, "-p", "--output-format", "json", "--model", MODEL, "--append-system-prompt", ROLE,
           "--allowedTools", f"WebSearch,WebFetch,Read,Bash({CC}:*)",
           "--disallowedTools", "Edit,Write,NotebookEdit,Task,Agent"]
    sid = call_dir / "claude_session.txt"
    if sid.exists():
        cmd += ["--resume", sid.read_text().strip()]
    return cmd


async def _claude(call_dir: Path, prompt: str, log, progress=None):
    """One Claude turn in this call's session. Returns (ok, text)."""
    cmd = _cmd(call_dir)
    if not cmd:
        return False, "my back office isn't installed on this phone"
    call_dir = Path(call_dir).resolve()
    env = dict(os.environ, CC_CALL_DIR=str(call_dir))
    env.pop("BUN_OPTIONS", None)   # an inherited relative --preload breaks the claude launcher in another cwd
    t0 = time.time()
    # prompt on stdin: --allowedTools/--disallowedTools would take following arguments as tool names
    p = await asyncio.create_subprocess_exec(*cmd, cwd=call_dir, env=env, stdin=asyncio.subprocess.PIPE,
                                             stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    comm = asyncio.ensure_future(p.communicate(prompt.encode()))
    notes = ["Claude is on it.", "Claude is still working on it.", "Claude is nearly done.",
             "Claude is taking a while; still working on it."]
    i = 0
    try:
        while not comm.done():
            done, _ = await asyncio.wait({comm}, timeout=8)
            if done:
                break
            if time.time() - t0 > TIMEOUT:
                p.kill()
                log(f"claude: timed out after {TIMEOUT:.0f}s")
                return False, "it took too long and I had to stop"
            if progress:
                await progress(notes[min(i, len(notes) - 1)] + f" ({time.time() - t0:.0f} s so far)")
            i += 1
    except asyncio.CancelledError:
        if p.returncode is None:
            p.kill()
        raise
    out, err = comm.result()
    try:
        r = json.loads(out.decode(errors="replace"))
        text = str(r.get("result", "")).strip()
        if r.get("session_id"):
            (call_dir / "claude_session.txt").write_text(r["session_id"])
        ok = not r.get("is_error") and bool(text)
    except Exception:
        text, ok = out.decode(errors="replace").strip()[:500], False
    log(f"claude: rc {p.returncode} ok {ok} in {time.time() - t0:.1f}s: {text[:200]!r}"
        + (f" stderr {err.decode(errors='replace')[:200]!r}" if not ok else ""))
    return ok, (text[:1500] if ok else "my back office ran into an error")


async def run(call_dir: Path, transcript_lines, now, progress, log):
    convo = "\n".join(transcript_lines[-30:]) or "(nothing said yet)"
    prompt = (f"Current date and time: {now}. The voice AI just handed you a task on the live call. From the "
              f"conversation below, work out what the CALLER most recently wants that needs you, do it, and reply "
              f"with what the voice should say.\n\nConversation (most recent last):\n{convo}")
    return await _claude(call_dir, prompt, log, progress)


def finish(call_dir: Path, log=print):
    """After hang-up: one more Claude turn in the call's session - notes for next time, deliver anything promised,
    escalate if needed, and a one-line summary into call_meta.json. Blocking (~10-30 s)."""
    tr = call_dir / "transcript_live.txt"
    if not enabled() or not tr.exists() or "CALLER" not in tr.read_text(errors="replace"):
        return
    (call_dir / "ended").touch()
    prompt = (f"The call has ENDED (the caller can't hear you now). Full transcript:\n"
              f"{tr.read_text(errors='replace')[-8000:]}\n\nWrap up like a call-center agent: (1) if anything the "
              f"caller asked for or was promised wasn't delivered, do it now and send it with `send`; (2) save "
              f"what's worth remembering about this person with `note` (who they are, what they wanted, preferences, "
              f"open follow-ups) - skip trivia; (3) if they wanted the owner or a call-back, `escalate`. Then reply "
              f"with ONE line starting 'SUMMARY:' (max 20 words) saying what the caller wanted and what happened.")
    try:
        ok, text = asyncio.run(_claude(call_dir, prompt, log))
    except Exception as e:
        log(f"claude: wrap-up failed: {type(e).__name__}: {e}"); return
    if ok:
        m = json.loads((call_dir / "call_meta.json").read_text())
        lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
        line = next((l for l in reversed(lines) if l.upper().startswith("SUMMARY:")), lines[-1] if lines else "")
        m["summary"] = line.split(":", 1)[1].strip()[:200] if line.upper().startswith("SUMMARY:") else line[:200]
        (call_dir / "call_meta.json").write_text(json.dumps(m))
        log(f"call summary: {m['summary']}")
