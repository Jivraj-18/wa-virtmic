#!/usr/bin/env python3
"""E2 "Hold on, let me check": tools the realtime voice agent can call mid-call, over a context folder.

Context folder format (shared with E1's call center):
  <context>/instructions.md  config.yaml  knowledge/ (.md/.txt/.pdf)  media/ (ignored here)

Tools
  search_knowledge(query)  ripgrep over the context folder (PDFs via pdftotext), simple term-weighted ranking,
                           returns the top snippets with file path + line (+ PDF page).
  read_file(path)          read one file inside the context folder (size-capped, PDFs as text).
  ask_agent(question)      slow background research agent: `claude -p` headless, cwd = context folder,
                           read-only tools (Read, Grep, Glob), timeout ~90 s.

Keeping the caller engaged: when a slow tool starts (ask_agent, or any tool still running after 1.5 s) the agent
speaks a short holding line, repeats a "still checking" line every ~15 s, and speaks the answer when it arrives.
Every tool call and result is logged as JSON lines to <log_dir>/tool_calls.jsonl, and response/audio timing
events to <log_dir>/e2_events.jsonl (see experiments/E2/tools/analyze_run.py).

Integration (E1 call center):
  import tools
  kw = tools.agent_kwargs(context_dir, call_dir)       # {"tools", "on_tool", "on_event", "instructions_suffix"}
  Agent(..., instructions=base + kw.pop("instructions_suffix"), **kw)
  # with other tools (e.g. E1's end_call): tools=kw["tools"] + [END_CALL_TOOL],
  #   on_tool=tools.chain_on_tool(kw["on_tool"], end_call_handler), on_event=tools.chain_on_event(kw["on_event"], other)

CLI
  python3 scripts/tools.py search "firmware freeze" --context experiments/E2/context
  python3 scripts/tools.py read knowledge/pricing_2027.md --context experiments/E2/context
  python3 scripts/tools.py ask "What is the total first-year cost of the pilot fleet?" --context experiments/E2/context
  python3 scripts/tools.py agent --context experiments/E2/context --in-device X.monitor --out-device Y --transcript t.txt
"""
import argparse, asyncio, json, math, os, re, shutil, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

TEXT_EXT = {".md", ".txt", ".yaml", ".yml", ".csv", ".json"}
READ_CAP = 12000            # chars returned by read_file
SNIPPET_LINES = 3           # context lines around a hit
ASK_TIMEOUT = float(os.environ.get("E2_ASK_TIMEOUT", 90))
ASK_MODEL = os.environ.get("E2_ASK_MODEL", "sonnet")
CLAUDE = os.environ.get("CLAUDE_BIN") or shutil.which("claude") or str(Path.home() / ".local/bin/claude")
SLOW_TOOLS = {"ask_agent"}
FILLER_AFTER = float(os.environ.get("E2_FILLER_AFTER", 1.5))  # seconds before a fast tool counts as slow
STILL_EVERY = float(os.environ.get("E2_STILL_EVERY", 15))  # seconds between "still checking" lines
STILL_MAX = 4

STOP = set("""a an and are as at be by can could did do does for from had has have how i if in into is it its
me my of on or our please should so tell that the their them then there these this to was we were what when where
which who whom why will with would you your about any much many know want need just like give get let also""".split())

FILLER = "Say exactly this one short sentence and nothing else: 'Give me a moment, I'm checking the documents.'"
STILL = ("Say exactly one short sentence and nothing else, telling the caller you are still checking and it will "
         "take a few more seconds, e.g. 'Still checking, thanks for waiting.' Do not answer anything yet.")


