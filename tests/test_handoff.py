import sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import handoff  # noqa: E402


def _fired(lines):
    got = []
    w = handoff.EscalationWatcher(got.append, log=lambda *a: None)
    for who, text in lines:
        w.feed(who, text)
    time.sleep(0.05)   # on_escalate runs in a thread
    return got


def test_ai_handover_line_rings_with_caller_reason():
    got = _fired([("CALLER", "I want a refund, let me talk to a real person."),
                  ("AI", "Let me connect you to a person, please hold on.")])
    assert got == ["I want a refund, let me talk to a real person."]


def test_rings_once_per_call():
    assert len(_fired([("AI", "Connecting you with a real person now."),
                       ("AI", "Let me transfer you to someone who can help.")])) == 1


def test_ordinary_lines_do_not_ring():
    assert _fired([("AI", "Let me get that for you."), ("AI", "I am not a person, I'm an AI."),
                   ("AI", "I'll pass on your message to the team."),
                   ("CALLER", "Connect me to a person.")]) == []   # only the AI's own handover line rings
