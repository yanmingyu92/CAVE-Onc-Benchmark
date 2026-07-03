"""Compute formal statistical metrics from Track B results per the SAP.

Outputs:
  - McNemar's exact test (CAVE vs CORE)
  - Exact binomial 95% CI (Clopper-Pearson)
  - Per-archetype detection summary
  - Updated P8-style metrics
"""
from __future__ import annotations

import json
import math
from pathlib import Path

# -- Exact binomial CI (Clopper-Pearson) ------------------------------------

def _beta_ppf(a: float, b: float, p: float) -> float:
    """Approximate inverse beta CDF using scipy if available, else fallback."""
    try:
        from scipy.stats import beta
        return beta.ppf(p, a, b)
    except ImportError:
        # Rough Wilson interval fallback
        n = a + b - 2
        k = a - 1
        phat = k / n if n > 0 else 0
        z = 1.96
        denom = 1 + z**2 / n
        lo = (phat + z**2 / (2 * n) - z * math.sqrt(phat * (1 - phat) / n + z**2 / (4 * n**2))) / denom
        hi = (phat + z**2 / (2 * n) + z * math.sqrt(phat * (1 - phat) / n + z**2 / (4 * n**2))) / denom
        return lo if p < 0.5 else hi


def clopper_pearson_ci(k: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    """Exact (Clopper-Pearson) binomial CI."""
    if k == 0:
        lo = 0.0
    else:
        lo = _beta_ppf(k, n - k + 1, alpha / 2)
    if k == n:
        hi = 1.0
    else:
        hi = _beta_ppf(k + 1, n - k, 1 - alpha / 2)
    return round(lo, 4), round(hi, 4)


# -- McNemar's exact test --------------------------------------------------

def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact binomial p-value for McNemar's test.
    
    b = CAVE detects, baseline misses
    c = CAVE misses, baseline detects
    """
    if b + c == 0:
        return 1.0
    try:
        from scipy.stats import binom_test
        return round(binom_test(b, b + c, 0.5), 6)
    except ImportError:
        # Fallback: exact binomial
        n = b + c
        k = min(b, c)
        # P(X <= k) * 2 for two-sided
        from math import comb
        p = sum(comb(n, i) * 0.5**n for i in range(k + 1)) * 2
        return round(min(p, 1.0), 6)


def compute_metrics(track_b_path: Path) -> dict:
    """Compute all SAP-specified metrics from Track B results."""
    data = json.loads(track_b_path.read_text(encoding="utf-8"))
    archetypes = data["archetypes"]
    n = len(archetypes)
    
    # Detection counts
    cave_detected = sum(1 for a in archetypes if a["detected"])
    l1_detected = sum(1 for a in archetypes if a.get("detection_source") in ("L1", "both"))
    l3_detected = sum(1 for a in archetypes if a.get("detection_source") in ("L3", "both"))
    # Empirical CORE baseline: load the real CORE v0.15 run on the injected corpus
    # (eval/core_p21_benchmark.json) rather than assuming 0/20. CORE detects 8/20 —
    # all among the ten CORE-seeded structural archetypes (A08-A17) — and 0/10 of the
    # non-CORE cross-domain RECIST contradictions. See docs/item_core_p21_findings.md.
    core_bench_path = track_b_path.parent / "core_p21_benchmark.json"
    core_bench = json.loads(core_bench_path.read_text(encoding="utf-8"))
    core_detect = {a["archetype"]: bool(a["core_detects_contradiction"])
                   for a in core_bench["per_archetype"]}
    core_category = {a["archetype"]: a.get("category")
                     for a in core_bench["per_archetype"]}
    cave_detect = {a["archetype_id"]: bool(a["detected"]) for a in archetypes}
    core_detected = sum(1 for v in core_detect.values() if v)

    # McNemar's exact test: CAVE vs CORE over all 20 archetypes (paired per-archetype).
    # b = CAVE detects & CORE misses; c = CORE detects & CAVE misses.
    b = sum(1 for aid in cave_detect if cave_detect[aid] and not core_detect.get(aid, False))
    c = sum(1 for aid in cave_detect if not cave_detect[aid] and core_detect.get(aid, False))
    mcnemar_p = mcnemar_exact(b, c)

    # Non-CORE cross-domain subset (the expressiveness-relevant class): CORE 0/10 vs CAVE.
    noncore_ids = [aid for aid, cat in core_category.items() if cat == "noncore_crossdomain"]
    nc_core_detected = sum(1 for aid in noncore_ids if core_detect.get(aid, False))
    nc_cave_detected = sum(1 for aid in noncore_ids if cave_detect.get(aid, False))
    nc_b = sum(1 for aid in noncore_ids if cave_detect.get(aid, False) and not core_detect.get(aid, False))
    nc_c = sum(1 for aid in noncore_ids if not cave_detect.get(aid, False) and core_detect.get(aid, False))
    mcnemar_noncore_p = mcnemar_exact(nc_b, nc_c)

    # Second empirical baseline: the branded Pinnacle 21 Community FDA production engine
    # (eval/p21_fda_benchmark.json). Both CORE and the FDA engine are domain-scoped, so the
    # FDA engine also detects 0/10 of the non-CORE class. See scripts/run_p21_fda_baseline.py.
    p21_path = track_b_path.parent / "p21_fda_benchmark.json"
    p21_detected = p21_b = p21_c = p21_nc_detected = None
    mcnemar_p21_p = mcnemar_p21_noncore_p = None
    if p21_path.is_file():
        p21_bench = json.loads(p21_path.read_text(encoding="utf-8"))
        p21_detect = {a["archetype"]: bool(a["p21_detects_contradiction"])
                      for a in p21_bench["per_archetype"]}
        p21_detected = sum(1 for v in p21_detect.values() if v)
        p21_b = sum(1 for aid in cave_detect if cave_detect[aid] and not p21_detect.get(aid, False))
        p21_c = sum(1 for aid in cave_detect if not cave_detect[aid] and p21_detect.get(aid, False))
        mcnemar_p21_p = mcnemar_exact(p21_b, p21_c)
        p21_nc_detected = sum(1 for aid in noncore_ids if p21_detect.get(aid, False))
        p21_nc_b = sum(1 for aid in noncore_ids if cave_detect.get(aid, False) and not p21_detect.get(aid, False))
        p21_nc_c = sum(1 for aid in noncore_ids if not cave_detect.get(aid, False) and p21_detect.get(aid, False))
        mcnemar_p21_noncore_p = mcnemar_exact(p21_nc_b, p21_nc_c)
    
    # McNemar's test: L1+L3 vs L1-only
    l3_only = sum(1 for a in archetypes if a.get("detection_source") == "L3")
    l1_missed_but_l3_caught = l3_only  # b for ablation
    mcnemar_ablation_p = mcnemar_exact(l1_missed_but_l3_caught, 0)
    
    # Exact binomial CI for detection rate
    ci_lo, ci_hi = clopper_pearson_ci(cave_detected, n)
    
    # Detection rate
    rate = cave_detected / n
    
    # Precision/Recall/F1 (binary per-archetype: each archetype is one test case)
    tp = cave_detected
    fn = n - cave_detected
    fp_flags = sum(abs(a["flag_delta_vs_clean"]) for a in archetypes 
                   if a["detected"] and a["flag_delta_vs_clean"] > 1)  # excess flags beyond detection
    precision = tp / (tp + 0) if tp > 0 else 0  # no FP at archetype level
    recall = tp / n
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    
    # Per-archetype summary
    per_arch = {}
    for a in archetypes:
        aid = a["archetype_id"]
        det = a["detected"]
        per_arch[aid] = {
            "detected": det,
            "source": a.get("detection_source", ""),
            "delta": a["flag_delta_vs_clean"],
            "l3_traces": a.get("l3_flag_count", 0),
        }
    
    # Undetected analysis
    undetected = [a["archetype_id"] for a in archetypes if not a["detected"]]
    
    metrics = {
        "track_b_detection": {
            "n_archetypes": n,
            "cave_detected": cave_detected,
            "detection_rate": round(rate, 3),
            "detection_rate_pct": f"{rate*100:.0f}%",
            "exact_binomial_95ci": [ci_lo, ci_hi],
            "exact_binomial_95ci_pct": f"[{ci_lo*100:.1f}%, {ci_hi*100:.1f}%]",
            "l1_detected": l1_detected,
            "l3_detected": l3_detected,
            "l3_only": l3_only,
            "undetected": undetected,
        },
        "core_baseline": {
            "source": "eval/core_p21_benchmark.json (real CORE v0.15 run, SDTMIG 3.4)",
            "core_detected_all": core_detected,
            "core_detected_all_str": f"{core_detected}/{n}",
            "note": "All CORE detections fall among the ten CORE-seeded structural "
                    "archetypes (A08-A17); CORE detects 0/10 of the non-CORE cross-domain class.",
        },
        "mcnemar_cave_vs_core": {
            "scope": "all_20_archetypes",
            "cave_only_catches": b,
            "core_only_catches": c,
            "discordant_pairs": b + c,
            "p_value": mcnemar_p,
            "significant_at_005": mcnemar_p < 0.05,
            "interpretation": f"CAVE {cave_detected}/{n} vs CORE {core_detected}/{n}; "
                            f"{b + c} discordant pairs (b={b}, c={c}); "
                            f"McNemar's exact p={mcnemar_p:.6f}"
        },
        "mcnemar_cave_vs_core_noncore": {
            "scope": "noncore_crossdomain_subset",
            "n": len(noncore_ids),
            "cave_detected": nc_cave_detected,
            "core_detected": nc_core_detected,
            "cave_only_catches": nc_b,
            "core_only_catches": nc_c,
            "discordant_pairs": nc_b + nc_c,
            "p_value": mcnemar_noncore_p,
            "significant_at_005": mcnemar_noncore_p < 0.05,
            "interpretation": f"On the {len(noncore_ids)} non-CORE cross-domain archetypes, "
                            f"CAVE {nc_cave_detected}/{len(noncore_ids)} vs CORE {nc_core_detected}/{len(noncore_ids)}; "
                            f"McNemar's exact p={mcnemar_noncore_p:.6f}"
        },
        "p21_fda_baseline": None if p21_detected is None else {
            "source": "eval/p21_fda_benchmark.json (branded Pinnacle 21 Community FDA engine, FDA 2405.2, SDTMIG 3.4)",
            "p21_detected_all": p21_detected,
            "p21_detected_all_str": f"{p21_detected}/{n}",
            "p21_detected_noncore": p21_nc_detected,
            "note": "The industry-standard FDA production engine, like the open CORE engine, "
                    "detects 0/10 of the non-CORE cross-domain class; its detections are all "
                    "CORE-seeded structural checks.",
        },
        "mcnemar_cave_vs_p21_fda": None if p21_detected is None else {
            "scope": "all_20_archetypes",
            "cave_only_catches": p21_b,
            "p21_only_catches": p21_c,
            "discordant_pairs": p21_b + p21_c,
            "p_value": mcnemar_p21_p,
            "significant_at_005": mcnemar_p21_p < 0.05,
            "interpretation": f"CAVE {cave_detected}/{n} vs P21 FDA {p21_detected}/{n}; "
                            f"{p21_b + p21_c} discordant; McNemar's exact p={mcnemar_p21_p:.6f}",
        },
        "mcnemar_cave_vs_p21_fda_noncore": None if p21_detected is None else {
            "scope": "noncore_crossdomain_subset",
            "n": len(noncore_ids),
            "cave_detected": nc_cave_detected,
            "p21_detected": p21_nc_detected,
            "p_value": mcnemar_p21_noncore_p,
            "significant_at_005": mcnemar_p21_noncore_p < 0.05,
            "interpretation": f"On the {len(noncore_ids)} non-CORE archetypes, CAVE "
                            f"{nc_cave_detected}/{len(noncore_ids)} vs P21 FDA {p21_nc_detected}/{len(noncore_ids)}; "
                            f"McNemar's exact p={mcnemar_p21_noncore_p:.6f}",
        },
        "mcnemar_ablation_l1_vs_cave": {
            "l3_adds": l3_only,
            "l1_only_catches_cave_misses": 0,
            "p_value": mcnemar_ablation_p,
        },
        "detection_metrics": {
            "true_positives": tp,
            "false_negatives": fn,
            "archetype_precision": round(precision, 3),
            "archetype_recall": round(recall, 3),
            "archetype_f1": round(f1, 3),
        },
        "bootstrap_ci": _bootstrap_cis(archetypes),
        "per_archetype": per_arch,
    }
    return metrics


def _bootstrap_cis(archetypes: list[dict], n_boot: int = 1000, seed: int = 42) -> dict:
    """Bootstrap 95% CIs for detection rate and F1 (SAP requirement)."""
    import random
    rng = random.Random(seed)
    n = len(archetypes)
    detected = [1 if a["detected"] else 0 for a in archetypes]
    
    boot_rates = []
    boot_f1s = []
    for _ in range(n_boot):
        sample = rng.choices(detected, k=n)
        tp = sum(sample)
        fn = n - tp
        rate = tp / n
        prec = 1.0 if tp > 0 else 0.0  # no FP at archetype level
        rec = tp / n
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
        boot_rates.append(rate)
        boot_f1s.append(f1)
    
    boot_rates.sort()
    boot_f1s.sort()
    lo_idx = int(n_boot * 0.025)
    hi_idx = int(n_boot * 0.975) - 1
    
    return {
        "n_bootstrap": n_boot,
        "seed": seed,
        "detection_rate_95ci": [round(boot_rates[lo_idx], 4), round(boot_rates[hi_idx], 4)],
        "detection_rate_95ci_pct": f"[{boot_rates[lo_idx]*100:.1f}%, {boot_rates[hi_idx]*100:.1f}%]",
        "f1_95ci": [round(boot_f1s[lo_idx], 4), round(boot_f1s[hi_idx], 4)],
        "f1_95ci_pct": f"[{boot_f1s[lo_idx]*100:.1f}%, {boot_f1s[hi_idx]*100:.1f}%]",
    }


if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    tb_path = root / "eval" / "track_b_results.json"
    metrics = compute_metrics(tb_path)
    
    out_path = root / "eval" / "statistical_metrics.json"
    out_path.write_text(json.dumps(metrics, indent=2, default=str), encoding="utf-8")
    
    # Pretty print
    det = metrics["track_b_detection"]
    print(f"\n{'='*60}")
    print(f"CAVE-Onc Statistical Metrics (SAP)")
    print(f"{'='*60}")
    print(f"Detection: {det['cave_detected']}/{det['n_archetypes']} "
          f"({det['detection_rate_pct']})")
    print(f"  L1: {det['l1_detected']}, L3: {det['l3_detected']} "
          f"(L3-only: {det['l3_only']})")
    print(f"  95% CI (Clopper-Pearson): {det['exact_binomial_95ci_pct']}")
    if det["undetected"]:
        print(f"  Undetected: {det['undetected']}")
    
    mcn = metrics["mcnemar_cave_vs_core"]
    print(f"\nMcNemar's test (CAVE vs CORE):")
    print(f"  Discordant pairs: {mcn['discordant_pairs']}")
    print(f"  p-value: {mcn['p_value']:.6f}")
    print(f"  Significant at α=0.05: {mcn['significant_at_005']}")
    
    dm = metrics["detection_metrics"]
    print(f"\nDetection metrics:")
    print(f"  TP={dm['true_positives']}, FN={dm['false_negatives']}")
    print(f"  Precision={dm['archetype_precision']}, "
          f"Recall={dm['archetype_recall']}, F1={dm['archetype_f1']}")
    
    bs = metrics["bootstrap_ci"]
    print(f"\nBootstrap 95% CIs (n={bs['n_bootstrap']}, seed={bs['seed']}):")
    print(f"  Detection rate: {bs['detection_rate_95ci_pct']}")
    print(f"  F1: {bs['f1_95ci_pct']}")
    print(f"{'='*60}")
    print(f"\nSaved to: {out_path}")