# ======================================================================= tools
class ContextTools:
    def __init__(self, context_dir, log_dir=None):
        self.root = Path(context_dir).resolve()
        if not self.root.is_dir():
            raise SystemExit(f"context folder not found: {self.root}")
        self.log_dir = Path(log_dir) if log_dir else None
        cache = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "wa-virtmic" / "pdftext"
        self.pdf_cache = cache / re.sub(r"[^A-Za-z0-9]+", "_", str(self.root)).strip("_")

    # ---- helpers --------------------------------------------------------
    def _files(self):
        for p in sorted(self.root.rglob("*")):
            rel = p.relative_to(self.root)
            if p.is_file() and rel.parts[0] != "media" and not any(x.startswith(".") for x in rel.parts):
                yield p, rel

    def _pdf_text(self, p: Path) -> Path:
        """pdftotext mirror of a PDF (cached by mtime). Pages are separated by form feeds."""
        out = self.pdf_cache / (str(p.relative_to(self.root)) + ".txt")
        if not out.exists() or out.stat().st_mtime < p.stat().st_mtime:
            out.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["pdftotext", "-layout", str(p), str(out)], check=True, capture_output=True, timeout=30)
        return out

    def _resolve(self, path: str) -> Path:
        cand = (self.root / path.lstrip("/")).resolve()
        if not cand.is_file():  # allow a bare file name
            hits = [p for p, rel in self._files() if p.name == Path(path).name]
            cand = hits[0].resolve() if hits else cand
        if self.root not in cand.parents:
            raise ValueError("path is outside the context folder")
        if not cand.is_file():
            raise FileNotFoundError(path)
        return cand

    @staticmethod
    def _terms(query: str):
        words = re.findall(r"[A-Za-z0-9][A-Za-z0-9.\-]*", query.lower())
        terms = []
        for w in words:
            w = w.strip(".-")
            if len(w) < 2 or w in STOP or (len(w) < 3 and not w.isdigit()):
                continue
            stem = w
            if w.isalpha():  # crude stemming, matched as a word prefix: warranties -> warrant, meetings -> meeting
                for suf in ("ies", "ing", "es", "ed", "s"):
                    if w.endswith(suf) and len(w) - len(suf) >= 4:
                        stem = w[: -len(suf)]
                        break
            if stem not in terms:
                terms.append(stem)
        return terms[:12]

    # ---- search_knowledge -------------------------------------------------
    def search_knowledge(self, query: str, max_results: int = 5) -> dict:
        terms = self._terms(query)
        if not terms:
            return {"query": query, "results": [], "note": "no usable keywords"}
        # text files are searched in place, PDFs through their pdftotext mirror
        targets, back = [], {}
        for p, rel in self._files():
            if p.suffix.lower() in TEXT_EXT:
                targets.append(str(p)); back[str(p)] = (str(rel), False)
            elif p.suffix.lower() == ".pdf":
                t = self._pdf_text(p); targets.append(str(t)); back[str(t)] = (str(rel), True)
        if not targets:
            return {"query": query, "results": []}
        cmd = ["rg", "--json", "-i", "-n", "--no-config"] + sum((["-e", r"\b" + re.escape(t)] for t in terms), []) + targets
        hits = {}  # file -> {line_no: set(terms)}
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=20).stdout
        for raw in out.splitlines():
            m = json.loads(raw)
            if m["type"] != "match":
                continue
            d = m["data"]
            f, ln, text = d["path"]["text"], d["line_number"], d["lines"].get("text", "").lower()
            found = {t for t in terms if re.search(r"\b" + re.escape(t), text)}
            hits.setdefault(f, {})[ln] = found
        # term weights: rarer terms count more (idf-like over matching lines)
        df = {t: sum(t in s for fl in hits.values() for s in fl.values()) for t in terms}
        w = {t: 1.0 / math.log(2 + df[t]) for t in terms}
        windows = []
        for f, lines in hits.items():
            for ln in lines:
                seen = set().union(*(lines.get(k, set()) for k in range(ln - SNIPPET_LINES, ln + SNIPPET_LINES + 1)))
                score = sum(w[t] for t in seen) + 0.5 * sum(w[t] for t in lines[ln])
                windows.append((score, f, ln))
        windows.sort(key=lambda x: -x[0])
        results, taken = [], []
        cache = {}
        for score, f, ln in windows:
            if any(f == f2 and abs(ln - l2) <= 2 * SNIPPET_LINES for f2, l2 in taken):
                continue
            taken.append((f, ln))
            if f not in cache:
                cache[f] = Path(f).read_text(errors="replace").split("\n")
            all_lines = cache[f]
            lo, hi = max(0, ln - 1 - SNIPPET_LINES), min(len(all_lines), ln + SNIPPET_LINES)
            rel, is_pdf = back.get(f, (f, False))
            r = {"file": rel, "line": ln, "score": round(score, 2),
                 "snippet": "\n".join(x.rstrip() for x in all_lines[lo:hi] if x.strip())[:900]}
            if is_pdf:
                r["page"] = "\n".join(all_lines[:ln]).count("\f") + 1
            results.append(r)
            if len(results) >= max_results:
                break
        return {"query": query, "terms": terms, "results": results}

    # ---- read_file ----------------------------------------------------------
    def read_file(self, path: str, start_line: int = 1) -> dict:
        p = self._resolve(path)
        text = self._pdf_text(p).read_text(errors="replace") if p.suffix.lower() == ".pdf" else p.read_text(errors="replace")
        lines = text.split("\n")
        start = max(1, int(start_line or 1))
        chunk, n = [], 0
        for i in range(start - 1, len(lines)):
            if n + len(lines[i]) + 1 > READ_CAP:
                break
            chunk.append(lines[i]); n += len(lines[i]) + 1
        end = start - 1 + len(chunk)
        r = {"file": str(p.relative_to(self.root)), "start_line": start, "end_line": end, "total_lines": len(lines),
             "content": "\n".join(chunk)}
        if end < len(lines):
            r["note"] = f"truncated; call read_file again with start_line={end + 1} for more"
        return r

    # ---- ask_agent ------------------------------------------------------------
    async def ask_agent(self, question: str, timeout: float = ASK_TIMEOUT) -> dict:
        prompt = ("You are the research assistant of a voice agent that is on a live phone call right now. "
                  "Answer the caller's question using ONLY the files in the current folder (instructions.md, "
                  "knowledge/ with .md, .txt and .pdf files). Look at every relevant file; later meeting notes override "
                  "earlier ones. Work fast. Reply with the answer only, in 1-3 short plain sentences that can be read "
                  "aloud (no markdown, no lists), with exact numbers, dates and any calculation result, and name the "
                  "files you used at the end in parentheses. If the files don't contain the answer, say so.\n\n"
                  f"Question: {question}")
        cmd = [CLAUDE, "-p", prompt, "--model", ASK_MODEL, "--allowedTools", "Read", "Grep", "Glob",
               "--disallowedTools", "Bash", "Edit", "Write", "NotebookEdit", "WebFetch", "WebSearch", "Task",
               "--no-session-persistence", "--output-format", "text"]
        t = time.time()
        proc = await asyncio.create_subprocess_exec(*cmd, cwd=str(self.root), stdin=asyncio.subprocess.DEVNULL,
                                                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                                                    start_new_session=True)
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout)
        except asyncio.CancelledError:
            proc.kill()
            raise
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return await self._ask_fallback(question, f"timed out after {timeout:.0f} s", t)
        ans = out.decode(errors="replace").strip()
        if proc.returncode != 0 or not ans:
            why = (err.decode(errors="replace") or ans)[-300:].strip()
            return await self._ask_fallback(question, f"failed (exit {proc.returncode}): {why}", t)
        return {"answer": ans, "seconds": round(time.time() - t, 1)}

    async def _ask_fallback(self, question, why, t):
        """The research assistant is down (timeout, usage limit, ...): hand back the best keyword-search snippets so
        the voice model can still try to combine them itself."""
        r = await asyncio.to_thread(self.search_knowledge, question, 6)
        return {"error": f"research assistant {why}", "seconds": round(time.time() - t, 1),
                "fallback": "Here are the most relevant document snippets instead. Combine them carefully; later "
                            "meeting notes override earlier ones. If they are not enough, offer a call back.",
                "snippets": r.get("results", [])}

    # ---- dispatch -------------------------------------------------------------
    async def call(self, name: str, args: dict):
        if name == "search_knowledge":
            return await asyncio.to_thread(self.search_knowledge, str(args.get("query", "")))
        if name == "read_file":
            return await asyncio.to_thread(self.read_file, str(args.get("path", "")), args.get("start_line") or 1)
        if name == "ask_agent":
            return await self.ask_agent(str(args.get("question", "")))
        return {"error": f"unknown tool {name}"}


