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


def test_yes():
    for t in YES:
        assert is_addressed(t), t


def test_no():
    for t in NO:
        assert not is_addressed(t), t


def test_early():
    assert early_address("Maya, what")
    assert early_address("Hey Maya can")
    assert not early_address("Maya")            # wait for the next word
    assert not early_address("Maya's numbers")
    assert not early_address("Maya said that")
    assert not early_address("I told Maya")


if __name__ == "__main__":
    for f in (test_yes, test_no, test_early):
        f()
    print("addressing: all tests passed")
