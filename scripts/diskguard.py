#!/usr/bin/env python3
"""Disk-safety helpers: this often runs on a phone, so storage is limited.

  DISK_MIN_FREE_GB   stop writing recordings/debug dumps below this much free space (default 2)
  CALLS_MAX_MB       keep scripts/calls/ under this size by deleting the oldest call folders (default 1000)

Usage: python3 scripts/diskguard.py   -> prints free space and the calls/ size, exit 1 if low.
"""
import os, shutil, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MIN_FREE_GB = float(os.environ.get("DISK_MIN_FREE_GB", "2"))
CALLS_MAX_MB = float(os.environ.get("CALLS_MAX_MB", "1000"))


def free_gb(path=HERE) -> float:
    return shutil.disk_usage(path).free / 1e9


def low(path=HERE, min_gb: float | None = None) -> bool:
    """True when free space under `path` is below the threshold (callers then skip optional writes)."""
    return free_gb(path) < (MIN_FREE_GB if min_gb is None else min_gb)


def dir_mb(d: Path) -> float:
    return sum(f.stat().st_size for f in Path(d).rglob("*") if f.is_file()) / 1e6


def prune_dirs(parent: Path, max_mb: float = CALLS_MAX_MB, keep: Path | None = None) -> list[Path]:
    """Delete the oldest sub-folders of `parent` (by name = timestamp) until it fits in `max_mb`.
    Never deletes `keep` (the call in progress). Returns the folders removed."""
    parent = Path(parent)
    if not parent.is_dir():
        return []
    dirs = sorted(p for p in parent.iterdir() if p.is_dir())
    sizes = {p: dir_mb(p) for p in dirs}
    total, removed = sum(sizes.values()), []
    for p in dirs:
        if total <= max_mb:
            break
        if keep is not None and p.resolve() == Path(keep).resolve():
            continue
        shutil.rmtree(p, ignore_errors=True)
        total -= sizes[p]
        removed.append(p)
    return removed


if __name__ == "__main__":
    calls = HERE / "calls"
    print(f"free: {free_gb():.1f} GB (min {MIN_FREE_GB:g} GB)   calls/: {dir_mb(calls) if calls.exists() else 0:.0f} MB "
          f"(max {CALLS_MAX_MB:g} MB)")
    sys.exit(1 if low() else 0)