TOOLS = [
    {"type": "function", "name": "search_knowledge",
     "description": "Fast keyword search over the project documents (specs, price lists, meeting notes, PDFs). "
                    "Returns the best matching snippets with file path and line. Use specific keywords.",
     "parameters": {"type": "object", "properties": {
         "query": {"type": "string", "description": "keywords, e.g. 'firmware freeze date' or 'Fleet plan price'"}},
         "required": ["query"]}},
    {"type": "function", "name": "read_file",
     "description": "Read a document from the project folder (path as returned by search_knowledge, e.g. "
                    "'knowledge/pricing_2027.md'). Long files are returned in chunks.",
     "parameters": {"type": "object", "properties": {
         "path": {"type": "string"}, "start_line": {"type": "integer", "description": "1-based line to start at"}},
         "required": ["path"]}},
    {"type": "function", "name": "ask_agent",
     "description": "Slow research assistant (takes 20-60 seconds) that reads ALL project documents and can combine "
                    "facts from several files and do arithmetic. Use it when the answer needs more than one document, "
                    "a calculation, or when search_knowledge did not give a clear answer. Pass the caller's full "
                    "question with every detail they mentioned.",
     "parameters": {"type": "object", "properties": {"question": {"type": "string"}}, "required": ["question"]}},
]

