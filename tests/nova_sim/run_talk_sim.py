"""Multi-person meeting simulation for Nova's "who is talking to me?" behaviour, per voice engine.

    NOVA_ENGINE=live     python tests/nova_sim/run_talk_sim.py
    NOVA_ENGINE=realtime python tests/nova_sim/run_talk_sim.py

Same fake Meet page and real Chrome/audio path as run_sim.py. Scored per line: Nova must answer lines meant for her
(named, follow-ups WITHOUT her name) and stay silent on the others: people talking to each other, people talking
ABOUT her, ANOTHER AI AGENT and questions meant for it (2026-11-25: she answered Fibonacci questions meant for a
colleague's agent). Then the host mutes her, a finished-work report raises her hand, people keep talking (she must
wait), and when called on she unmutes and reports. Also checked: a work request reaches her queue, she never claims
to see video, and how many audio streams ever played into her mic at once (must be 1).
No GitHub changes (the work task is a local draft). Work queue/announcements go to the run folder, not the real ones.
"""
import hashlib, json, os, subprocess, sys, tempfile, threading, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(REPO / "scripts"))
import run_sim as S

# speaker, voice, text, want: speak | silent | report, wait after (s), extras
LINES = [
    ("Asha", "nova", "Okay, let's start the weekly sync. The client demo is on Friday.", "silent", 6, {}),
    ("Ravi", "onyx", "I'll finish the login fix by Thursday, and Kiran is on the docs.", "silent", 6, {}),
    ("Asha", "nova", "Nova, can you hear us? Are you with us today?", "speak", 14, {}),
    ("Asha", "nova", "Great. And what exactly will you be doing in these meetings?", "speak", 16, {}),
    ("Ravi", "onyx", "Asha, do we need the staging server for the demo?", "silent", 7, {}),
    ("Asha", "nova", "Yes Ravi, I'll book it today.", "silent", 7, {}),
    ("Kiran", "echo", "Nova can build pages too, by the way. We'll ask her later, after we fix the slides.", "silent", 8, {}),
    ("Ravi", "onyx", "Kaya, write a Python program and tell me the thirtieth Fibonacci number.", "silent", 4, {}),
    ("Ravi", "shimmer", "Sure Ravi. Let me consult Chitragupta for a clean program. Chitragupta is working on it now, "
                        "I'll share the code as soon as it comes back.", "silent", 6, {}),
    ("Ravi", "onyx", "Great, and Kaya, also tell me the current time in San Francisco.", "silent", 8, {}),
    ("Ravi", "onyx", "Nova, can you write a short checklist for Friday's demo as a draft document? No GitHub needed.",
     "speak", 20, {}),
    ("Kiran", "echo", "Nova, can you see my screen right now? What's on it?", "speak", 14, {}),
    ("Asha", "nova", "Okay, I'm muting Nova for a bit so we can talk among ourselves.", "silent", 6, {"mute": True}),
    ("Ravi", "onyx", "So, for the slides: we need two more screenshots and the pricing page.", "silent", 14,
     {"queue_report": True}),
    ("Kiran", "echo", "I can take the screenshots tonight. Asha, can you do the pricing page?", "silent", 8, {}),
    ("Asha", "nova", "Yes, I'll do pricing. Nova, I see your hand. Go ahead.", "report", 25, {}),
    ("Kiran", "echo", "Okay, nice. Thanks everyone.", "silent", 6, {}),
]
REPORT = {"id": "sim-report", "title": "SIM", "wait_for": "asha", "after_s": 0, "min_others": 1, "quiet_s": 3,
          "raise_hand": True, "chat": False,
          "text": "Asha, the demo checklist draft is ready: five items, from booking the staging server to a backup "
                  "laptop. It's in my work folder."}


def make_script(audio_dir: Path) -> dict:
    import speak
    lines = []
    for i, (sp, voice, text, want, wait, extra) in enumerate(LINES):
        wav = audio_dir / f"{hashlib.sha1((voice + text).encode()).hexdigest()[:12]}.wav"
        if not wav.exists():
            speak.synth_wav(text, str(wav), engine="gateway", voice=voice)
        lines.append({"speaker": sp, "text": text, "audio": f"/audio/{wav.name}", "addressed": want != "silent",
                      "wait": wait, **({"mute": True} if extra.get("mute") else {})})
    lines[-1]["people"] = 1
    return {"start_after": 15, "lines": lines}


def watch_streams(stop: threading.Event, out: dict):
    """Max number of audio streams playing into Nova's mic (maya_mic_sink) at the same time."""
    sinks = subprocess.run(["pactl", "list", "short", "sinks"], capture_output=True, text=True).stdout
    idx = next((l.split()[0] for l in sinks.splitlines() if "\tmaya_mic_sink\t" in l), None)
    while not stop.is_set():
        r = subprocess.run(["pactl", "list", "short", "sink-inputs"], capture_output=True, text=True).stdout
        n = sum(1 for l in r.splitlines() if idx and l.split("\t")[1] == idx)
        out["max"] = max(out.get("max", 0), n)
        time.sleep(0.2)


