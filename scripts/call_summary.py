#!/usr/bin/env python3
"""E1: write <call folder>/summary.md for the owner after a call (LLM chat completion via the gateway).

  python3 scripts/call_summary.py <call or sim-run folder> [--context callcenter] [--caller "Name"]

Works on real call folders from auto_answer.py (transcript.txt / transcript_live.txt) and on sim_call.py run
folders (transcript.txt / agent_transcript.txt).
"""
import argparse, json, sys, time, urllib.error, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gateway  # noqa: E402

MODEL = gateway.CHAT_MODEL
TRANSCRIPTS = ("transcript.txt", "transcript_live.txt", "agent_transcript.txt")

PROMPT = """You write short after-call notes for {owner}, whose AI assistant just answered a WhatsApp call for them.
Use only what is in the transcript. Write Markdown with exactly these sections:

## Caller
Name/number (WhatsApp shows: {caller}; prefer a name the caller gave). One line.
## What they wanted
1-3 bullets.
## What the AI told them / promised
Bullets of facts given and any promise made on {owner}'s behalf (e.g. "Alex will call back after 6 pm").
## Follow-ups for {owner}
Checkbox list (- [ ] ...) of concrete actions, with any message, phone number or deadline the caller left. "None" if nothing.
## Issues
Anything the AI got wrong, could not answer, or misheard. "None" if nothing."""


def chat(messages, model=MODEL, retries=5) -> str:
    body = json.dumps(gateway.adapt_chat({"model": model, "messages": messages, "temperature": 0.2})).encode()
    for i in range(retries):
        req = urllib.request.Request(gateway.base() + "/openai/v1/chat/completions", data=body,
                                     headers={**gateway.auth_header(), "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.load(r)["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and i < retries - 1:
                time.sleep(2 ** i * 2)
                continue
            raise


def read_transcript(d: Path) -> tuple[str, str]:
    for name in TRANSCRIPTS:
        f = d / name
        if f.exists() and f.read_text().strip():
            return name, f.read_text()
    raise FileNotFoundError(f"no transcript in {d}")


def summarize(folder, ctx: dict | None = None, caller: str | None = None, model=MODEL) -> Path:
    """Summarize the call in `folder` into folder/summary.md and return its path."""
    d = Path(folder)
    src, text = read_transcript(d)
    owner = (ctx or {}).get("config", {}).get("owner_name", "the owner")
    meta = {}
    if (d / "call_meta.json").exists():
        meta = json.loads((d / "call_meta.json").read_text())
    caller = caller or meta.get("caller") or "unknown"
    md = chat([{"role": "system", "content": PROMPT.format(owner=owner, caller=caller)},
               {"role": "user", "content": f"Transcript ({src}; AGENT/AI = the assistant):\n\n{text[:30000]}"}], model)
    out = d / "summary.md"
    out.write_text(f"# Call summary: {d.name}\n\n_WhatsApp caller: {caller} · transcript: {src} · "
                   f"generated {time.strftime('%Y-%m-%d %H:%M')} by {model}_\n\n{md.strip()}\n")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--context")
    ap.add_argument("--caller")
    ap.add_argument("--model", default=MODEL)
    a = ap.parse_args()
    ctx = None
    if a.context:
        from context import load_context
        ctx = load_context(a.context)
    out = summarize(a.folder, ctx, a.caller, a.model)
    print(out.read_text())
    print(out)


if __name__ == "__main__":
    main()