SUFFIX = """

## Looking things up
You can look things up in the project documents with tools. For ANY question about the project (dates, prices, numbers,
people, decisions, specifications), use a tool; never answer such questions from memory or guess.
- search_knowledge(query): fast keyword search, returns snippets with file paths. read_file(path) reads more of a file.
- ask_agent(question): a slower research assistant (20-60 s) for questions that combine several documents or need
  a calculation (totals, costs for N units, comparisons). Pass the caller's full question.
{preface}
When the result arrives, give the answer in one or two short sentences with the exact number or date. Mention which
document it came from only if asked. If the documents don't have it, say so and offer a call back."""
PREFACE_MODEL = "Before calling a tool, say one very short holding phrase (like 'Let me check that.') in the same turn."
PREFACE_NONE = ("Do NOT say anything before calling a tool: call it straight away, the system plays a holding "
                "line for you.")


# ======================================================================= realtime glue
class E2Session:
    """Tool handler + filler controller for one call (one realtime_agent.Agent)."""

    def __init__(self, context_dir, log_dir=None, log=print):
        self.ctx = ContextTools(context_dir, log_dir)
        self.log_dir = Path(log_dir) if log_dir else None
        if self.log_dir:
            self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log = log
        self.active = False                 # a realtime response is in progress
        self.idle = asyncio.Event()
        self.idle.set()
        self.cur = None                     # current response id
        self.resp = {}                      # id -> {kind, created, first_audio, audio_s, text}
        self.next_kind = []                 # labels for the next response.created events (filler/answer)
        self.turn_stopped = None            # wall time of the last caller speech_stopped
        self.turn_audio = False             # agent audio produced since that speech_stopped
        self.n = 0

    # ---- logging ------------------------------------------------------------
    def _jl(self, fname, rec):
        if self.log_dir:
            with open(self.log_dir / fname, "a") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def ev(self, event, **kw):
        self._jl("e2_events.jsonl", {"t": round(time.time(), 3), "ev": event, **kw})

    # ---- server events (Agent on_event) -------------------------------------
    def on_event(self, m, agent):
        ty = m.get("type")
        if ty == "response.created":
            rid = m.get("response", {}).get("id")
            kind = self.next_kind.pop(0) if self.next_kind else "auto"
            self.active, self.cur = True, rid
            self.idle.clear()
            self.resp[rid] = {"kind": kind, "created": time.time(), "first_audio": None, "audio_s": 0.0}
            self.ev("response_created", id=rid, kind=kind)
        elif ty in ("response.output_audio.delta", "response.audio.delta"):
            r = self.resp.get(m.get("response_id")) or self.resp.get(self.cur)
            if r is not None:
                if r["first_audio"] is None:
                    r["first_audio"] = time.time()
                    self.ev("first_audio", id=m.get("response_id"), kind=r["kind"])
                r["audio_s"] += len(m.get("delta", "")) * 3 / 4 / 2 / 24000
            self.turn_audio = True
        elif ty in ("response.output_audio_transcript.done", "response.audio_transcript.done"):
            self.ev("transcript", id=m.get("response_id"), text=m.get("transcript", ""))
        elif ty == "response.done":
            rid = m.get("response", {}).get("id")
            r = self.resp.get(rid, {})
            st = m.get("response", {}).get("status")
            self.ev("response_done", id=rid, kind=r.get("kind"), status=st, audio_s=round(r.get("audio_s", 0), 2))
            if rid == self.cur or rid is None:
                self.active = False
                self.idle.set()
        elif ty == "input_audio_buffer.speech_stopped":
            self.turn_stopped, self.turn_audio = time.time(), False
            self.ev("speech_stopped", audio_end_ms=m.get("audio_end_ms"))
        elif ty == "input_audio_buffer.speech_started":
            self.ev("speech_started")
        elif ty == "error":
            self.ev("error", error=m.get("error"))
            code = (m.get("error") or {}).get("code", "")
            if "active_response" in code and self.next_kind:
                self.next_kind.pop(0)  # our response.create was rejected: forget its label

    async def wait_idle(self, timeout=15.0):
        try:
            await asyncio.wait_for(self.idle.wait(), timeout)
        except asyncio.TimeoutError:
            pass

    async def speak(self, agent, instructions, kind):
        """Ask for a short spoken line without tools; waits until no response is active (API rule)."""
        await self.wait_idle()
        self.next_kind.append(kind)
        self.ev("speak_request", kind=kind)
        await agent.send({"type": "response.create",
                          "response": {"instructions": instructions, "tool_choice": "none"}})

    # ---- tool handler (Agent on_tool) -----------------------------------------
    async def on_tool(self, name, args, agent):
        """Returns None for tools this module doesn't own, so a dispatcher can chain handlers (see chain_on_tool)."""
        if name not in TOOL_NAMES:
            return None
        self.n += 1
        cid = self.n
        t0 = time.time()
        rec = {"call": cid, "tool": name, "args": args, "t_start": round(t0, 3),
               "t_caller_stopped": self.turn_stopped and round(self.turn_stopped, 3), "fillers": []}
        self.ev("tool_start", call=cid, tool=name)
        task = asyncio.create_task(self.ctx.call(name, args))

        async def keep_engaged():
            if name not in SLOW_TOOLS:
                await asyncio.sleep(FILLER_AFTER)
            await self.wait_idle()               # let the response that carried the function call finish
            if task.done():
                return
            if self.turn_audio:                  # the model already said "let me check" itself
                rec["fillers"].append({"source": "model"})
            else:
                rec["fillers"].append({"source": "forced", "t": round(time.time(), 3)})
                await self.speak(agent, FILLER, "filler")
            for _ in range(STILL_MAX):
                await asyncio.sleep(STILL_EVERY)
                if task.done():
                    return
                rec["fillers"].append({"source": "still", "t": round(time.time(), 3)})
                await self.speak(agent, STILL, "still")

        filler = asyncio.create_task(keep_engaged())
        try:
            result = await task
        except Exception as e:
            result = {"error": f"{type(e).__name__}: {e}"}
        filler.cancel()
        rec.update(t_end=round(time.time(), 3), seconds=round(time.time() - t0, 2),
                   ok="error" not in result, result=result)
        self.log(f"E2 tool {name} #{cid} {rec['seconds']}s ok={rec['ok']}")
        self._jl("tool_calls.jsonl", rec)
        self.ev("tool_end", call=cid, tool=name, seconds=rec["seconds"])
        # Agent sends the output and calls response.create right after we return: make sure nothing is active
        await self.wait_idle()
        self.next_kind.append(f"answer:{cid}")
        return result


