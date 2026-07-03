"""Track A regression analysis — B3 L1-only vs B2 CORE on pilot1.

Runs both baselines, computes Jaccard similarity on (USUBJID, rule_id)
tuples scoped to oncology domains, per-rule recall, and saves results
to ``eval/track_a_results.json``.
"""

from __future__ import annotations

import json
import logging
import sys
from collections import Counter
from pathlib import Path

from eval.baselines import b2_core, b3_l1_only
from eval.flag_schema import FlagSet

logger = logging.getLogger(__name__)

_DATA_DIR = Path("data/pilot1")
_OUTPUT = Path("eval/track_a_results.json")


def _flag_counts(fs: FlagSet) -> dict[str, int]:
    """Count flags per domain."""
    return dict(Counter(f.domain for f in fs.flags))


def _per_rule_detail(l1: FlagSet, core: FlagSet) -> dict:
    """Per-rule recall of L1 against CORE gold."""
    recall = l1.per_rule_recall(core)
    l1_by_rule: dict[str, int] = Counter(f.rule_id for f in l1.flags)
    core_by_rule: dict[str, int] = Counter(f.rule_id for f in core.flags)
    table: dict[str, dict] = {}
    for rule in sorted(core_by_rule):
        table[rule] = {
            "core_count": core_by_rule.get(rule, 0),
            "l1_count": l1_by_rule.get(rule, 0),
            "recall": round(recall.get(rule, 0.0), 4),
        }
    return table


def run_analysis(data_dir: Path = _DATA_DIR) -> dict:
    """Execute Track A analysis and return results dict."""
    logger.info("Running B3 L1-only on %s", data_dir)
    l1_flags = b3_l1_only.run(data_dir)

    logger.info("Running B2 CORE on %s", data_dir)
    core_flags = b2_core.run(data_dir)

    j = l1_flags.jaccard(core_flags)
    recall_detail = _per_rule_detail(l1_flags, core_flags)

    results = {
        "track": "A",
        "data_dir": str(data_dir),
        "jaccard": round(j, 4),
        "pass_threshold": j >= 0.95,
        "l1_flags": len(l1_flags),
        "core_flags": len(core_flags),
        "l1_by_domain": _flag_counts(l1_flags),
        "core_by_domain": _flag_counts(core_flags),
        "overlap": len(l1_flags._pairs() & core_flags._pairs()),
        "per_rule_recall": recall_detail,
        "unique_core_rules": len({f.rule_id for f in core_flags.flags}),
    }
    return results


def _print_summary(results: dict) -> None:
    """Print summary table to stdout."""
    print("\n=== Track A: L1 vs CORE Regression ===")
    print(f"  Jaccard:        {results['jaccard']:.4f}  "
          f"({'PASS' if results['pass_threshold'] else 'FAIL'})")
    print(f"  L1 flags:       {results['l1_flags']}")
    print(f"  CORE flags:     {results['core_flags']}")
    print(f"  Overlap pairs:  {results['overlap']}")
    print(f"  CORE rules:     {results['unique_core_rules']}")
    print("\n  Per-rule recall:")
    for rule, info in results["per_rule_recall"].items():
        status = "OK" if info["recall"] >= 0.95 else "LOW"
        print(f"    {rule:16s}  CORE={info['core_count']:4d}  "
              f"L1={info['l1_count']:4d}  recall={info['recall']:.4f}  {status}")
    print()


def main() -> None:
    """CLI entry point."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    data_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else _DATA_DIR
    results = run_analysis(data_dir)
    _print_summary(results)
    _OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    _OUTPUT.write_text(json.dumps(results, indent=2), encoding="utf-8")
    logger.info("Results saved to %s", _OUTPUT)


if __name__ == "__main__":
    main()
