"""Reproduce the CAVE-Onc expert-validation (G8) agreement statistics.

Recomputes Fleiss' kappa and the summary counts from the de-identified
per-archetype rating matrix (``eval/expert_ratings_deidentified.csv``) and
checks them against the values reported in the manuscript. This lets any reader
independently reproduce the kappa = 0.705 finding without access to the raw
(reviewer-identifiable) response files.

Run from the repo root:
    python scripts/reproduce_kappa.py
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

CSV_PATH = Path("eval/expert_ratings_deidentified.csv")
CATEGORIES = ("valid", "invalid", "uncertain")

# Values as stated in the manuscript (Expert validation subsection / Table).
EXPECTED = {
    "fleiss_kappa": 0.705,
    "unanimous_valid": 14,
    "majority_valid": 16,
    "any_invalid": 0,
    "majority_uncertain": 4,
}


def load_matrix(path: Path) -> list[list[int]]:
    """Read the de-identified count matrix; each row is [valid, invalid, uncertain]."""
    matrix: list[list[int]] = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.reader(f):
            if not row or row[0].startswith("#") or row[0] == "archetype_id":
                continue
            matrix.append([int(row[1]), int(row[2]), int(row[3])])
    return matrix


def fleiss_kappa(matrix: list[list[int]]) -> float:
    """Fleiss' kappa for a (N items x k categories) count matrix."""
    n_items = len(matrix)
    n_raters = sum(matrix[0])
    if n_items == 0 or n_raters <= 1:
        return 0.0

    p_cat = [sum(row[j] for row in matrix) / (n_items * n_raters) for j in range(len(CATEGORIES))]
    p_bar_e = sum(p * p for p in p_cat)
    p_i = [(sum(r * r for r in row) - n_raters) / (n_raters * (n_raters - 1)) for row in matrix]
    p_bar = sum(p_i) / n_items
    if p_bar_e == 1.0:
        return 1.0
    return round((p_bar - p_bar_e) / (1.0 - p_bar_e), 4)


def interpret(k: float) -> str:
    """Landis & Koch (1977) interpretation."""
    bounds = [(0.0, "Poor"), (0.21, "Slight"), (0.41, "Fair"),
              (0.61, "Moderate"), (0.81, "Substantial")]
    for hi, label in bounds:
        if k < hi:
            return label
    return "Almost perfect"


def main() -> int:
    if not CSV_PATH.exists():
        print(f"ERROR: {CSV_PATH} not found (run from the repo root).", file=sys.stderr)
        return 2

    matrix = load_matrix(CSV_PATH)
    n_raters = sum(matrix[0])
    kappa = fleiss_kappa(matrix)

    unanimous_valid = sum(1 for r in matrix if r[0] == n_raters)
    majority_valid = sum(1 for r in matrix if r[0] > n_raters / 2)
    any_invalid = sum(1 for r in matrix if r[1] > 0)
    majority_uncertain = sum(1 for r in matrix if r[2] > n_raters / 2)

    got = {
        "fleiss_kappa": round(kappa, 3),
        "unanimous_valid": unanimous_valid,
        "majority_valid": majority_valid,
        "any_invalid": any_invalid,
        "majority_uncertain": majority_uncertain,
    }

    print(f"Items (archetypes): {len(matrix)}   Raters: {n_raters}")
    print(f"Fleiss' kappa     : {kappa} ({interpret(kappa)})")
    print(f"Unanimous valid   : {unanimous_valid}/20")
    print(f"Majority valid    : {majority_valid}/20")
    print(f"Majority uncertain: {majority_uncertain}/20")
    print(f"Any invalid       : {any_invalid}/20")

    ok = all(got[k] == EXPECTED[k] for k in EXPECTED)
    print("\n" + ("PASS: reproduces manuscript values." if ok
                  else f"FAIL: got {got}, expected {EXPECTED}"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