TOOL_NAMES = {t["name"] for t in TOOLS}


def chain_on_tool(*handlers):
    """Combine several on_tool handlers: the first one returning non-None wins (e.g. E2 tools + E1's end_call)."""
    async def on_tool(name, args, agent):
        for h in handlers:
            if h is None:
                continue
            try:
                r = await h(name, args, agent)
            except KeyError:
                continue
            if r is not None:
                return r
        return {"error": f"unknown tool {name}"}
    return on_tool


def chain_on_event(*handlers):
    """Combine several on_event handlers (sync or async)."""
    async def on_event(m, agent):
        for h in handlers:
            if h is not None:
                r = h(m, agent)
                if asyncio.iscoroutine(r):
                    await r
    return on_event


def agent_kwargs(context_dir, log_dir=None, log=print, preface=True) -> dict:
    """Plug-in for realtime_agent.Agent: {"tools", "on_tool", "on_event", "instructions_suffix"}.
    on_tool returns None for names it doesn't own; combine with other tools via
    tools=kw["tools"] + other_tools, on_tool=chain_on_tool(kw["on_tool"], other_on_tool),
    on_event=chain_on_event(kw["on_event"], other_on_event). on_event is required for the filler logic."""
    s = E2Session(context_dir, log_dir, log)
    return {"tools": TOOLS, "on_tool": s.on_tool, "on_event": s.on_event,
            "instructions_suffix": SUFFIX.format(preface=PREFACE_MODEL if preface else PREFACE_NONE)}


