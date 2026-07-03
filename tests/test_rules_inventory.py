"""Tests for scripts.build_rules_inventory against real rules.pkl."""

import csv
import sys
from pathlib import Path

import pytest

# Make scripts/ importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

RULES_PKL = Path("vendor/core/resources/cache/rules.pkl")
EXPECTED_COLUMNS = [
    "core_id", "description", "sensitivity", "executability", "rule_type",
    "status", "oncology_domains", "domains_include", "domains_exclude",
    "classes_include", "standards", "use_case", "n_conditions", "n_actions",
]


@pytest.mark.skipif(not RULES_PKL.exists(), reason="rules.pkl not present")
def test_inventory_builds(tmp_path: Path) -> None:
    """Build inventory from real rules.pkl and validate output."""
    from scripts.build_rules_inventory import build_inventory

    out = tmp_path / "rules_inventory.csv"
    n = build_inventory(RULES_PKL, out)

    assert n >= 120, f"Expected >=120 rows, got {n}"
    assert n <= 200, f"Expected <=200 rows, got {n}"

    with open(out, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == EXPECTED_COLUMNS
        rows = list(reader)

    assert len(rows) == n
    assert all(r["oncology_domains"] for r in rows), "Every row must have oncology_domains"
