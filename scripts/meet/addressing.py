"""Decide whether a transcribed meeting utterance is addressed to the agent (pure functions, unit-tested).

The agent's name comes from MAYA_NAME (default "Nova"); examples below use Maya, the old name.

Addressed  : "Maya, what do you think?"  "Hey Maya can you ..."  "What's your take, Maya?"  "OK so, Maya, ..."
Not        : "I sent it to Maya yesterday."  "Maya's numbers look off."  "Let's ask Maya later."  (3rd person)

The speech-to-text often misspells the name, so a few look-alikes count too (Maia, Mayah, Mya, Myah, Maja).
`early_address()` runs on the partial transcript (streaming deltas) so Maya can start answering before the
final transcript arrives; `is_addressed()` is the full rule on the final text.
"""
import os, re
from functools import lru_cache

AGENT_NAME = os.environ.get("MAYA_NAME", "Nova")
# Latin spellings + how STT writes the name in Hindi (Devanagari) and Urdu script when people speak Hindi/Hinglish.
# Look-alikes are only ones STT really produces for the name. "noah": Google Meet's captions AND gpt-4o-transcribe
# wrote "Hi Nova, can you hear me?" as "Hi Noah, can you hear me?" every time on 2026-11-24 - so it must count, even
# though Noah is a real name (if the team has a Noah, remove it here and rely on the other spellings).
VARIANTS = {
    "maya": ["maya", "sumaya", "somaya", "maia", "mayah", "maiya", "mya", "myah", "maja", "mayya", "माया", "मया",
             "मायाजी", "مایا", "مايا", "ماया"],
    "nova": ["nova", "novah", "novaa", "nowa", "noava", "knova", "noah", "noa", "nouva", "नोवा", "नोवाजी", "नोवा जी", "नोवाँ",
             "نووا", "نوا", "نووہ"],
}


def names_for(name: str) -> list:
    return VARIANTS.get(name.strip().lower(), [name.strip().lower()])


@lru_cache(maxsize=8)
def _rx(name: str):
    nm = r"(?:%s)" % "|".join(re.escape(n) for n in sorted(names_for(name), key=len, reverse=True))
    return nm


_FILLER = r"(?:hey|hi|hello|ok|okay|so|and|well|um|uh|right|yeah|yes|now|alright|all right|oh)"


@lru_cache(maxsize=8)
def _rules(name: str):
    _NAME = _rx(name)
    # vocative at the start: "[filler,] Maya[,|?|!|space] <rest>"   (but not "Maya's" / "Maya said")
    _START = re.compile(rf"^\s*(?:{_FILLER}[\s,.!]+){{0,3}}{_NAME}(?!\w)(?!['’]s)(?!\s+(?:said|says|thinks|thought|was|is|has|had|will|would|did|and|told|mentioned|wrote|sent)\b)",
                    re.I)
    # vocative at the end: "..., Maya?"  "what do you think Maya."
    _END = re.compile(rf"[\s,]{_NAME}\s*[?.!]*\s*$", re.I)
    # vocative in the middle, set off by commas: "so, Maya, could you ..."
    _MID = re.compile(rf",\s*{_NAME}\s*,", re.I)
    # second-person cue after a mid-sentence name: "Maya can you", "Maya do you", "Maya what"
    _CUE = re.compile(rf"(?<!\w){_NAME}(?!\w)[\s,]+(?:can|could|would|will|do|did|are|what|how|why|when|where|who|please|tell|give|summari[sz]e|any)\b",
                  re.I)
    return _START, _END, _MID, _CUE, _NAME


# words that make the name an object ("ask Maya", "sent it to Maya") -> about her, not to her
_THIRD_WORDS = {"ask", "asked", "to", "with", "from", "by", "for", "tell", "told", "let", "cc", "ping", "and",
                "thank", "thanks", "about", "like", "of", "on", "at", "call", "email", "message"}


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def mentions_name(text: str, name: str = None) -> bool:
    return re.search(rf"(?<!\w){_rx(name or AGENT_NAME)}(?!\w)", text or "", re.I) is not None


def _object_of(t: str, name_start: int) -> bool:
    prev = re.findall(r"[a-z']+", t[:name_start].lower())
    return bool(prev) and prev[-1] in _THIRD_WORDS


def is_addressed(text: str, name: str = None) -> bool:
    name = name or AGENT_NAME
    _START, _END, _MID, _CUE, _NAME = _rules(name)
    t = norm(text)
    if not t or not mentions_name(t, name):
        return False
    if _START.search(t) or _MID.search(t):
        return True
    for rx in (_CUE, _END):
        m = rx.search(t)
        if m:
            name = re.search(rf"{_NAME}", t[m.start():], re.I)
            if not _object_of(t, m.start() + name.start()):
                return True
    return False


def early_address(partial: str, name: str = None) -> bool:
    """True as soon as the partial transcript clearly STARTS with a vocative ("Maya, ..."/"Hey Maya ...").
    Needs at least one word after the name, so 'Maya's ...' / 'Maya said ...' can still be ruled out."""
    _START = _rules(name or AGENT_NAME)[0]
    t = norm(partial)
    m = _START.search(t)
    return bool(m) and len(t[m.end():].strip(" ,.!?")) > 0
