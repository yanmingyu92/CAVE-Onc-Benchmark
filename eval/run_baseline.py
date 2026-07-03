"""Evaluation dispatcher — runs registered baselines and saves results.

Usage::

    from eval.run_baseline import run_evaluation
    results = run_evaluation(
        data_dir=Path("data/pilot1"),
        output_dir=Path("eval/results"),
        baselines=["B3_L1", "CAVE"],
    )
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Callable

from eval.baselines import b1_p21, b2_core, b3_l1_only, b_cave
from eval.flag_schema import FlagSet
from eval.metrics import jaccard, track_a_report, track_b_report

logger = logging.getLogger(__name__)

# -- Registry ----------------------------------------------------------------

BASELINES: dict[str, Callable[[Path], FlagSet]] = {
    "B1_P21": b1_p21.run,
    "B2_CORE": b2_core.run,
    "B3_L1": b3_l1_only.run,
    "CAVE": b_cave.run,
}


# -- Core dispatcher ---------------------------------------------------------

def run_evaluation(
    data_dir: Path,
    output_dir: Path,
    baselines: list[str] | None = None,
    injected: bool = False,
) -> dict[str, FlagSet]:
    """Dispatch *data_dir* through each registered baseline.

    Parameters
    ----------
    data_dir:
        Directory containing XPT files (or injected copies).
    output_dir:
        Where per-baseline JSON and metrics.json are written.
    baselines:
        Subset of ``BASELINES`` keys to run.  *None* → all non-stub baselines.
    injected:
        If *True*, tag output directory with ``_injected`` suffix.

    Returns
    -------
    dict mapping baseline name → FlagSet.
    """
    output_dir = Path(output_dir)
    if injected:
        output_dir = output_dir.with_name(output_dir.name + "_injected")
    output_dir.mkdir(parents=True, exist_ok=True)

    selected = baselines or [k for k in BASELINES if k in ("B3_L1", "CAVE")]
    results: dict[str, FlagSet] = {}

    for name in selected:
        runner = BASELINES.get(name)
        if runner is None:
            logger.warning("Unknown baseline: %s — skipping", name)
            continue
        try:
            flagset = runner(Path(data_dir))
            results[name] = flagset
            _save_flags(output_dir / f"{name}.json", flagset)
            logger.info("%s: %d flags", name, len(flagset))
        except NotImplementedError as exc:
            logger.info("%s: stub — %s", name, exc)
        except Exception as exc:
            logger.error("%s: failed — %s", name, exc)

    metrics = _compute_metrics(results)
    _save_metrics(output_dir / "metrics.json", metrics)
    return results


# -- Metrics computation -----------------------------------------------------

def _compute_metrics(results: dict[str, FlagSet]) -> dict:
    """Build Track A and Track B reports from available baselines."""
    metrics: dict = {"baselines_run": list(results.keys())}

    if "B3_L1" in results and "B2_CORE" in results:
        metrics["track_a"] = track_a_report(results["B3_L1"], results["B2_CORE"])
    elif "B3_L1" in results:
        metrics["track_a_partial"] = {
            "note": "No B2_CORE gold standard available",
            "b3_l1_flag_count": len(results["B3_L1"]),
        }

    if "CAVE" in results and "B3_L1" in results:
        metrics["track_b"] = track_b_report(results["CAVE"], results["B3_L1"])
    elif "CAVE" in results and "B2_CORE" in results:
        metrics["track_b"] = track_b_report(results["CAVE"], results["B2_CORE"])

    # Pairwise Jaccard matrix
    names = list(results.keys())
    matrix: dict[str, dict[str, float]] = {}
    for i, a in enumerate(names):
        matrix[a] = {}
        for b in names:
            matrix[a][b] = round(jaccard(results[a], results[b]), 4)
    metrics["jaccard_matrix"] = matrix
    return metrics


# -- I/O helpers -------------------------------------------------------------

def _save_flags(path: Path, flagset: FlagSet) -> None:
    data = [f.model_dump() for f in flagset.flags]
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


def _save_metrics(path: Path, metrics: dict) -> None:
    path.write_text(json.dumps(metrics, indent=2, default=str), encoding="utf-8")


# -- CLI entry point ---------------------------------------------------------

def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Run evaluation baselines")
    ap.add_argument("--data-dir", required=True, type=Path)
    ap.add_argument("--output-dir", required=True, type=Path)
    ap.add_argument("--baselines", nargs="+", default=None)
    ap.add_argument("--injected", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO)
    run_evaluation(args.data_dir, args.output_dir, args.baselines, args.injected)


if __name__ == "__main__":
    main()
