"""Background chat suggestions: at most one every `min_interval` seconds, from the rolling meeting transcript.

An LLM (gateway chat completions) reads the last few minutes and either returns ONE short suggestion
("Maybe consider X", "You seem stuck on Y") or NONE. `post(text)` decides where it goes:
the Meet chat (join mode) or a log file (simulation).
"""
import json, threading, time, urllib.request
from collections import deque

import gateway

MODEL = "gpt-4.1-mini"
PROMPT = """You are Maya, a quiet AI participant in a team meeting. Below is the recent meeting transcript
(speech-to-text, so expect small errors). Decide whether ONE short chat message would genuinely help the
meeting right now: a consideration nobody raised, a way to unblock a discussion going in circles, or a
concrete next step. Write it like a helpful colleague in chat, max 20 words, e.g. "Maybe consider X" or
"You seem stuck on Y - could Z settle it?". Don't repeat earlier suggestions. Don't summarise.
If nothing is clearly useful, answer exactly NONE.

Earlier suggestions: {previous}

Transcript:
{transcript}"""


def chat_complete(messages, model=MODEL, timeout=30, retries=3) -> str:
    body = json.dumps({"model": model, "messages": messages, "temperature": 0.4, "max_tokens": 80}).encode()
    for attempt in range(retries):
        req = urllib.request.Request(gateway.base() + "/openai/v1/chat/completions", data=body,
                                     headers={**gateway.auth_header(), "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)["choices"][0]["message"]["content"].strip()
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == retries - 1:
                raise
            time.sleep(5 * (attempt + 1))  # back off on gateway rate limits
    return "NONE"


class Suggester:
    def __init__(self, post, llm=None, min_interval=180.0, first_after=60.0, check_every=20.0,
                 window_lines=40, min_new_lines=4, clock=time.monotonic, log=print):
        self.post, self.llm, self.log, self.clock = post, llm or self._llm, log, clock
        self.min_interval, self.first_after, self.check_every = min_interval, first_after, check_every
        self.lines = deque(maxlen=window_lines)
        self.min_new_lines = min_new_lines
        self.new_lines = 0
        self.t_start = clock()
        self.t_last = None
        self.previous = []
        self.stop = threading.Event()
        self.lock = threading.Lock()

    def add(self, who: str, text: str):
        if text and text.strip():
            with self.lock:
                self.lines.append(f"{who}: {text.strip()}")
                self.new_lines += 1

    def due(self) -> bool:
        now = self.clock()
        if now - self.t_start < self.first_after or self.new_lines < self.min_new_lines:
            return False
        return self.t_last is None or now - self.t_last >= self.min_interval

    def _llm(self, transcript: str, previous: list) -> str:
        return chat_complete([{"role": "user", "content": PROMPT.format(
            transcript=transcript, previous="; ".join(previous) or "(none)")}])

    def tick(self):
        """One check. Returns the posted suggestion or None."""
        if not self.due():
            return None
        with self.lock:
            transcript = "\n".join(self.lines)
            self.new_lines = 0
        self.t_last = self.clock()  # counts as an attempt even if the LLM says NONE (no hammering)
        try:
            out = self.llm(transcript, self.previous)
        except Exception as e:
            self.log(f"suggester: LLM failed: {type(e).__name__}: {e}")
            return None
        out = (out or "").strip().strip('"')
        if not out or out.upper().startswith("NONE"):
            self.log("suggester: nothing useful right now")
            return None
        out = out[:200]
        self.previous.append(out)
        self.post(out)
        return out

    def run(self):
        while not self.stop.wait(self.check_every):
            self.tick()

    def start(self) -> threading.Thread:
        th = threading.Thread(target=self.run, daemon=True)
        th.start()
        return th
