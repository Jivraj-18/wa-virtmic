import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import hangup  # noqa: E402


def _watch(lines):
    """Feed (t, who, text) lines; returns (t, reason) of the first trigger or None. Timers are not started."""
    w = hangup.HangupWatcher(lambda r: None, log=lambda *a: None, grace=0)
    hangup.threading.Timer = lambda *a, **k: type("T", (), {"start": lambda self: None})()
    for t, who, text in lines:
        r = w.feed(who, text, now=t)
        if r:
            return t, r
    return None


def test_caller_asks_then_ai_goodbye():
    assert _watch([(147, "CALLER", "Could you cut the call?"), (151, "AI", "Goodbye for now.")]) == \
        (151, "caller asked to end + AI said goodbye")


def test_single_stray_ai_goodbye_does_not_hang_up():
    # real call: line noise was transcribed as "ね" and the AI answered "Goodbye!"
    assert _watch([(29.7, "CALLER", "ね"), (30.1, "AI", "Goodbye! It was nice talking with you."),
                   (34.2, "CALLER", "What I'll be doing is")]) is None


def test_ai_goodbyes_far_apart_do_not_hang_up():
    assert _watch([(30, "AI", "Goodbye!"), (133, "AI", "Goodbye! Ending the call now")]) is None


def test_caller_asks_twice_even_if_ai_never_says_bye():
    assert _watch([(300, "CALLER", "Are you going to cut the call?"), (310, "CALLER", "Please end the call.")]) == \
        (310, "caller asked to end twice")


def test_hinglish_request():
    assert _watch([(10, "CALLER", "achha phone rakhta hu"), (12, "AI", "Okay, bye!")])[1] == \
        "caller asked to end + AI said goodbye"


def test_normal_talk_about_calls_does_not_trigger():
    assert _watch([(5, "CALLER", "Can you call the API and end up with a list?"),
                   (9, "AI", "Sure, I can explain how to call it.")]) is None
