"""Inventory the real-world PDS oncology data: per-dataset shapes + columns.

Walks ``data/real_oncology_data/`` (or a given root), reads metadata only from
every ``.sas7bdat`` / ``.csv`` file, and emits a column-level inventory CSV used
to drive the Item E legacy->SDTM mapping (see ``docs/item_e_real_data_plan.md``).

The raw PDS data is gitignored (sponsor data-use terms); this inventory CSV and
the SHA-256 manifest are the committed provenance artifacts.

Usage:
    python -m scripts.explore_real_data \
        --root data/real_oncology_data --out gate_a/real_data_inventory.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import pyreadstat


def _study_tag(path: Path, root: Path) -> str:
    """Top-level package folder name relative to *root* (e.g. AllProvidedFiles_123)."""
    rel = path.relative_to(root)
    return rel.parts[0] if rel.parts else ""


def _iter_sas(root: Path):
    for p in sorted(root.rglob("*.sas7bdat")):
        try:
            _df, meta = pyreadstat.read_sas7bdat(str(p), metadataonly=True)
        except Exception as exc:  # noqa: BLE001 - report, keep scanning
            yield p, None, None, str(exc)
            continue
        labels = dict(zip(meta.column_names, meta.column_labels or []))
        yield p, meta, labels, ""


def _iter_csv(root: Path):
    for p in sorted(root.rglob("*.csv")):
        try:
            with open(p, "r", encoding="utf-8", newline="") as fh:
                reader = csv.reader(fh)
                header = next(reader, [])
                nrows = sum(1 for _ in reader)
        except Exception as exc:  # noqa: BLE001
            yield p, None, 0, str(exc)
            continue
        yield p, header, nrows, ""


def build_rows(root: Path) -> list[dict]:
    rows: list[dict] = []
    for p, meta, labels, err in _iter_sas(root):
        tag = _study_tag(p, root)
        if err:
            rows.append({"study": tag, "dataset": p.stem, "format": "sas7bdat",
                         "n_rows": "", "column": "", "label": f"ERROR: {err}"})
            continue
        for col in meta.column_names:
            rows.append({"study": tag, "dataset": p.stem, "format": "sas7bdat",
                         "n_rows": meta.number_rows, "column": col,
                         "label": labels.get(col, "")})
    for p, header, nrows, err in _iter_csv(root):
        tag = _study_tag(p, root)
        if err:
            rows.append({"study": tag, "dataset": p.stem, "format": "csv",
                         "n_rows": "", "column": "", "label": f"ERROR: {err}"})
            continue
        for col in header:
            rows.append({"study": tag, "dataset": p.stem, "format": "csv",
                         "n_rows": nrows, "column": col, "label": ""})
    return rows


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Inventory real PDS oncology data.")
    parser.add_argument("--root", type=Path, default=Path("data/real_oncology_data"))
    parser.add_argument("--out", type=Path, default=Path("gate_a/real_data_inventory.csv"))
    args = parser.parse_args(argv)

    root: Path = args.root.resolve()
    if not root.is_dir():
        print(f"Error: {root} is not a directory.", file=sys.stderr)
        sys.exit(1)

    rows = build_rows(root)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=["study", "dataset", "format", "n_rows", "column", "label"]
        )
        writer.writeheader()
        writer.writerows(rows)

    n_datasets = len({(r["study"], r["dataset"]) for r in rows})
    print(f"Wrote {len(rows)} column rows across {n_datasets} datasets to {args.out}")


if __name__ == "__main__":
    main()
