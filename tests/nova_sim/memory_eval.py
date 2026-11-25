"""Memory test for Nova's back office (the meeting desk), on REAL meeting records - no Meet, no voice.

    python tests/nova_sim/memory_eval.py [meeting_dir]     # cases + default meeting: NOVA_MEMORY_CASES json

For each case the two records (GPT-Live transcript + Meet captions) are cut at the moment the question was asked,
the question is appended as the newest line, and scripts/meet/live_meet.desk() answers it exactly as in a meeting.
Scored by expected / forbidden words. Uses Claude Code (the desk model) once per case; the work queue is a temp
copy (nothing real is queued). Cases are the questions Nova got wrong in that call (2026-11-25).
"""
import asyncio, json, os, re, shutil, sys, tempfile, time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts")); sys.path.insert(0, str(REPO / "scripts" / "meet"))

T0 = "00:00:00"       # wall clock of transcript 00:00 for old session-relative transcripts (set from the cases file)

# cut (HH:MM:SS), speaker, question, words that must appear (any of each group), words that must NOT appear
CASES_FILE = Path(os.environ.get("NOVA_MEMORY_CASES", str(Path.home() / ".config" / "nova" / "memory_eval_cases.json")))
# Cases come from a LOCAL file (real names/emails stay out of this public repo):
# {"meeting_dir": "...", "t0": "HH:MM:SS", "cases": [[cut "HH:MM:SS", speaker, question, [[any-of words], ...], [forbidden]]]}


def to_secs(hms):
    h, m, s = hms.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def cut_records(src: Path, dst: Path, cut: str, speaker: str, question: str):
    cut_s, t0 = to_secs(cut), to_secs(T0)
    out = []
    for line in (src / "transcript.txt").read_text(errors="replace").splitlines():
        m = re.match(r"\[(\d+):(\d+\.\d)\]\s+(\w+)\s+(.*)", line)
        if m:   # old format: session-relative -> wall clock
            t = t0 + int(m.group(1)) * 60 + float(m.group(2))
            who = {"CALLER": "HEARD", "AI": "NOVA", "TOOL": "BACKOFFICE"}.get(m.group(3), m.group(3))
            text = m.group(4)
        else:
            m = re.match(r"(\d\d:\d\d:\d\d)\s+(\S+)\s+(.*)", line)
            if not m:
                continue
            t, who, text = to_secs(m.group(1)), m.group(2), m.group(3)
        if t <= cut_s:
            out.append(f"{time.strftime('%H:%M:%S', time.gmtime(t))} {who:10s} {text}")
    out.append(f"{cut} {'HEARD':10s} {question}")
    (dst / "transcript.txt").write_text("\n".join(out) + "\n")
    caps = [l for l in (src / "who_said_what.txt").read_text(errors="replace").splitlines()
            if re.match(r"\d\d:\d\d:\d\d", l) and to_secs(l[:8]) <= cut_s]
    caps.append(f"{cut} [Captions] {speaker}: {question}")
    (dst / "who_said_what.txt").write_text("\n".join(caps) + "\n")


class FakeAgent:
    def __init__(self, tr):
        self.transcript, self._buf, self._lines = tr, {}, []


class FakeMaya:
    def __init__(self, d: Path, speaker):
        self.agent = FakeAgent(d / "transcript.txt")
        self.who_path = d / "who_said_what.txt"
        self.history, self.meeting_url, self.meeting_title = [], "https://meet.google.com/test", "Testing nova"
        self.recent_speakers = [(time.time(), speaker)]

    def caption_now(self):
        return None, None


async def main():
    global T0
    cfg = json.loads(CASES_FILE.read_text())
    CASES = [tuple(c) for c in cfg["cases"]]
    T0 = cfg.get("t0", T0)
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(cfg["meeting_dir"])
    tmp = Path(tempfile.mkdtemp(prefix="nova_mem_eval_"))
    work = tmp / "work"
    real = Path.home() / "nova_work" / "queue.json"
    work.mkdir()
    if real.exists():
        shutil.copy2(real, work / "queue.json")
    os.environ["NOVA_WORK"] = str(work)
    import live_meet
    ok_n, rows = 0, []
    for i, (cut, sp, q, must, never) in enumerate(CASES):
        d = tmp / f"case{i}"; d.mkdir()
        cut_records(src, d, cut, sp, q)
        t = time.time()
        ok, ans = await live_meet.desk(FakeMaya(d, sp), log=lambda *_: None)
        a = ans.lower()
        miss = [g for g in must if not any(w in a for w in g)]
        bad = [w for w in never if w in a]
        good = ok and not miss and not bad
        ok_n += good
        rows.append(f"{'PASS' if good else 'FAIL'} ({time.time() - t:.0f}s) Q: {q}\n     A: {ans}" +
                    (f"\n     missing: {miss}" if miss else "") + (f"\n     forbidden: {bad}" if bad else ""))
        print(rows[-1], flush=True)
    print(f"\n=== memory: {ok_n}/{len(CASES)} right  (records: {src.name}, cut copies in {tmp})")


if __name__ == "__main__":
    asyncio.run(main())
