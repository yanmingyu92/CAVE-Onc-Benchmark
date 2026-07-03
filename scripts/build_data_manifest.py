"""Build a SHA-256 manifest for all data files under data/.

Usage:
    python -m scripts.build_data_manifest --data-dir data --out data/MANIFEST.sha256

Walks data/ recursively, computes SHA-256 per file, sorts by relative path,
writes one line per file: ``<sha256>  <relpath>\\n`` (two-space separator,
GNU sha256sum -b compatible).

Excludes MANIFEST.sha256 and PROVENANCE.md from the scan.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path

_EXCLUDE_NAMES: frozenset[str] = frozenset({"MANIFEST.sha256", "PROVENANCE.md"})

BUFFER_SIZE: int = 1 << 20  # 1 MiB


def sha256_of(path: Path) -> str:
    """Return lowercase hex SHA-256 digest of *path*."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(BUFFER_SIZE)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def build_manifest(data_dir: Path) -> list[tuple[str, str]]:
    """Collect (sha256, relpath) tuples, sorted by relpath."""
    entries: list[tuple[str, str]] = []
    for root, _dirs, files in os.walk(data_dir):
        for fname in files:
            if fname in _EXCLUDE_NAMES:
                continue
            fpath = Path(root) / fname
            relpath = fpath.relative_to(data_dir).as_posix()
            digest = sha256_of(fpath)
            entries.append((digest, relpath))
    entries.sort(key=lambda t: t[1])
    return entries


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Build SHA-256 manifest for data files."
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data"),
        help="Root data directory (default: data)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("data/MANIFEST.sha256"),
        help="Output manifest path (default: data/MANIFEST.sha256)",
    )
    args = parser.parse_args(argv)

    data_dir: Path = args.data_dir.resolve()
    out_path: Path = args.out.resolve()

    if not data_dir.is_dir():
        print(f"Error: {data_dir} is not a directory.", file=sys.stderr)
        sys.exit(1)

    entries = build_manifest(data_dir)

    lines = [f"{digest}  {relpath}\n" for digest, relpath in entries]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", newline="\n") as fh:
        fh.writelines(lines)

    print(f"Wrote {len(lines)} entries to {out_path}")


if __name__ == "__main__":
    main()
