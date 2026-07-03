"""Generate a deterministic SHA-256 manifest of the CORE rule cache.

Usage: python scripts/snapshot_core_cache.py --core-root vendor/core
"""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

CACHE_SUBDIR = "resources/cache"
OUTPUT_PATH = Path("gate_a/cache_snapshot.txt")
CORE_REMOTE = "https://github.com/cdisc-org/cdisc-rules-engine"


def _git_info(core_root: Path) -> tuple[str, str, str]:
    """Return (tag, commit_sha, iso_date) from the CORE checkout."""
    tag = subprocess.check_output(
        ["git", "describe", "--tags", "--exact-match"],
        cwd=core_root, stderr=subprocess.DEVNULL,
    ).decode().strip()
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=core_root,
    ).decode().strip()
    iso_date = subprocess.check_output(
        ["git", "show", "-s", "--format=%cI", "HEAD"], cwd=core_root,
    ).decode().strip()
    return tag, commit, iso_date


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def generate_snapshot(core_root: Path) -> None:
    """Walk the cache dir and write ``gate_a/cache_snapshot.txt``."""
    cache_dir = core_root / CACHE_SUBDIR
    if not cache_dir.is_dir():
        raise FileNotFoundError(f"Cache directory not found: {cache_dir}")

    tag, commit, iso_date = _git_info(core_root)
    files = sorted(p for p in cache_dir.rglob("*") if p.is_file())

    lines: list[str] = []
    for fp in files:
        rel = fp.relative_to(cache_dir).as_posix()
        lines.append(f"{_sha256_file(fp)}  {rel}\n")

    aggregate_sha = hashlib.sha256("".join(lines).encode()).hexdigest()

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8", newline="\n") as f:
        f.write(f"# CORE cache snapshot\n")
        f.write(f"date: {iso_date}\n")
        f.write(f"core_repo: {CORE_REMOTE}\n")
        f.write(f"core_tag: {tag}\n")
        f.write(f"core_commit: {commit}\n")
        f.write(f"cache_root: {CACHE_SUBDIR}\n")
        f.write(f"file_count: {len(files)}\n")
        f.write(f"aggregate_sha256: {aggregate_sha}\n\n")
        f.write(f"# Per-file SHA-256 (sorted by path, relative to cache_root)\n")
        f.writelines(lines)

    print(f"Snapshot written to {OUTPUT_PATH} ({len(files)} files)")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="SHA-256 manifest of CORE cache.")
    parser.add_argument("--core-root", type=Path, required=True)
    generate_snapshot(parser.parse_args().core_root.resolve())
