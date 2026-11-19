#!/usr/bin/env python3
"""Script-side hang-up: the call script ends the call itself, instead of trusting the AI to call a tool.

Why: on a real call the caller asked ~6 times to end the call; the AI said "Goodbye, ending the call now" every time
but never called its end_call tool, so the call ran to the 10-minute limit.

HangupWatcher.feed(who, text) gets every transcript line (realtime_agent.Agent(on_line=...)). It fires
on_hangup(reason) once, ~GRACE seconds after the trigger so the AI's goodbye finishes playing, when:
  1. the caller asked to end / said bye  AND  the AI said goodbye   (either order, within WINDOW s), or
  2. the caller asked to end twice within WINDOW s (the AI ignored it), or
  3. the AI said goodbye twice within WINDOW s (the AI thinks the call is over and keeps saying so).
A single stray "Goodbye!" (e.g. the AI misreading line noise) does NOT hang up.
"""
import re, threading, time

CALLER_END = re.compile(
    r"\b(cut|end|hang ?up|disconnect|drop|close|stop)\b.{0,20}\bcall\b"   # "cut the call", "end this call"
    r"|\bcall\b.{0,12}\b(cut|end|off)\b"                                    # "call cut kar do"
    r"|\bhang (it )?up\b|\bgood ?bye\b|\bbye\b|\bgood ?night\b|\btake care\b"
    r"|\b(phone|call) (rakh|kaat|kat|band)|\b(rakhta|rakhti|rakho|kaato|kaat do|kat do)\b",
    re.I)
AI_BYE = re.compile(
    r"\bgood ?bye\b|\bbye\b|\bgood ?night\b|\b(ending|end|hanging up|cut(ting)?) (the |this )?call\b|\bhang(ing)? up\b",
    re.I)


class HangupWatcher:
    def __init__(self, on_hangup, log=print, window: float = 30.0, grace: float = 2.5):
        self.on_hangup, self.log, self.window, self.grace = on_hangup, log, window, grace
        self.caller_end: list[float] = []
        self.ai_bye: list[float] = []
        self.fired = False
        self._lock = threading.Lock()

    def _recent(self, ts: list[float], now: float) -> list[float]:
        ts[:] = [t for t in ts if now - t <= self.window]
        return ts

    def feed(self, who: str, text: str, now: float | None = None) -> str | None:
        """Returns the hang-up reason if this line triggered it (the callback runs after `grace` seconds)."""
        now = time.time() if now is None else now
        with self._lock:
            if self.fired:
                return None
            if who == "CALLER" and CALLER_END.search(text):
                self.caller_end.append(now)
            elif who == "AI" and AI_BYE.search(text):
                self.ai_bye.append(now)
            else:
                return None
            ce, ab = self._recent(self.caller_end, now), self._recent(self.ai_bye, now)
            reason = ("caller asked to end + AI said goodbye" if ce and ab else
                      "caller asked to end twice" if len(ce) >= 2 else
                      "AI said goodbye twice" if len(ab) >= 2 else None)
            if not reason:
                return None
            self.fired = True
        self.log(f"hangup: {reason} (last line {who}: {text[:80]!r}) - hanging up in {self.grace:g}s")
        threading.Timer(self.grace, self.on_hangup, args=(reason,)).start()
        return reason
