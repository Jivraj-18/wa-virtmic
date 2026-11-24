import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from scripts.meet.addressing import is_addressed, early_address

YES = ["Maya, what do you think?", "Hey Maya, can you summarize the options?", "maya what's the risk here",
       "OK so, Maya, could you give us a quick recap?", "What's your take, Maya?", "What do you think Maya.",
       "Maia, any ideas?", "Right, Maya. Which option is cheaper?", "Um, Maya can you help us decide",
       "So which one should we pick, Maya?"]
NO = ["I sent the draft to Maya yesterday.", "Maya's numbers look off to me.", "Let's ask Maya later.",
      "Maya said the deadline moved.", "We should loop in Maya and Ravi.", "The budget is fine.",
      "Thanks Maya.", "I talked with Maya about it", "Maya and I will handle the slides.", ""]


NAMES = ("Maya", "Nova")


def test_yes():
    for n in NAMES:
        for t in YES:
            t = t.replace("Maya", n).replace("maya", n.lower()).replace("Maia", "Novah" if n == "Nova" else "Maia")
            assert is_addressed(t, n), t


def test_no():
    for n in NAMES:
        for t in NO:
            t = t.replace("Maya", n)
            assert not is_addressed(t, n), t


def test_nova_hindi_and_isolation():
    assert is_addressed("नोवा, आज का एजेंडा क्या है?", "Nova")
    assert is_addressed("नोवा जी, summary दो", "Nova")
    assert is_addressed("okay Nova, what did we decide?", "Nova")
    assert not is_addressed("Maya, what do you think?", "Nova")       # old name no longer triggers
    assert is_addressed("Hi Noah, can you hear me?", "Nova")      # Meet captions spell Nova as Noah
    assert is_addressed("Oh, hi, Noah! Can you hear me?", "Nova")
    assert not is_addressed("the supernova demo went well", "Nova")


def test_early():
    assert early_address("Nova, what", "Nova")
    assert early_address("Maya, what", "Maya")
    assert early_address("Hey Maya can", "Maya")
    assert not early_address("Maya", "Maya")            # wait for the next word
    assert not early_address("Maya's numbers", "Maya")
    assert not early_address("Maya said that", "Maya")
    assert not early_address("I told Maya", "Maya")


if __name__ == "__main__":
    for f in (test_yes, test_no, test_nova_hindi_and_isolation, test_early):
        f()
    print("addressing: all tests passed")
