"""Claude Code as GPT-Live's one tool (client delegation).

GPT-Live (gpt-live-1) hands work it can't do itself (look-ups, current facts, anything needing the web) to the client:
the server sends `session.delegation.created` with only an id - no task text. We build the task from the recent call
transcript, run headless Claude Code (`claude -p`, web search/fetch ONLY: callers are strangers, so no shell or file
tools), and return the answer with `session.commentary.append` (the voice model paraphrases it). While Claude works we
send `session.thinking.append` progress notes so the voice can keep the caller company instead of going silent.
Before this existed nothing answered the delegations, and the model said "Checking." for minutes (2026-11-23 calls).

Enabled when LIVE_CLAUDE_TOOL=1 (wa_call.py sets it for outgoing calls). Env: CLAUDE_TOOL_MODEL (default sonnet),
CLAUDE_TOOL_TIMEOUT (s, default 90).
"""
import asyncio, os, shutil, time
from pathlib import Path

MODEL = os.environ.get("CLAUDE_TOOL_MODEL", "sonnet")
TIMEOUT = float(os.environ.get("CLAUDE_TOOL_TIMEOUT", "90"))
WORKDIR = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "wa-virtmic" / "claude-tool"

INSTRUCTIONS = """
TOOLS UPDATE (overrides the 'NO tools' rule above): you have ONE helper: Claude, a research assistant that can search the web and read web pages (current time is below;
Claude can find news, facts, travel times, prices, explanations, etc.). When the caller asks for something you can't
answer reliably yourself, delegate it. While Claude works (often 10-40 s): tell the caller once that you're asking
Claude, then KEEP THE CONVERSATION GOING - chat naturally, ask the caller about themselves or the topic, share a
related thought, or mention the progress notes you receive. Never go silent and never repeat 'checking' or 'one
moment' over and over. When Claude's answer arrives, give it in one or two short spoken sentences.
If Claude fails, say so plainly."""


def enabled():
    return os.environ.get("LIVE_CLAUDE_TOOL", "0") == "1"


def _cmd():
    exe = shutil.which("claude")
    if not exe:
        return None
    return [exe, "-p", "--model", MODEL, "--allowedTools", "WebSearch WebFetch",
            "--disallowedTools", "Bash Edit Write NotebookEdit Task Agent"]


def _prompt(transcript_lines, now):
    convo = "\n".join(transcript_lines[-30:]) or "(no transcript yet)"
    return (f"You are the research helper for an AI voice assistant on a live WhatsApp phone call. Current date and "
            f"time: {now}. The voice assistant just handed you a task: work out from the conversation below what the "
            f"CALLER most recently asked for that needs looking up, and answer it. Use web search when it helps. "
            f"Reply with ONLY the answer, in at most 2 short plain sentences that sound natural when spoken aloud "
            f"(no markdown, no URLs, no lists). If it is unclear what they want, reply with one short clarifying "
            f"question.\n\nConversation (most recent last):\n{convo}")


async def run(transcript_lines, now, progress, log):
    """Ask Claude; calls `await progress(text)` every ~8 s while it works. Returns (ok, answer_text)."""
    cmd = _cmd()
    if not cmd:
        return False, "my research helper isn't installed on this phone"
    WORKDIR.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.pop("BUN_OPTIONS", None)   # an inherited relative --preload breaks the claude launcher in another cwd
    t0 = time.time()
    # prompt on stdin: --allowedTools/--disallowedTools take every following argument as a tool name
    p = await asyncio.create_subprocess_exec(*cmd, cwd=WORKDIR, env=env, stdin=asyncio.subprocess.PIPE,
                                             stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    comm = asyncio.ensure_future(p.communicate(_prompt(transcript_lines, now).encode()))
    notes = ["Claude is searching the web for it.", "Claude is still reading sources.",
             "Claude is putting the answer together.", "Claude is taking a while; still working on it."]
    i = 0
    while not comm.done():
        done, _ = await asyncio.wait({comm}, timeout=8)
        if done:
            break
        if time.time() - t0 > TIMEOUT:
            p.kill()
            log(f"claude: timed out after {TIMEOUT:.0f}s")
            return False, "the lookup took too long and I had to stop it"
        await progress(notes[min(i, len(notes) - 1)] + f" ({time.time() - t0:.0f} s so far)")
        i += 1
    out, err = comm.result()
    text = out.decode(errors="replace").strip()
    log(f"claude: rc {p.returncode} in {time.time() - t0:.1f}s: {text[:200]!r}"
        + (f" stderr {err.decode(errors='replace')[:200]!r}" if p.returncode else ""))
    if p.returncode != 0 or not text:
        return False, "my research helper ran into an error"
    return True, text[:1500]
