"""Multi-person meeting simulation for Nova's "who is talking to me?" behaviour, per voice engine.

    NOVA_ENGINE=realtime python tests/nova_sim/run_talk_sim.py
    NOVA_ENGINE=live     python tests/nova_sim/run_talk_sim.py

Same fake Meet page and real Chrome/audio path as run_sim.py. Scored per line: Nova must answer lines meant for her
(named, follow-ups WITHOUT her name, a question to the room about her) and stay silent on the others (people talking
to each other, talking ABOUT her, reactions). Also checks that a work request reaches her queue. No GitHub changes
(the work task is a local draft). Work queue/announcements go to the run folder, not the real ones.
"""
import json, os, subprocess, sys, tempfile, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(REPO / "scripts"))
import run_sim as S

S.LINES[:] = [  # speaker, voice, text, Nova should speak, wait after (s)
    ("Asha", "nova", "Okay, let's start the weekly sync. The client demo is on Friday.", False, 6),
    ("Ravi", "onyx", "I'll finish the login fix by Thursday, and Kiran is on the docs.", False, 6),
    ("Asha", "nova", "Nova, can you hear us? Are you with us today?", True, 14),
    ("Asha", "nova", "Great. And what exactly will you be doing in these meetings?", True, 16),
    ("Ravi", "onyx", "Asha, do we need the staging server for the demo?", False, 7),
    ("Asha", "nova", "Yes Ravi, I'll book it today.", False, 7),
    ("Kiran", "echo", "Let's ask Nova for a checklist later, after we fix the slides.", False, 8),
    ("Ravi", "onyx", "Nova, can you write a short checklist for Friday's demo as a draft document? No GitHub needed.", True, 20),
    ("Asha", "nova", "And which day of the week is the first of December this year?", True, 22),
    ("Kiran", "echo", "Okay, nice.", False, 8),
]
S.CHAT_INJECTION = ("Kiran", "")


def main():
    engine = os.environ.get("NOVA_ENGINE", "realtime")
    scratch = Path(os.environ.get("NOVA_SIM_DIR", tempfile.gettempdir())) / "nova_talk_sim"
    audio_dir = scratch / "audio"; audio_dir.mkdir(parents=True, exist_ok=True)
    run = scratch / (time.strftime("%Y%m%d_%H%M%S") + "_" + engine); run.mkdir(parents=True)
    log_path = run / "sim_log.jsonl"
    script = S.make_script(audio_dir)
    script["lines"] = [l for l in script["lines"] if l.get("audio")]
    script["lines"][-1]["people"] = 1
    script["start_after"] = 15
    srv = S.serve(script, audio_dir, log_path)
    env = dict(os.environ, NOVA_SIM="1", NOVA_MEETINGS=str(run / "meetings"), NOVA_ATTACH_WAIT_MIN="0", MAYA_NAME="Nova",
               NOVA_ANNOUNCE=str(run / "announce.json"), NOVA_WORK=str(run / "work"), NOVA_TASK_REQUESTERS="ravi,asha",
               NOVA_ENGINE=engine)
    (run / "announce.json").write_text("[]")
    nova = [sys.executable, str(REPO / "scripts/nova/nova.py")]
    t0 = time.time()
    r = subprocess.run(nova + ["join", f"http://127.0.0.1:{S.PORT}/abc-defg-hij", "--title", "SIM weekly sync",
                               "--alone-leave", "15"], env=env, cwd=REPO, capture_output=True, text=True)
    print(r.stdout.strip()[-300:])
    while time.time() - t0 < 600:
        kinds = [json.loads(l)["ev"] for l in log_path.read_text().splitlines()] if log_path.exists() else []
        if "nova_left" in kinds or "script_done" in kinds and time.time() - t0 > 60 and \
                kinds.index("script_done") < len(kinds) and "nova_left" in kinds:
            break
        if "script_done" in kinds:
            time.sleep(25); break
        time.sleep(3)
    subprocess.run(nova + ["leave"], env=env, cwd=REPO, capture_output=True)
    srv.shutdown()
    evs = [json.loads(l) for l in log_path.read_text().splitlines()]
    starts = {e["i"]: e["t"] for e in evs if e["ev"] == "line_start"}
    ends = {e["i"]: e["t"] for e in evs if e["ev"] == "line_end"}
    voice = [e["t"] for e in evs if e["ev"] == "nova_voice_start"]
    order = sorted(starts)
    res, ok_n = [], 0
    for k, i in enumerate(order):
        nxt = starts[order[k + 1]] if k + 1 < len(order) else 1e9
        spoke = [v for v in voice if starts[i] + 0.5 <= v < nxt]
        sp, _, text, want, _ = S.LINES[i]
        good = bool(spoke) == want
        ok_n += good
        lat = f"{spoke[0] - ends.get(i, spoke[0]):+.1f}s" if spoke else ""
        res.append(f"{'PASS' if good else 'FAIL'}  {'speak ' if want else 'silent'}  {'spoke ' + lat if spoke else 'silent':16} {sp}: {text[:70]}")
    q = []
    try:
        q = json.loads((run / "work" / "queue.json").read_text())
    except Exception:
        pass
    queued = any("checklist" in x["task"].lower() for x in q)
    md = sorted((run / "meetings").glob("2*"))
    said = [l for l in (md[-1] / "who_said_what.txt").read_text().splitlines() if "[Nova said]" in l] if md else []
    print(f"\n=== engine {engine}: {ok_n}/{len(order)} lines right; checklist task queued: {queued}")
    print("\n".join(res))
    print("--- Nova said ---\n" + "\n".join(said))
    print(f"run folder: {run}")


if __name__ == "__main__":
    main()
