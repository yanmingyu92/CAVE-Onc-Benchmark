"""E2 mutation transfer: inject the 20 contradiction archetypes into the mapped
real SDTM (Synta 123) and measure detection on real trial structure.

Phase 3 of the Item E plan (``docs/item_e_real_data_plan.md``). This is the
quantitative-recall companion to E1 (naturalistic specificity): E1 asks "does the
engine stay quiet on clean real data?", E2 asks "when a known contradiction is
injected into real trial topology, does the engine still catch it?".

Method (rigorous, per-subject targeted — mirrors the E1 false-positive discipline):
  1. For an archetype Ai, draw candidate subjects from the real cohort that are
     NOT already Ai-flagged on clean data, and inject one contradiction into each
     (``bench.mutations``), trying up to ``--candidates`` of them.
  2. The archetype SHACL-SPARQL shapes are USUBJID-scoped joins, so detection is
     run on a per-subject SUBGRAPH (the injected subject's rows + trial-design
     domains). This is both correct and fast, and lets the candidate pool span the
     full cohort. The one cross-subject archetype (A17: ARMCD<->ARM one-to-one) is
     run on the full graph.
  3. Ai is *detected* iff its own shape fires on the injected subject in the
     mutated subgraph but NOT in that subject's clean subgraph — a newly-induced,
     subject-specific catch, never a coarse total-flag delta. Trying several
     candidates removes the artifact of an auto-picked subject that happens not to
     satisfy the archetype's precondition.

Applicability boundary (honest data-availability, not detection misses; excluded
from the recall denominator):
  * A03/A10/A11/A14/A15 require ``EX``/``AE`` domains absent from the Synta RECIST
    package; A09 requires ``DM.ACTARMCD`` whose mapping (no ``EX`` present) floods
    A14 with per-subject false positives, so the actual-arm/exposure family is out
    of scope for this trial.
  * A07/A20 require fine-grained ``RSDTC`` dates (Synta dates are year-only).
  * A19 (L3 Table-7) requires the benchmark's single overall-response row plus
    ``NTOVRLRESP``/``NEWLEC`` test codes; real Synta RS is multi-row and lacks
    them, so detection would depend on synthetic enrichment, defeating the
    real-data purpose.

Backend: Oxigraph hybrid (G2) — pyShACL for structural shapes, pyoxigraph for the
SHACL-SPARQL detectors.

Output: ``eval/real_data_e2_synta.json``.

Usage::

    uv run python -m scripts.run_e2_real_data --backend oxigraph \
        --out eval/real_data_e2_synta.json
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

import pandas as pd
from rdflib import Graph

from audit.store import AuditStore
from bench.injector import Injector
from bench.mutations import MUTATIONS
from scripts.map_synta_to_sdtm import enrich_recist_graph
from scripts.track_b_analysis import _frames_to_graph
from shacl.runner import ShaclRunner

logger = logging.getLogger(__name__)

# L3 Table-7 (A19) can never be exercised on real multi-row RS without synthetic
# enrichment, regardless of trial — so it is always not-applicable here.
ALWAYS_NA: dict[str, str] = {
    "A19": "L3 Table-7 needs a single overall-RS row + NTOVRLRESP/NEWLEC codes; "
           "real-trial RS is multi-row and lacks them (would need synthetic enrichment)",
}
# Genuinely cross-subject archetype (ARMCD<->ARM one-to-one) — needs the full graph.
CROSS_SUBJECT = {"A17"}
# Detected outside the per-archetype shapes (duplicate USUBJID -> CORE uniqueness).
A16_STRUCTURAL = "A16"


def not_applicable(frames: dict) -> dict[str, str]:
    """Compute, from the mapped data, which archetypes cannot be exercised.

    Trial-agnostic: an archetype is not-applicable only when the domain/column/date
    it depends on is genuinely absent (honest data availability), so a richer trial
    (e.g. CA012, which ships EX + day-offset dates) automatically widens the
    applicable set relative to a sparser one (Synta).
    """
    def present(dom: str) -> bool:
        df = frames.get(dom)
        return df is not None and not df.empty

    rs = frames.get("RS")
    has_dates = (
        rs is not None and "RSDTC" in rs.columns
        and rs["RSDTC"].astype(str).str.match(r"\d{4}-\d{2}-\d{2}").any()
    )
    dm = frames.get("DM")
    has_actarmcd = dm is not None and "ACTARMCD" in dm.columns
    has_ex, has_ae = present("EX"), present("AE")
    # A03 (exposure-after-*attributed*-AE) needs an AE domain carrying drug-causality
    # attribution (AEREL in {Y, PROBABLE, POSSIBLE}). A mapped AE without a causality
    # variable (e.g. CA012's solicited-toxicity records) cannot exercise it.
    ae = frames.get("AE")
    has_ae_attrib = (
        has_ae and "AEREL" in ae.columns
        and ae["AEREL"].astype(str).str.upper().isin({"Y", "PROBABLE", "POSSIBLE"}).any()
    )

    na: dict[str, str] = dict(ALWAYS_NA)
    if not has_ae_attrib:
        na["A03"] = (
            "requires an AE domain (not mapped for this trial)" if not has_ae
            else "AE domain present but carries no causality attribution (AEREL); "
                 "A03's attributed-AE join cannot be exercised"
        )
    if not has_dates:
        na["A07"] = "requires fine-grained RSDTC dates (absent / year-only)"
        na["A20"] = "requires fine-grained RSDTC dates for iRECIST confirmation"
    if not has_actarmcd:
        na["A09"] = "requires DM.ACTARMCD (not mapped for this trial)"
    if not has_ex:
        for aid in ("A10", "A11", "A15"):
            na[aid] = "requires an EX domain (absent from this trial's RECIST package)"
    if not (has_ex and has_actarmcd):
        na["A14"] = "requires EX + DM.ACTARMCD (absent from this trial's RECIST package)"
    return na


# -- graph / detection -------------------------------------------------------

def _build_graph(frames: dict[str, pd.DataFrame]) -> Graph:
    """Frames -> RDF graph with the real-data TRTARGETLN enrichment."""
    g = _frames_to_graph(frames)
    enrich_recist_graph(g)  # derive cave:TRTARGETLN from cave:TRGRPID
    return g


def _detect(graph: Graph, backend: str) -> tuple[set[tuple[str, str]], int]:
    """Run L1; return ({(archetype, subject)}, total_flag_count) from the audit trace."""
    flags: set[tuple[str, str]] = set()
    with AuditStore(":memory:") as store:
        counts = ShaclRunner(
            graph, shapes_dir="shacl", store=store, backend=backend
        ).run()
        rows = store._conn.execute("SELECT archetype, subject FROM traces").fetchall()
    for archetype, subject in rows:
        flags.add((str(archetype), str(subject)))
    return flags, int(counts.get("total", 0))


def _subject_frames(frames: dict[str, pd.DataFrame], s: str) -> dict[str, pd.DataFrame]:
    """Restrict subject-scoped domains to USUBJID == s; keep trial-design domains."""
    out: dict[str, pd.DataFrame] = {}
    for dom, df in frames.items():
        if df is None or df.empty:
            out[dom] = df
        elif "USUBJID" in df.columns:
            out[dom] = df[df["USUBJID"] == s].reset_index(drop=True)
        else:
            out[dom] = df  # TA / trial design — keep whole
    return out


# -- per-archetype analysis --------------------------------------------------

def _candidates(
    frames: dict[str, pd.DataFrame], aid: str, clean_full: set[tuple[str, str]], k: int
) -> list[str]:
    """Subjects (sorted) not already Ai-flagged on clean data, capped at k."""
    subs = sorted(frames["DM"]["USUBJID"].unique()) if "DM" in frames else []
    eligible = [s for s in subs if (aid, s) not in clean_full]
    return eligible[:k]


def _inject_detect_subgraph(
    frames: dict[str, pd.DataFrame], aid: str, subj: str, backend: str
) -> tuple[bool, set[str]]:
    """Inject Ai into subj on a per-subject subgraph; return (newly_fired, new_shapes).

    new_shapes = archetype labels firing on subj after injection but not before.
    """
    mini = _subject_frames(frames, subj)
    clean_set, _ = _detect(_build_graph(mini), backend)
    clean_arch = {a for (a, s) in clean_set if s == subj}

    mut_frames, _meta = MUTATIONS[aid](mini, usubjid=subj)
    mut_set, _ = _detect(_build_graph(mut_frames), backend)
    mut_arch = {a for (a, s) in mut_set if s == subj}

    new = mut_arch - clean_arch
    fired = aid in new
    return fired, new


def analyze_per_subject(
    aid: str, frames: dict, clean_full: set[tuple[str, str]], backend: str, k: int
) -> dict:
    """Try up to k candidates; detected iff Ai newly fires on any injected subject."""
    rec: dict = {"archetype_id": aid, "status": "missed", "detection_source": ""}
    cands = _candidates(frames, aid, clean_full, k)
    rec["candidates_tried"] = 0
    rec["candidates_detected"] = 0
    detecting: list[str] = []
    for c in cands:
        rec["candidates_tried"] += 1
        try:
            fired, new = _inject_detect_subgraph(frames, aid, c, backend)
        except Exception as exc:  # noqa: BLE001 — record, keep sweeping
            rec.setdefault("errors", []).append(f"{c}: {exc}")
            continue
        # A16 has no own shape: any newly-induced flag on the subject counts.
        hit = fired or (aid == A16_STRUCTURAL and bool(new))
        if hit:
            rec["candidates_detected"] += 1
            detecting.append(c)
            if aid == A16_STRUCTURAL and not fired:
                rec["detection_source"] = "L1_structural"
                rec["new_shapes_on_subject"] = sorted(new)
    if detecting:
        rec["status"] = "detected"
        rec["usubjid"] = detecting[0]
        rec["detection_source"] = rec["detection_source"] or "L1"
    return rec


def analyze_cross_subject(
    aid: str, frames: dict, clean_full: set[tuple[str, str]],
    clean_full_total: int, backend: str,
) -> dict:
    """A17: inject on the full cohort and compare full-graph detection."""
    rec: dict = {"archetype_id": aid, "status": "missed", "detection_source": ""}
    mut_frames, meta = MUTATIONS[aid]({k: v.copy() for k, v in frames.items()})
    subj = str(meta.get("usubjid", ""))
    rec["usubjid"] = subj
    rec["description"] = meta.get("description", "")
    mut_set, mut_total = _detect(_build_graph(mut_frames), backend)
    rec["total_flag_delta"] = mut_total - clean_full_total
    # ARM is changed on a peer subject sharing the ARMCD; detection is cohort-level.
    newly = (aid, subj) in mut_set and (aid, subj) not in clean_full
    cohort_new = any(a == aid for (a, _s) in mut_set) and \
        not any(a == aid for (a, _s) in clean_full)
    if newly or cohort_new:
        rec.update(status="detected", detection_source="L1")
    return rec


# -- driver ------------------------------------------------------------------

def run(src: str, backend: str, out: Path, candidates: int = 10, tag: str = "synta_e2") -> dict:
    """Run the full E2 mutation-transfer sweep and write the JSON report."""
    t0 = time.time()
    frames = Injector(source_dirs=[src])._load_all()
    n_subj = frames["DM"]["USUBJID"].nunique() if "DM" in frames else 0

    clean_full, clean_full_total = _detect(_build_graph(frames), backend)
    t_baseline = time.time() - t0
    logger.info("clean full baseline: %d flags, %d subjects (%.1fs)",
                clean_full_total, n_subj, t_baseline)

    na_map = not_applicable(frames)
    results: list[dict] = []
    for aid in sorted(MUTATIONS):
        t = time.time()
        if aid in na_map:
            rec = {"archetype_id": aid, "status": "not_applicable",
                   "reason": na_map[aid]}
        elif aid in CROSS_SUBJECT:
            rec = analyze_cross_subject(
                aid, frames, clean_full, clean_full_total, backend)
        else:
            rec = analyze_per_subject(aid, frames, clean_full, backend, candidates)
        rec["seconds"] = round(time.time() - t, 1)
        results.append(rec)
        logger.info("%s: %s (%s) %.1fs", aid, rec["status"],
                    rec.get("detection_source", ""), rec["seconds"])

    applicable = [r for r in results if r["status"] in ("detected", "missed")]
    detected = [r for r in applicable if r["status"] == "detected"]
    na = [r for r in results if r["status"] == "not_applicable"]
    summary = {
        "archetypes_total": len(results),
        "applicable": len(applicable),
        "detected": len(detected),
        "missed": len(applicable) - len(detected),
        "not_applicable": len(na),
        "recall_on_applicable":
            round(len(detected) / len(applicable), 3) if applicable else 0.0,
        "detected_ids": [r["archetype_id"] for r in detected],
        "missed_ids": [r["archetype_id"] for r in applicable if r["status"] != "detected"],
        "not_applicable_ids": [r["archetype_id"] for r in na],
    }
    report = {
        "tag": tag,
        "backend": backend,
        "src": src,
        "n_subjects": n_subj,
        "candidates_per_archetype": candidates,
        "clean_baseline_l1_flags": clean_full_total,
        "summary": summary,
        "archetypes": results,
        "timing_sec": {"baseline": round(t_baseline, 1),
                       "total": round(time.time() - t0, 1)},
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print("->", out)
    return report


def main(argv=None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="E2 mutation transfer on real SDTM.")
    ap.add_argument("--src", default="data/real_sdtm/synta")
    ap.add_argument("--backend", choices=["pyshacl", "oxigraph"], default="oxigraph")
    ap.add_argument("--candidates", type=int, default=10,
                    help="max candidate subjects to try per archetype")
    ap.add_argument("--tag", default="synta_e2")
    ap.add_argument("--out", default="eval/real_data_e2_synta.json")
    a = ap.parse_args(argv)
    run(a.src, a.backend, Path(a.out), a.candidates, a.tag)


if __name__ == "__main__":
    main()
