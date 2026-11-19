import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import diskguard  # noqa: E402


def _call(parent: Path, name: str, mb: float) -> Path:
    d = parent / name
    d.mkdir()
    (d / "ai.wav").write_bytes(b"\0" * int(mb * 1e6))
    return d


def test_prune_removes_oldest_until_under_budget(tmp_path):
    a, b, c = (_call(tmp_path, n, 2) for n in ("20261101_100000", "20261102_100000", "20261103_100000"))
    removed = diskguard.prune_dirs(tmp_path, max_mb=4.5)
    assert removed == [a] and not a.exists() and b.exists() and c.exists()


def test_prune_never_deletes_the_call_in_progress(tmp_path):
    a = _call(tmp_path, "20261101_100000", 5)
    b = _call(tmp_path, "20261102_100000", 1)
    removed = diskguard.prune_dirs(tmp_path, max_mb=0.5, keep=a)
    assert a.exists() and removed == [b]


def test_prune_missing_dir_is_noop(tmp_path):
    assert diskguard.prune_dirs(tmp_path / "nope", max_mb=1) == []


def test_low_threshold(tmp_path):
    free = diskguard.free_gb(tmp_path)
    assert diskguard.low(tmp_path, min_gb=free + 1000)
    assert not diskguard.low(tmp_path, min_gb=0)