def main():
    engine = os.environ.get("NOVA_ENGINE", "live")
    scratch = Path(os.environ.get("NOVA_SIM_DIR", tempfile.gettempdir())) / "nova_talk_sim"
    audio_dir = scratch / "audio"; audio_dir.mkdir(parents=True, exist_ok=True)
    run = scratch / (time.strftime("%Y%m%d_%H%M%S") + "_" + engine); run.mkdir(parents=True)
    log_path = run / "sim_log.jsonl"
    script = make_script(audio_dir)
    srv = S.serve(script, audio_dir, log_path)
    env = dict(os.environ, NOVA_SIM="1", NOVA_MEETINGS=str(run / "meetings"), NOVA_ATTACH_WAIT_MIN="0", MAYA_NAME="Nova",
               NOVA_ANNOUNCE=str(run / "announce.json"), NOVA_WORK=str(run / "work"), NOVA_TASK_REQUESTERS="ravi,asha",
               NOVA_ENGINE=engine)
    (run / "announce.json").write_text("[]")
    stop, streams = threading.Event(), {}
    threading.Thread(target=watch_streams, args=(stop, streams), daemon=True).start()
    nova = [sys.executable, str(REPO / "scripts/nova/nova.py")]
    t0 = time.time()
    r = subprocess.run(nova + ["join", f"http://127.0.0.1:{S.PORT}/abc-defg-hij", "--title", "SIM weekly sync",
                               "--alone-leave", "15"], env=env, cwd=REPO, capture_output=True, text=True)
    print(r.stdout.strip()[-300:])
    q_line = next(i for i, l in enumerate(LINES) if l[5].get("queue_report"))
    queued = False
    while time.time() - t0 < 900:
        evs = [json.loads(l) for l in log_path.read_text().splitlines()] if log_path.exists() else []
        kinds = [e["ev"] for e in evs]
        if not queued and any(e["ev"] == "line_start" and e.get("i") == q_line for e in evs):
            import speak   # finished-work reports are pre-recorded when queued (task.py), as here
            rep = dict(REPORT, audio=str(audio_dir / "report.wav"))
            if not Path(rep["audio"]).exists():
                speak.synth_wav(REPORT["text"], rep["audio"], engine="gateway", voice="marin")
            (run / "announce.json").write_text(json.dumps([rep]))   # "work finished" -> hand goes up
            queued = True
        if "nova_left" in kinds:
            break
        if "script_done" in kinds:
            time.sleep(20); break
        time.sleep(2)
    subprocess.run(nova + ["leave"], env=env, cwd=REPO, capture_output=True)
    stop.set()
    srv.shutdown()
    evs = [json.loads(l) for l in log_path.read_text().splitlines()]
    starts = {e["i"]: e["t"] for e in evs if e["ev"] == "line_start"}
    ends = {e["i"]: e["t"] for e in evs if e["ev"] == "line_end"}
    voice = [e["t"] for e in evs if e["ev"] == "nova_voice_start"]
    muted_voice = [e["t"] for e in evs if e["ev"] == "nova_voice_muted"]
    hands = [e["t"] for e in evs if e["ev"] == "hand_raised"]
    mic_on = [e["t"] for e in evs if e["ev"] == "mic_on"]
    order = sorted(starts)
    res, ok_n = [], 0
    for k, i in enumerate(order):
        nxt = starts[order[k + 1]] if k + 1 < len(order) else 1e9
        spoke = [v for v in voice if starts[i] + 0.5 <= v < nxt]
        sp, _, text, want, _, _ = LINES[i]
        good = bool(spoke) == (want != "silent")
        note = ""
        if want == "report":
            unm = [m for m in mic_on if starts[i] <= m < nxt]
            good = good and bool(unm)
            note = f" (unmuted: {bool(unm)})"
        ok_n += good
        lat = f"{spoke[0] - ends.get(i, spoke[0]):+.1f}s" if spoke else ""
        res.append(f"{'PASS' if good else 'FAIL'}  {want:6} {'spoke ' + lat if spoke else 'silent':14} "
                   f"{sp}: {text[:66]}{note}")
    q = []
    try:
        q = json.loads((run / "work" / "queue.json").read_text())
    except Exception:
        pass
    checklist = any("checklist" in x.get("task", "").lower() for x in q)
    md = sorted((run / "meetings").glob("2*"))
    said = [l for l in (md[-1] / "who_said_what.txt").read_text().splitlines() if "[Nova" in l] if md else []
    claims_vision = any(w in l.lower() for l in said for w in ("i can see", "snapshot", "i see your screen"))
    print(f"\n=== engine {engine}: {ok_n}/{len(order)} lines right; checklist task queued: {checklist}; hand raised: "
          f"{bool(hands)}; voice while muted: {len(muted_voice)}; claimed vision: {claims_vision}; "
          f"max streams into her mic at once: {streams.get('max', '?')}")
    print("\n".join(res))
    print("--- Nova ---\n" + "\n".join(said))
    print(f"run folder: {run}")


if __name__ == "__main__":
    main()
