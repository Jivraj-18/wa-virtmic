"""Decide whether a transcribed meeting utterance is addressed to Maya (pure functions, unit-tested).

Addressed  : "Maya, what do you think?"  "Hey Maya can you ..."  "What's your take, Maya?"  "OK so, Maya, ..."
Not        : "I sent it to Maya yesterday."  "Maya's numbers look off."  "Let's ask Maya later."  (3rd person)

The speech-to-text often misspells the name, so a few look-alikes count too (Maia, Mayah, Mya, Myah, Maja).
`early_address()` runs on the partial transcript (streaming deltas) so Maya can start answering before the
final transcript arrives; `is_addressed()` is the full rule on the final text.
"""
import re

NAMES = ["maya", "maia", "mayah", "maiya", "mya", "myah", "maja", "mayya"]
_NAME = r"(?:%s)" % "|".join(NAMES)
_FILLER = r"(?:hey|hi|hello|ok|okay|so|and|well|um|uh|right|yeah|yes|now|alright|all right|oh)"

# vocative at the start: "[filler,] Maya[,|?|!|space] <rest>"   (but not "Maya's" / "Maya said")
_START = re.compile(rf"^\s*(?:{_FILLER}[\s,.!]+){{0,3}}{_NAME}\b(?!['’]s)(?!\s+(?:said|says|thinks|thought|was|is|has|had|will|would|did|and|told|mentioned|wrote|sent)\b)",
                    re.I)
# vocative at the end: "..., Maya?"  "what do you think Maya."
_END = re.compile(rf"[\s,]{_NAME}\s*[?.!]*\s*$", re.I)
# vocative in the middle, set off by commas: "so, Maya, could you ..."
_MID = re.compile(rf",\s*{_NAME}\s*,", re.I)
# second-person cue after a mid-sentence name: "Maya can you", "Maya do you", "Maya what"
_CUE = re.compile(rf"\b{_NAME}\b[\s,]+(?:can|could|would|will|do|did|are|what|how|why|when|where|who|please|tell|give|summari[sz]e|any)\b",
                  re.I)
# words that make the name an object ("ask Maya", "sent it to Maya") -> about her, not to her
_THIRD_WORDS = {"ask", "asked", "to", "with", "from", "by", "for", "tell", "told", "let", "cc", "ping", "and",
                "thank", "thanks", "about", "like", "of", "on", "at", "call", "email", "message"}


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def mentions_name(text: str) -> bool:
    return re.search(rf"\b{_NAME}\b", text or "", re.I) is not None


def _object_of(t: str, name_start: int) -> bool:
    prev = re.findall(r"[a-z']+", t[:name_start].lower())
    return bool(prev) and prev[-1] in _THIRD_WORDS


def is_addressed(text: str) -> bool:
    t = norm(text)
    if not t or not mentions_name(t):
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


def early_address(partial: str) -> bool:
    """True as soon as the partial transcript clearly STARTS with a vocative ("Maya, ..."/"Hey Maya ...").
    Needs at least one word after the name, so 'Maya's ...' / 'Maya said ...' can still be ruled out."""
    t = norm(partial)
    m = _START.search(t)
    return bool(m) and len(t[m.end():].strip(" ,.!?")) > 0
