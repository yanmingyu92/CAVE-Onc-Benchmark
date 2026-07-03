"""P8 extended benchmark — enriched Track B, ablation, and timing analysis.

Re-runs all 20 archetypes with RS data enriched with NTOVRLRESP / NEWLEC
test codes so A19 L3 detection can fire.  Produces an ablation table
(L1-only vs L1+L3) and wall-clock timing per configuration.

Outputs:
    eval/p8_benchmark_results.json
"""
from __future__ import annotations

import json
import logging
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from bench.mutations import MUTATIONS
from scripts.track_b_analysis import _frames_to_graph, _run_l1, _run_l3

logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

RESULTS_PATH = _ROOT / "eval" / "p8_benchmark_results.json"
TRACK_A_PATH = _ROOT / "eval" / "track_a_results.json"
ARCHETYPES = sorted(MUTATIONS.keys())


# -- RS enrichment -------------------------------------------------------------

def enrich_rs(frames: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Add NTOVRLRESP and NEWLEC rows to RS for each USUBJID."""
    rs = frames.get("RS")
    if rs is None or rs.empty:
        return frames
    extra_rows: list[pd.Series] = []
    for usubjid in rs["USUBJID"].unique():
        subj_rs = rs[rs["USUBJID"] == usubjid]
        base_row = subj_rs.iloc[0].copy()
        for testcd, val in [("NTOVRLRESP", "NON-CR/NON-PD"), ("NEWLEC", "N")]:
            row = base_row.copy()
            row["RSTESTCD"] = testcd
            row["RSORRES"] = val
            row["RSSTRESC"] = val
            row["RSSEQ"] = rs["RSSEQ"].max() + 1 + len(extra_rows)
            extra_rows.append(row)
    if extra_rows:
        frames["RS"] = pd.concat(
            [rs, pd.DataFrame(extra_rows)], ignore_index=True,
        )
    return frames


# -- Per-archetype result ------------------------------------------------------

@dataclass
class BenchResult:
    """Detection + timing results for one archetype under enrichment."""
    archetype_id: str
    l1_detected: bool = False
    l3_detected: bool = False
    cave_detected: bool = False
    l1_flag_delta: int = 0
    l3_traces: int = 0
    detection_source: str = ""
    l1_time_s: float = 0.0
    l3_time_s: float = 0.0


def _run_archetype(
    aid: str,
    clean_frames: dict[str, pd.DataFrame],
    clean_l1: int,
) -> BenchResult:
    """Inject *aid*, enrich RS, measure L1 and L3 with timing."""
    frames = {k: v.copy() for k, v in clean_frames.items()}

    # Apply archetype mutation FIRST, then enrich RS.
    # Order matters: mutate_A19 sets RSORRES="CR" on ALL rows at a
    # given visit/subject — if enrichment happens first, the extra
    # NTOVRLRESP/NEWLEC rows get overwritten too, breaking L3 detection.
    frames, _ = MUTATIONS[aid](frames)

    # Enrich AFTER mutation so NTOVRLRESP/NEWLEC rows keep their values
    frames = enrich_rs(frames)

    graph = _frames_to_graph(frames)
    result = BenchResult(archetype_id=aid)

    # L1 timing
    t0 = time.perf_counter()
    l1_flags = _run_l1(graph)
    result.l1_time_s = round(time.perf_counter() - t0, 3)
    result.l1_flag_delta = l1_flags - clean_l1
    result.l1_detected = result.l1_flag_delta != 0

    # L3 timing
    t0 = time.perf_counter()
    traces = _run_l3(graph)
    result.l3_time_s = round(time.perf_counter() - t0, 3)
    result.l3_traces = len(traces)
    result.l3_detected = result.l3_traces > 0

    # Combined
    l1d, l3d = result.l1_detected, result.l3_detected
    if l1d and l3d:
        result.detection_source = "both"
    elif l3d:
        result.detection_source = "L3"
    elif l1d:
        result.detection_source = "L1"
    result.cave_detected = l1d or l3d
    return result


# -- Main benchmark ------------------------------------------------------------

def run_benchmark(output_path: Path = RESULTS_PATH) -> dict:
    """Run full P8 benchmark: enriched Track B + ablation + timing."""
    from bench.injector import Injector

    # Clean baseline (with enrichment applied for fair comparison)
    raw_frames = Injector(output_dir="bench/output_p8")._load_all()
    enriched_clean = enrich_rs({k: v.copy() for k, v in raw_frames.items()})
    clean_l1 = _run_l1(_frames_to_graph(enriched_clean))
    logger.info("Enriched clean baseline L1: %d", clean_l1)

    # Run each archetype
    results: list[BenchResult] = []
    for aid in ARCHETYPES:
        r = _run_archetype(aid, raw_frames, clean_l1)
        results.append(r)
        logger.info(
            "%s: l1=%s l3=%s cave=%s src=%s dL1=%+d L3t=%d "
            "(%.3fs / %.3fs)",
            aid, r.l1_detected, r.l3_detected, r.cave_detected,
            r.detection_source, r.l1_flag_delta, r.l3_traces,
            r.l1_time_s, r.l3_time_s,
        )

    # -- Aggregation -----------------------------------------------------------
    l1_det = sum(1 for r in results if r.l1_detected)
    l3_det = sum(1 for r in results if r.l3_detected)
    cave_det = sum(1 for r in results if r.cave_detected)
    l3_contribution = [r.archetype_id for r in results if r.l3_detected]
    cave_only = [
        r.archetype_id for r in results
        if r.detection_source in ("L3", "both")
    ]

    mean_l1 = sum(r.l1_time_s for r in results) / len(results)
    mean_l3 = sum(r.l3_time_s for r in results) / len(results)
    mean_full = mean_l1 + mean_l3

    # Clean baseline L1 timing (single run)
    t0 = time.perf_counter()
    _run_l1(_frames_to_graph(enriched_clean))
    bl_l1_s = round(time.perf_counter() - t0, 3)
    ratio = round(mean_full / bl_l1_s, 2) if bl_l1_s > 0 else 0.0

    # Track A summary
    track_a: dict = {}
    if TRACK_A_PATH.exists():
        track_a = json.loads(TRACK_A_PATH.read_text(encoding="utf-8"))

    report = {
        "track_a": track_a,
        "track_b_enriched": {
            "archetypes": [asdict(r) for r in results],
            "summary": {
                "l1_detection_rate": f"{l1_det}/20",
                "l3_detection_rate": f"{l3_det}/20",
                "cave_detection_rate": f"{cave_det}/20",
                "cave_only_catches": cave_only,
                "mean_l1_time_s": round(mean_l1, 3),
                "mean_l3_time_s": round(mean_l3, 3),
            },
        },
        "ablation": {
            "l1_only_detections": l1_det,
            "l1_plus_l3_detections": cave_det,
            "l3_contribution": l3_contribution,
        },
        "timing": {
            "clean_baseline_l1_s": bl_l1_s,
            "mean_per_archetype_l1_s": round(mean_l1, 3),
            "mean_per_archetype_l3_s": round(mean_l3, 3),
            "mean_full_pipeline_s": round(mean_full, 3),
            "cave_to_baseline_ratio": ratio,
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8",
    )
    _print_table(report)
    return report


def _print_table(report: dict) -> None:
    """Print formatted summary table to stdout."""
    print("\n" + "=" * 72)
    print("P8 Extended Benchmark — Enriched Track B")
    print("=" * 72)
    print(
        f"{'ID':<5} {'L1':>5} {'L3':>5} {'CAVE':>6} "
        f"{'Source':<6} {'dL1':>5} {'L3t':>4} "
        f"{'L1(s)':>7} {'L3(s)':>7}"
    )
    print("-" * 72)
    for a in report["track_b_enriched"]["archetypes"]:
        print(
            f"{a['archetype_id']:<5} "
            f"{'Y' if a['l1_detected'] else '.':>5} "
            f"{'Y' if a['l3_detected'] else '.':>5} "
            f"{'Y' if a['cave_detected'] else '.':>6} "
            f"{a['detection_source'] or '-':<6} "
            f"{a['l1_flag_delta']:+5d} "
            f"{a['l3_traces']:>4d} "
            f"{a['l1_time_s']:>7.3f} "
            f"{a['l3_time_s']:>7.3f}"
        )
    print("-" * 72)
    s = report["track_b_enriched"]["summary"]
    t = report["timing"]
    print(
        f"L1={s['l1_detection_rate']}  L3={s['l3_detection_rate']}  "
        f"CAVE={s['cave_detection_rate']}  "
        f"L3-adds={report['ablation']['l3_contribution']}"
    )
    print(
        f"Timing: L1={t['mean_per_archetype_l1_s']:.3f}s  "
        f"L3={t['mean_per_archetype_l3_s']:.3f}s  "
        f"Full={t['mean_full_pipeline_s']:.3f}s  "
        f"Ratio={t['cave_to_baseline_ratio']:.2f}x"
    )
    print("=" * 72)


if __name__ == "__main__":
    run_benchmark()
