import sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
from scripts.meet.suggester import Suggester


def test_rate_limit():
    now = [0.0]
    posted, calls = [], []
    def llm(tr, prev):
        calls.append(tr)
        return "NONE" if len(calls) == 2 else f"Maybe consider option {len(calls)}"
    s = Suggester(posted.append, llm=llm, min_interval=180, first_after=60, min_new_lines=2,
                  clock=lambda: now[0], log=lambda *a: None)
    for i in range(5):
        s.add("MEETING", f"line {i}")
    now[0] = 30; assert s.tick() is None and not calls          # too early
    now[0] = 61; assert s.tick() == "Maybe consider option 1"   # first suggestion
    s.add("MEETING", "a"); s.add("MEETING", "b")
    now[0] = 200; assert s.tick() is None and len(calls) == 1   # < 180 s since last
    now[0] = 242; assert s.tick() is None and len(calls) == 2   # LLM said NONE
    now[0] = 500; assert s.tick() is None and len(calls) == 2   # no new lines since
    s.add("MEETING", "c"); s.add("MEETING", "d")
    now[0] = 501; assert s.tick() == "Maybe consider option 3"
    assert posted == ["Maybe consider option 1", "Maybe consider option 3"]
    assert "line 4" in calls[0]


if __name__ == "__main__":
    test_rate_limit()
    print("suggester: all tests passed")
