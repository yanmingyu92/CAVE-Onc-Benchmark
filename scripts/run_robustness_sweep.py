"""Gate 2b (robustness) — adversarial perturbation sweep on real mapped trials.

Deployment realism check for CAVE-Onc: a validator that is only sound on pristine
benchmark data is a proof of concept, not a tool. This sweep perturbs the REAL
mapped SDTM cohorts (data/real_sdtm/*) four ways and measures, single-pass (no
clean-baseline delta), that:

  (a) MISSINGNESS       — dropping random rows does not manufacture contradictions
                          (archetype-flag count stays bounded: specificity holds).
  (b) BROKEN RELREC/FK  — orphan foreign keys / dangling links do not crash the
                          engine and do not flood it with spurious flags.
  (c) UNDEFINED VISITS   — corrupted VISITNUM is caught by the visit-window shape
                          (A04) while the other shapes stay specific.
  (d) CO-OCCURRENCE      — several distinct contradictions injected into ONE subject
                          are detected together (recall does not collapse).

Each family reports a graceful-degradation curve rather than a single number.
Reproducible: a fixed seed drives every random choice.

Usage:
    python -m scripts.run_robustness_sweep --backend oxigraph \
        --out eval/robustness_sweep.json
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import time
from pathlib import Path

import pandas as pd
from rdflib import Graph

from bench.injector import Injector
from bench.mutations import MUTATIONS
from scripts.run_e2_real_data import (
    _build_graph, _detect, _subject_frames, not_applicable,
    CROSS_SUBJECT, A16_STRUCTURAL,
)

# Archetypes that cannot fire on a single-subject subgraph and so are excluded
# from the co-occurrence pool (they are not co-occurrence failures — they need
# the full cross-subject graph or an L3 agent path).
_PER_SUBJECT_EXCLUDED = set(CROSS_SUBJECT) | {A16_STRUCTURAL, "A19"}

# Archetypes whose mutations write or depend on the SAME field (the visit-level
# overall response RSORRES) are MUTUALLY EXCLUSIVE by construction: injecting two
# of them into one subject makes the later mutation overwrite the earlier one's
# precondition (e.g. RSORRES cannot be both PD and SD at one visit). A miss then
# reflects data clobbering, not detector interference. We therefore admit at most
# ONE representative of this group into a co-occurrence set so the measured recall
# isolates true detector interference. A04 shifts VISITNUM, which breaks the
# TR<->RS visit-equijoins the RS-response shapes rely on, so it is grouped here too.
_RS_RESPONSE_GROUP = {"A01", "A02", "A06", "A07", "A18", "A20", "A04"}


def _compatible_cooccurrence_set(detectable: list[str]) -> tuple[list[str], list[str]]:
    """Split a detectable set into a mutually-compatible co-occurrence set + excluded.

    Keeps every archetype with a disjoint write-target plus at most one member of
    the RS-overall-response group (whose members clobber each other's preconditions).
    """
    compatible = [a for a in detectable if a not in _RS_RESPONSE_GROUP]
    rs_group = [a for a in detectable if a in _RS_RESPONSE_GROUP]
    excluded = rs_group[1:]  # keep the first, exclude the rest as mutually exclusive
    if rs_group:
        compatible.append(rs_group[0])
    return sorted(compatible), sorted(excluded)

logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TRIALS = {"synta": "data/real_sdtm/synta", "ca012": "data/real_sdtm/ca012"}
MEASURE_DOMAINS = ("TR", "RS", "TU")


# -- helpers ------------------------------------------------------------------

def _archetype_flag_count(flags: set[tuple[str, str]]) -> int:
    """Count flags whose archetype id looks like a contradiction archetype (A..)."""
    return sum(1 for (a, _s) in flags if a.startswith("A"))


def _subset_subjects(frames: dict[str, pd.DataFrame], n: int, rng: random.Random
                     ) -> dict[str, pd.DataFrame]:
    """Restrict to n subjects (seeded) so the full-graph detects stay fast."""
    if "DM" not in frames or frames["DM"] is None:
        return frames
    subs = sorted(frames["DM"]["USUBJID"].unique())
    if len(subs) > n:
        subs = sorted(rng.sample(subs, n))
    keep = set(subs)
    out: dict[str, pd.DataFrame] = {}
    for dom, df in frames.items():
        if df is None or df.empty or "USUBJID" not in df.columns:
            out[dom] = df
        else:
            out[dom] = df[df["USUBJID"].isin(keep)].reset_index(drop=True)
    return out


def _drop_fraction(frames: dict[str, pd.DataFrame], domains, p: float,
                   rng: random.Random) -> dict[str, pd.DataFrame]:
    """Return a copy of frames with fraction p of rows dropped from each domain."""
    out = {k: (v.copy() if v is not None else v) for k, v in frames.items()}
    for dom in domains:
        df = out.get(dom)
        if df is None or df.empty or p <= 0:
            continue
        n_drop = int(round(len(df) * p))
        if n_drop <= 0:
            continue
        drop_idx = rng.sample(list(df.index), min(n_drop, len(df)))
        out[dom] = df.drop(index=drop_idx).reset_index(drop=True)
    return out


# -- experiment (a): missingness ---------------------------------------------

def exp_missingness(frames, backend, rng, levels=(0.0, 0.1, 0.25, 0.5)) -> list[dict]:
    """Specificity under random row deletion — flags must not explode."""
    curve: list[dict] = []
    for p in levels:
        pert = _drop_fraction(frames, MEASURE_DOMAINS, p, rng)
        t = time.time()
        crashed, n_flags = False, -1
        try:
            flags, _ = _detect(_build_graph(pert), backend)
            n_flags = _archetype_flag_count(flags)
        except Exception as exc:  # noqa: BLE001
            crashed = True
            logger.warning("missingness p=%.2f crashed: %s", p, exc)
        curve.append({"missing_fraction": p, "archetype_flags": n_flags,
                      "crashed": crashed, "seconds": round(time.time() - t, 1)})
        logger.info("  missingness p=%.2f -> flags=%d crashed=%s", p, n_flags, crashed)
    base = curve[0]["archetype_flags"]
    for c in curve:
        # None (not a number) when either endpoint crashed, so a crash cannot masquerade
        # as a flag decrease in the summary's max-increase computation.
        c["delta_vs_clean"] = (
            c["archetype_flags"] - base
            if (base >= 0 and c["archetype_flags"] >= 0) else None)
    return curve


# -- experiment (b): broken RELREC / orphan foreign keys ---------------------

def exp_orphan_fk(frames, backend, rng, p: float = 0.15) -> dict:
    """Dangling links / orphan FKs must not crash or flood the engine."""
    out = {k: (v.copy() if v is not None else v) for k, v in frames.items()}
    injected = []

    # (1) TR lesion links pointing at a non-existent lesion id.
    tr = out.get("TR")
    if tr is not None and not tr.empty and "TRLNKID" in tr.columns:
        idx = rng.sample(list(tr.index), max(1, int(len(tr) * p)))
        tr.loc[idx, "TRLNKID"] = "ORPHAN-LESION-ZZZ"
        out["TR"] = tr
        injected.append(f"TR.TRLNKID orphaned x{len(idx)}")

    # (2) RS rows referencing a subject absent from DM (orphan USUBJID).
    rs = out.get("RS")
    if rs is not None and not rs.empty:
        ghost = rs.iloc[[0]].copy()
        ghost["USUBJID"] = "GHOST-SUBJECT-000"
        out["RS"] = pd.concat([rs, ghost], ignore_index=True)
        injected.append("RS ghost USUBJID x1")

    # (3) Drop TU rows that TR lesion links depend on (dangling references).
    tu = out.get("TU")
    if tu is not None and not tu.empty:
        drop = rng.sample(list(tu.index), max(1, int(len(tu) * p)))
        out["TU"] = tu.drop(index=drop).reset_index(drop=True)
        injected.append(f"TU rows dropped x{len(drop)} (dangling TR)")

    t = time.time()
    crashed, n_flags = False, -1
    try:
        flags, _ = _detect(_build_graph(out), backend)
        n_flags = _archetype_flag_count(flags)
    except Exception as exc:  # noqa: BLE001
        crashed = True
        logger.warning("orphan_fk crashed: %s", exc)
    return {"perturbations": injected, "archetype_flags": n_flags,
            "crashed": crashed, "seconds": round(time.time() - t, 1)}


# -- experiment (c): undefined visit structures ------------------------------

def exp_undefined_visits(frames, backend, rng, p: float = 0.15) -> dict:
    """Corrupt VISITNUM; A04 should catch it, other shapes stay specific."""
    base_flags, _ = _detect(_build_graph(frames), backend)
    base_a04 = sum(1 for (a, _s) in base_flags if a == "A04")
    base_other = _archetype_flag_count(base_flags) - base_a04

    out = {k: (v.copy() if v is not None else v) for k, v in frames.items()}
    n_corrupt = 0
    for dom in ("TR", "RS"):
        df = out.get(dom)
        if df is None or df.empty or "VISITNUM" not in df.columns:
            continue
        idx = rng.sample(list(df.index), max(1, int(len(df) * p)))
        # fractional visit numbers = undefined window (A04 target)
        df.loc[idx, "VISITNUM"] = df.loc[idx, "VISITNUM"].astype(float) + 0.5
        out[dom] = df
        n_corrupt += len(idx)

    t = time.time()
    crashed, a04, other = False, -1, -1
    try:
        flags, _ = _detect(_build_graph(out), backend)
        a04 = sum(1 for (a, _s) in flags if a == "A04")
        other = _archetype_flag_count(flags) - a04
    except Exception as exc:  # noqa: BLE001
        crashed = True
        logger.warning("undefined_visits crashed: %s", exc)
    return {"rows_corrupted": n_corrupt, "crashed": crashed,
            "a04_flags_baseline": base_a04, "a04_flags_perturbed": a04,
            "other_flags_baseline": base_other, "other_flags_perturbed": other,
            "a04_detected_corruption": a04 > base_a04,
            "other_shapes_stable": other <= base_other,
            "seconds": round(time.time() - t, 1)}


# -- experiment (d): co-occurring contradictions -----------------------------

def _single_injections(mini, subj, aids, backend) -> dict[str, bool]:
    """For a subject subgraph, return {aid: fires individually} for each aid."""
    clean_set, _ = _detect(_build_graph(mini), backend)
    clean_arch = {a for (a, s) in clean_set if s == subj}
    fires: dict[str, bool] = {}
    for aid in aids:
        try:
            mut, _m = MUTATIONS[aid]({k: v.copy() for k, v in mini.items()},
                                     usubjid=subj)
            mut_set, _ = _detect(_build_graph(mut), backend)
            fires[aid] = aid in ({a for (a, s) in mut_set if s == subj} - clean_arch)
        except Exception as exc:  # noqa: BLE001
            logger.warning("single %s on %s skipped: %s", aid, subj, exc)
            fires[aid] = False
    return fires


def exp_co_occurrence(frames, backend, rng, na_map, n_subjects=3) -> list[dict]:
    """Measure whether co-occurring contradictions in ONE subject interfere.

    Rigorous denominator: only archetypes that fire INDIVIDUALLY on the subject
    count. We then inject that whole detectable set at once and check how many
    still fire — isolating co-occurrence interference from data availability.
    """
    pool = [a for a in sorted(MUTATIONS)
            if a not in na_map and a not in _PER_SUBJECT_EXCLUDED]
    subs = sorted(frames["DM"]["USUBJID"].unique()) if "DM" in frames else []
    results: list[dict] = []
    for subj in rng.sample(subs, min(n_subjects, len(subs))):
        mini = _subject_frames(frames, subj)
        fires = _single_injections(mini, subj, pool, backend)
        detectable = [a for a, ok in fires.items() if ok]
        # Inject only mutually-compatible contradictions so a miss reflects detector
        # interference, not one mutation overwriting another's precondition.
        co_set, mutually_exclusive = _compatible_cooccurrence_set(detectable)
        if len(co_set) < 2:
            continue  # need >=2 co-occurring to test interference

        clean_set, _ = _detect(_build_graph(mini), backend)
        clean_arch = {a for (a, s) in clean_set if s == subj}
        mut = {k: v.copy() for k, v in mini.items()}
        for aid in co_set:
            try:
                mut, _m = MUTATIONS[aid](mut, usubjid=subj)
            except Exception as exc:  # noqa: BLE001
                logger.warning("co-occ %s on %s skipped: %s", aid, subj, exc)
        t = time.time()
        joint_set, _ = _detect(_build_graph(mut), backend)
        joint = sorted(({a for (a, s) in joint_set if s == subj} - clean_arch)
                       & set(co_set))
        results.append({
            "subject": subj, "k": len(co_set),
            "individually_detectable": sorted(detectable),
            "co_occurring_injected": co_set,
            "mutually_exclusive_excluded": mutually_exclusive,
            "jointly_detected": joint,
            "co_occurrence_recall": round(len(joint) / len(co_set), 3),
            "seconds": round(time.time() - t, 1)})
        logger.info("  co-occ subj=%s inject=%s joint=%s (excl %s)",
                    subj, co_set, joint, mutually_exclusive)
    return results


# -- driver -------------------------------------------------------------------

def run_trial(name: str, src: str, backend: str, max_subjects: int,
              seed: int) -> dict:
    rng = random.Random(seed)
    frames = Injector(source_dirs=[src])._load_all()
    n_full = frames["DM"]["USUBJID"].nunique() if "DM" in frames else 0
    frames = _subset_subjects(frames, max_subjects, rng)
    n_used = frames["DM"]["USUBJID"].nunique() if "DM" in frames else 0
    na_map = not_applicable(frames)
    logger.info("[%s] %d subjects (of %d) | not-applicable: %s",
                name, n_used, n_full, sorted(na_map))

    return {
        "src": src, "n_subjects_full": n_full, "n_subjects_used": n_used,
        "not_applicable": sorted(na_map),
        "missingness": exp_missingness(frames, backend, rng),
        "orphan_fk": exp_orphan_fk(frames, backend, rng),
        "undefined_visits": exp_undefined_visits(frames, backend, rng),
        "co_occurrence": exp_co_occurrence(frames, backend, rng, na_map),
    }


def run(out: Path, backend: str, max_subjects: int, seed: int) -> dict:
    t0 = time.time()
    trials = {}
    for name, src in TRIALS.items():
        if not Path(src).exists():
            logger.warning("trial %s absent at %s — skipping", name, src)
            continue
        trials[name] = run_trial(name, src, backend, max_subjects, seed)

    # cross-trial specificity + robustness summary
    summary = {}
    for name, tr in trials.items():
        miss = tr["missingness"]
        summary[name] = {
            "no_crash_all_experiments": (
                all(not m["crashed"] for m in miss)
                and not tr["orphan_fk"]["crashed"]
                and not tr["undefined_visits"]["crashed"]),
            "missingness_max_flag_increase": max(
                (m.get("delta_vs_clean") or 0) for m in miss),
            "undefined_visit_a04_caught": tr["undefined_visits"]["a04_detected_corruption"],
            "undefined_visit_other_flag_delta": (
                tr["undefined_visits"]["other_flags_perturbed"]
                - tr["undefined_visits"]["other_flags_baseline"]),
            "co_occurrence_recall": [c["co_occurrence_recall"] for c in tr["co_occurrence"]],
            "co_occurrence_min_recall": (
                min((c["co_occurrence_recall"] for c in tr["co_occurrence"]), default=None)),
        }

    report = {
        "seed": seed, "backend": backend, "max_subjects": max_subjects,
        "trials": trials, "summary": summary,
        "runtime_sec": round(time.time() - t0, 1),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print("->", out)
    return report


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Adversarial robustness sweep on real trials.")
    ap.add_argument("--backend", choices=["pyshacl", "oxigraph"], default="oxigraph")
    ap.add_argument("--out", default="eval/robustness_sweep.json")
    ap.add_argument("--max-subjects", type=int, default=60,
                    help="cap subjects per trial to keep full-graph detects fast")
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args(argv)
    run(Path(a.out), a.backend, a.max_subjects, a.seed)


if __name__ == "__main__":
    main()