def context_instructions(context_dir) -> tuple:
    """(instructions, greeting) from a context folder (minimal reader; E1's scripts/context.py is the full one)."""
    import yaml
    root = Path(context_dir)
    base = ("You are a friendly AI voice assistant answering a phone call. Keep every reply short: one or two "
            "sentences. Always speak English unless the caller clearly speaks another language first.\n\n")
    ins = (root / "instructions.md").read_text() if (root / "instructions.md").exists() else ""
    cfg = yaml.safe_load((root / "config.yaml").read_text()) if (root / "config.yaml").exists() else {}
    return base + ins, (cfg or {}).get("greeting")


# ======================================================================= CLI
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for c in ("search", "read", "ask"):
        p = sub.add_parser(c)
        p.add_argument("text")
        p.add_argument("--context", required=True)
    g = sub.add_parser("agent", help="realtime voice agent with E2 tools (use as sim_call.py --agent)")
    g.add_argument("--context", required=True)
    g.add_argument("--in-device", default="callout_sink.monitor")
    g.add_argument("--out-device", default="virtmic_sink")
    g.add_argument("--transcript")
    g.add_argument("--log-dir", help="default: folder of --transcript")
    g.add_argument("--seconds", type=float, default=300)
    g.add_argument("--no-preface", action="store_true",
                   help="tell the model not to speak before tool calls (always use the forced filler line)")
    a = ap.parse_args()

    if a.cmd != "agent":
        t = ContextTools(a.context)
        r = (t.search_knowledge(a.text) if a.cmd == "search" else t.read_file(a.text) if a.cmd == "read"
             else asyncio.run(t.ask_agent(a.text)))
        print(json.dumps(r, indent=1, ensure_ascii=False))
        return

    from realtime_agent import Agent
    log_dir = a.log_dir or (str(Path(a.transcript).parent) if a.transcript else None)
    ins, greeting = context_instructions(a.context)
    kw = agent_kwargs(a.context, log_dir, preface=not a.no_preface)
    ins += kw.pop("instructions_suffix")
    extra = {"greeting": greeting} if greeting else {}
    ag = Agent(Path(a.transcript) if a.transcript else None, instructions=ins, in_device=a.in_device,
               out_device=a.out_device, **extra, **kw)
    print(f"E2 agent: context={a.context} log_dir={log_dir} preface={not a.no_preface}", flush=True)
    try:
        asyncio.run(ag.run(a.seconds))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
