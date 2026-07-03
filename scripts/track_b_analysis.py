"""Track B novelty analysis — CAVE-only catches on contradiction-injected data.

For each of 20 archetypes (A01–A20): load clean DataFrames, apply mutation,
convert to RDF, run L1 SHACL + L3 CaveAgent, record detection vs clean baseline.
Saves results to eval/track_b_results.json.
"""
from __future__ import annotations

import hashlib
import json
import logging
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd
from rdflib import Graph, Literal, RDF, XSD

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent.orchestrator import CaveAgent
from audit.store import AuditStore
from bench.mutations import MUTATIONS
from kg.ontology import CAVE, CDISC, DOMAINS, record_iri
from shacl.runner import ShaclRunner

logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

RESULTS_PATH = _ROOT / "eval" / "track_b_results.json"
ARCHETYPES = sorted(MUTATIONS.keys())


@dataclass
class ArchetypeResult:
    """Detection results for a single archetype."""
    archetype_id: str
    injected: bool
    description: str = ""
    l1_flag_count: int = 0
    l3_flag_count: int = 0
    detected: bool = False
    detection_source: str = ""  # "L1" | "L3" | "both" | ""
    flag_delta_vs_clean: int = 0
    error: str = ""


# -- RDF conversion from DataFrames ------------------------------------------

def _frames_to_graph(frames: dict[str, pd.DataFrame]) -> Graph:
    """Convert dict of DataFrames to an RDF graph (only DOMAINS)."""
    g = Graph()
    g.bind("cdisc", CDISC)
    g.bind("cave", CAVE)
    for domain in DOMAINS:
        df = frames.get(domain)
        if df is None or df.empty:
            continue
        seq_col = f"{domain}SEQ"
        is_supp = domain.startswith("SUPP")
        for _, row in df.iterrows():
            usubjid = str(row.get("USUBJID", ""))
            # Trial design domains (TA, TE, etc.) have no USUBJID — use hash
            if not usubjid:
                seq = row.get(seq_col, _hash_row(row))
                subj = record_iri(domain, "_trial_", seq)
            else:
                seq = row.get(seq_col, _hash_row(row))
                subj = record_iri(domain, usubjid, seq)
            g.add((subj, RDF.type, CAVE[domain]))
            if usubjid:
                g.add((subj, CDISC.USUBJID, Literal(usubjid)))
                g.add((subj, CAVE.USUBJID, Literal(usubjid)))
            g.add((subj, CDISC.STUDYID, Literal(str(row.get("STUDYID", "")))))
            for col in df.columns:
                if col in ("STUDYID", "DOMAIN", "USUBJID", seq_col):
                    continue
                val = row.get(col)
                if val is None or (isinstance(val, float) and val != val):
                    continue
                lit = _to_literal(val)
                g.add((subj, CAVE[col], lit))
            # Supplemental qualifier expansion
            if is_supp:
                qnam = str(row.get("QNAM", "")).strip()
                qval = row.get("QVAL")
                if qnam and qval is not None:
                    g.add((subj, CAVE[f"SUPP_{qnam}"], _to_literal(qval)))
    return g


def _to_literal(val) -> Literal:
    if isinstance(val, bool):
        return Literal(val, datatype=XSD.boolean)
    if isinstance(val, int):
        return Literal(val, datatype=XSD.integer)
    if isinstance(val, float):
        return Literal(val, datatype=XSD.double)
    return Literal(str(val))


def _hash_row(row) -> str:
    payload = "|".join(str(v) for v in row.values)
    return hashlib.md5(payload.encode()).hexdigest()[:12]


# -- RS enrichment (for L3 agent A19 detection) --------------------------------

# Valid RECIST 1.1 Table 7 target-axis responses. An overall response of
# "NON-CR/NON-PD" denotes a subject with only non-target disease (no measurable
# target lesions), for whom the target-driven Table 7 overall-response derivation
# does not apply. Enriching such a subject only manufactures a spurious A19
# contradiction (Table 7 can never return "NON-CR/NON-PD"), so they are skipped.
_TABLE7_TARGET_RESPONSES = {"CR", "PR", "SD", "PD", "NE"}


def _has_target_overall(subj_rs: pd.DataFrame) -> bool:
    """True if the subject has any overall response on the Table-7 target axis.

    A subject whose only overall responses are non-target categories (e.g.
    ``NON-CR/NON-PD``) or never-done (``ND``) has no measurable target response
    for the Table-7 derivation, so enriching them only manufactures a spurious
    A19 contradiction. We test the subject's whole OVRLRESP set (not just the
    first visit), so an ``ND``-at-screening-then-``SD`` subject stays eligible.
    """
    ov = subj_rs[subj_rs["RSTESTCD"].astype(str).str.upper() == "OVRLRESP"]
    vals = {str(v).upper() for v in ov["RSORRES"]}
    return bool(vals & _TABLE7_TARGET_RESPONSES)


def _new_lesion_status(frames: dict[str, pd.DataFrame], usubjid: str) -> str:
    """NEWLEC Y/N from explicit new-lesion records in TU/TR (per-subject).

    Falls back to "N" when no mapped domain encodes a new-lesion marker (the
    case for both real trials and the benchmark, where new lesions are not
    represented as a "NEW" token in these columns).
    """
    for dom, cols in (("TU", ("TUORRES", "TUSTRESC", "TULNKID")),
                      ("TR", ("TRGRPID", "TRLNKID"))):
        df = frames.get(dom)
        if df is None or df.empty or "USUBJID" not in df.columns:
            continue
        sub = df[df["USUBJID"] == usubjid]
        for col in cols:
            if col in sub.columns and sub[col].astype(str).str.upper().str.contains("NEW").any():
                return "Y"
    return "N"


def _enrich_rs(frames: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Add NTOVRLRESP and NEWLEC rows to RS for each eligible USUBJID.

    The L3 CaveAgent needs these RECIST test codes for the Table 7 lookup that
    detects A19 (overall-response) contradictions.

    Enrichment is applied **per-subject** rather than uniformly:

    * Subjects whose overall response is non-target-only (not one of
      CR/PR/SD/PD/NE) are **skipped** — the target-driven Table 7 derivation does
      not apply to them, so the previous blanket enrichment produced two spurious
      baseline contradictions on clean data. Restricting enrichment to subjects
      with a measurable target response removes that noise (R1-4).
    * ``NEWLEC`` is derived from the subject's actual new-lesion records rather
      than assumed.

    ``NTOVRLRESP`` is held at "NON-CR/NON-PD": the benchmark carries no per-subject
    non-target *overall* response, and the delta-based A19 evaluation relies on a
    fixed non-target reference (deriving it from the injected overall would erase
    the very contradiction the construction validation injects). This is the
    documented delta-methodology assumption, now scoped to the subjects for whom
    Table 7 is well-defined.
    """
    rs = frames.get("RS")
    if rs is None or rs.empty:
        return frames
    extra_rows: list[pd.Series] = []
    for usubjid in rs["USUBJID"].unique():
        subj_rs = rs[rs["USUBJID"] == usubjid]
        if not _has_target_overall(subj_rs):
            continue  # non-target-only / never-done subject: Table 7 derivation N/A
        base_row = subj_rs.iloc[0].copy()
        for testcd, val in [("NTOVRLRESP", "NON-CR/NON-PD"),
                            ("NEWLEC", _new_lesion_status(frames, usubjid))]:
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


# -- Validation helpers -------------------------------------------------------

def _run_l1(graph: Graph) -> int:
    """Run L1 SHACL, return violation count."""
    with AuditStore(":memory:") as store:
        return ShaclRunner(graph, store=store).run().get("total", 0)


def _run_l3(graph: Graph) -> list[dict]:
    """Run L3 CaveAgent (A19), return traces."""
    return CaveAgent().run(graph)


# -- Core logic ---------------------------------------------------------------

def analyze_archetype(
    archetype_id: str, clean_frames: dict[str, pd.DataFrame], clean_l1: int,
) -> ArchetypeResult:
    """Inject one archetype, run L1+L3, return result."""
    result = ArchetypeResult(archetype_id=archetype_id, injected=False)
    frames = {k: v.copy() for k, v in clean_frames.items()}

    try:
        frames, meta = MUTATIONS[archetype_id](frames)
    except Exception as exc:
        result.error = str(exc)
        return result

    result.injected = True
    result.description = meta.get("description", "")

    # Enrich RS with NTOVRLRESP/NEWLEC for L3 agent (A19 detection)
    frames = _enrich_rs(frames)

    graph = _frames_to_graph(frames)
    result.l1_flag_count = _run_l1(graph)
    result.l3_flag_count = len(_run_l3(graph))
    result.flag_delta_vs_clean = result.l1_flag_count - clean_l1

    l1d = result.flag_delta_vs_clean != 0  # any delta (positive or negative) = detected
    l3d = result.l3_flag_count > 0
    if l1d and l3d:
        result.detection_source = "both"
    elif l3d:
        result.detection_source = "L3"
    elif l1d:
        result.detection_source = "L1"
    result.detected = l1d or l3d
    return result


def run_analysis(output_path: Path = RESULTS_PATH) -> dict:
    """Run full Track B analysis across all 20 archetypes."""
    from bench.injector import Injector
    clean_frames = Injector(output_dir="bench/output_track_b")._load_all()
    # Apply RS enrichment to clean baseline for fair delta comparison
    enriched_clean = _enrich_rs({k: v.copy() for k, v in clean_frames.items()})
    clean_l1 = _run_l1(_frames_to_graph(enriched_clean))
    logger.info("Clean baseline L1: %d", clean_l1)

    results: list[dict] = []
    for aid in ARCHETYPES:
        r = analyze_archetype(aid, clean_frames, clean_l1)
        results.append(asdict(r))
        logger.info("%s: det=%s src=%s d=%d", aid, r.detected,
                    r.detection_source, r.flag_delta_vs_clean)

    # Aggregate metrics
    total = len(results)
    inj = sum(1 for r in results if r["injected"])
    det = sum(1 for r in results if r["detected"])
    l1_det = sum(1 for r in results if r["detection_source"] in ("L1", "both"))
    l3_det = sum(1 for r in results if r["detection_source"] in ("L3", "both"))
    cave_only = [r["archetype_id"] for r in results
                 if r["detection_source"] in ("L3", "both")]
    fp_delta = sum(r["flag_delta_vs_clean"] for r in results
                   if r["flag_delta_vs_clean"] > 0)

    report = {
        "archetypes": results,
        "summary": {
            "archetypes_tested": total, "injected": inj, "detected": det,
            "detection_rate": round(det / inj, 3) if inj else 0.0,
            "l1_detections": l1_det, "l3_detections": l3_det,
            "cave_total": det, "cave_only_catches": cave_only,
            "cave_only_count": len(cave_only),
            "false_positive_delta": fp_delta, "clean_baseline_l1": clean_l1,
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, default=str),
                           encoding="utf-8")
    s = report["summary"]
    print(f"\nTrack B Novelty Analysis: {s['archetypes_tested']}/20 tested, "
          f"L1={s['l1_detections']}, L3={s['l3_detections']}, "
          f"CAVE-only={s['cave_only_catches']}, results={output_path}")
    return report


# -- Single-pass detection path (Gate 2a) -------------------------------------
#
# The delta path above declares a contradiction "detected" when the injected
# graph's total L1 flag count differs from a *clean baseline* run
# (``flag_delta_vs_clean != 0``). A real deployment has no clean reference to
# subtract. The single-pass path removes that crutch: it runs L1 **once** on one
# dataset and declares detection when the *injected subject itself* is flagged by
# the archetype's own shape — no clean-baseline subtraction. It also measures the
# clean-data specificity directly (how many subjects each shape flags on the
# untouched reference), which is the honest single-pass false-positive count.

SINGLE_PASS_PATH = _ROOT / "eval" / "single_pass_results.json"


@dataclass
class SinglePassResult:
    """Single-pass (no clean-baseline delta) detection result for one archetype."""
    archetype_id: str
    injected_subject: str = ""
    detected: bool = False
    detection_source: str = ""  # "L1" | "L3" | ""
    clean_fp_subjects: int = 0
    note: str = ""


def _flagged_subjects_by_archetype(
    graph: Graph, backend: str = "oxigraph",
) -> dict[str, set[str]]:
    """Map each archetype id to the set of subjects its L1 shape flags on ``graph``."""
    out: dict[str, set[str]] = {}
    with AuditStore(":memory:") as store:
        ShaclRunner(graph, store=store, backend=backend).run()
        for archetype, subject in store._conn.execute(
            "SELECT archetype, subject FROM traces",
        ).fetchall():
            out.setdefault(archetype, set()).add(subject)
    return out


def _flag_counts_by_archetype(
    graph: Graph, backend: str = "oxigraph",
) -> dict[str, int]:
    """Map each archetype id to the NUMBER of flags (rows) it emits on ``graph``.

    Distinct from :func:`_flagged_subjects_by_archetype` (which counts subjects):
    a shape can emit several flags for one subject, so flags >= subjects.
    """
    out: dict[str, int] = {}
    with AuditStore(":memory:") as store:
        ShaclRunner(graph, store=store, backend=backend).run()
        for (archetype,) in store._conn.execute(
            "SELECT archetype FROM traces",
        ).fetchall():
            out[archetype] = out.get(archetype, 0) + 1
    return out


def analyze_archetype_single_pass(
    archetype_id: str,
    clean_frames: dict[str, pd.DataFrame],
    clean_flagged: dict[str, set[str]],
    backend: str = "oxigraph",
) -> SinglePassResult:
    """Inject one archetype and detect it single-pass (no clean-baseline delta)."""
    result = SinglePassResult(
        archetype_id=archetype_id,
        clean_fp_subjects=len(clean_flagged.get(archetype_id, set())),
    )
    frames = {k: v.copy() for k, v in clean_frames.items()}
    try:
        frames, meta = MUTATIONS[archetype_id](frames)
    except Exception as exc:  # noqa: BLE001 — record and continue
        result.note = f"injection error: {exc}"
        return result

    tgt = str(meta.get("usubjid", ""))
    result.injected_subject = tgt
    if not tgt or "skipped" in meta.get("description", ""):
        result.note = "no target subject (mutation not applicable to this cohort)"
        return result

    graph = _frames_to_graph(_enrich_rs(frames))
    flagged = _flagged_subjects_by_archetype(graph, backend)
    if tgt in flagged.get(archetype_id, set()):
        result.detected = True
        result.detection_source = "L1"
        return result

    # L3-only archetypes (A19) have no L1 shape — fall back to the agent trace.
    l3 = [t for t in _run_l3(graph) if t.get("archetype") == archetype_id]
    if l3:
        result.detected = True
        result.detection_source = "L3"
    return result


# -- Candidate-based subject-specific detection (Gate 2a, robust harness) ------
#
# The auto-picked-subject single-pass path above can miss an archetype when the
# one subject `bench.mutations` happens to select does not manifest the pattern
# (e.g. A01's SLD drop, or A07's confirmation window) after the shapes were
# hardened for specificity. The manuscript's held-out analysis and the E2
# real-data runner both avoid this by trying several candidate subjects and
# crediting detection only when the archetype fires on the *injected* subject
# (subject-specific, no global-delta over-crediting). This function applies that
# same principled criterion to the benchmark, so the Track B detection number is
# reproducible from the current hardened shapes.

def _subject_subframes(frames: dict[str, pd.DataFrame], subj: str
                       ) -> dict[str, pd.DataFrame]:
    """Restrict subject-scoped domains to USUBJID == subj; keep trial-design domains."""
    out: dict[str, pd.DataFrame] = {}
    for dom, df in frames.items():
        if df is None or df.empty or "USUBJID" not in df.columns:
            out[dom] = df.copy() if df is not None else df
        else:
            out[dom] = df[df["USUBJID"] == subj].reset_index(drop=True)
    return out


def _archetype_fires_on_subject(
    frames: dict[str, pd.DataFrame], aid: str, subj: str, backend: str,
) -> bool:
    """Inject Ai into subj on a per-subject subgraph; True iff Ai NEWLY fires on subj."""
    mini = _subject_subframes(frames, subj)
    clean = _flagged_subjects_by_archetype(
        _frames_to_graph(_enrich_rs({k: v.copy() for k, v in mini.items()})), backend)
    if subj in clean.get(aid, set()):
        return False  # already flagged pre-injection — not a new detection
    try:
        mut, meta = MUTATIONS[aid](mini, usubjid=subj)
    except Exception:  # noqa: BLE001
        return False
    if "skipped" in meta.get("description", ""):
        return False
    graph = _frames_to_graph(_enrich_rs(mut))
    fired = _flagged_subjects_by_archetype(graph, backend)
    if subj in fired.get(aid, set()):
        return True
    if aid == "A19":  # L3-only
        return len([t for t in _run_l3(graph) if t.get("archetype") == aid]) > 0
    return False


# A16 (cross-study duplicate USUBJID) and A17 (ARMCD<->ARM one-to-one) are not
# expressible on a single-subject subgraph: A17 compares ARM across subjects, and
# A16 is a structural uniqueness violation caught by the ported CORE checks rather
# than an archetype shape. They are evaluated on the FULL graph instead.
_FULLGRAPH_ARCHETYPES = {"A16", "A17"}


def analyze_archetype_fullgraph(
    aid: str, clean_frames: dict[str, pd.DataFrame],
    clean_flagged: dict[str, set[str]], clean_total: int, backend: str,
) -> dict:
    """Full-graph detection for cross-subject (A17) / structural (A16) archetypes."""
    rec = {"archetype_id": aid, "status": "missed", "detection_source": ""}
    frames = {k: v.copy() for k, v in clean_frames.items()}
    try:
        frames, meta = MUTATIONS[aid](frames)
    except Exception as exc:  # noqa: BLE001
        rec["error"] = str(exc)
        return rec
    subj = str(meta.get("usubjid", ""))
    rec["usubjid"] = subj
    graph = _frames_to_graph(_enrich_rs(frames))
    if aid == "A17":
        # cohort-level: the A17 shape fires on the tampered ARMCD group
        fired = _flagged_subjects_by_archetype(graph, backend)
        if fired.get("A17", set()) - clean_flagged.get("A17", set()):
            rec.update(status="detected", detection_source="L1")
    else:  # A16 structural duplicate — detected by a change in the structural flag set
        total = _flag_counts_by_archetype(graph, backend)
        mut_total = sum(total.values())
        rec["total_flag_delta"] = mut_total - clean_total
        if mut_total != clean_total:
            rec.update(status="detected", detection_source="structural")
    return rec


def analyze_archetype_candidates(
    aid: str, clean_frames: dict[str, pd.DataFrame],
    clean_flagged: dict[str, set[str]], backend: str, k: int,
) -> dict:
    """Try up to k candidate subjects; detected iff Ai fires on any injected subject."""
    rec = {"archetype_id": aid, "status": "missed", "detection_source": "",
           "candidates_tried": 0, "candidates_detected": 0}
    subs = (sorted(clean_frames["DM"]["USUBJID"].unique())
            if "DM" in clean_frames else [])
    eligible = [s for s in subs if s not in clean_flagged.get(aid, set())]
    for subj in eligible[:k]:
        rec["candidates_tried"] += 1
        try:
            if _archetype_fires_on_subject(clean_frames, aid, subj, backend):
                rec["candidates_detected"] += 1
                rec["status"] = "detected"
                rec["detection_source"] = "L3" if aid == "A19" else "L1"
                rec["usubjid"] = subj
                break
        except Exception as exc:  # noqa: BLE001
            rec.setdefault("errors", []).append(f"{subj}: {exc}")
    return rec


def run_candidate_analysis(
    output_path: Path | None = None, backend: str = "oxigraph", k: int = 12,
) -> dict:
    """Track B detection via the subject-specific candidate criterion (reproducible)."""
    from bench.injector import Injector
    out = output_path or (_ROOT / "eval" / "track_b_candidate_results.json")
    clean_frames = Injector(output_dir="bench/output_candidate")._load_all()
    clean_graph = _frames_to_graph(
        _enrich_rs({k2: v.copy() for k2, v in clean_frames.items()}))
    clean_flagged = _flagged_subjects_by_archetype(clean_graph, backend)
    clean_total = sum(_flag_counts_by_archetype(clean_graph, backend).values())
    results = []
    for aid in ARCHETYPES:
        if aid in _FULLGRAPH_ARCHETYPES:
            r = analyze_archetype_fullgraph(
                aid, clean_frames, clean_flagged, clean_total, backend)
        else:
            r = analyze_archetype_candidates(
                aid, clean_frames, clean_flagged, backend, k)
        results.append(r)
        logger.info("%s candidate: %s (%s) tried=%d", aid, r["status"],
                    r.get("detection_source", ""), r.get("candidates_tried", 0))
    detected = [r["archetype_id"] for r in results if r["status"] == "detected"]
    report = {
        "method": "candidate_subject_specific_no_global_delta",
        "backend": backend, "candidates_per_archetype": k,
        "archetypes": results,
        "summary": {
            "archetypes_tested": len(results),
            "detected": len(detected),
            "detected_ids": detected,
            "missed_ids": [r["archetype_id"] for r in results
                           if r["status"] != "detected"],
            "l1_detections": sum(1 for r in results
                                 if r.get("detection_source") == "L1"),
            "l3_detections": sum(1 for r in results
                                 if r.get("detection_source") == "L3"),
            "structural_detections": sum(1 for r in results
                                         if r.get("detection_source") == "structural"),
        },
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    s = report["summary"]
    print(f"\nTrack B candidate detection: {s['detected']}/{s['archetypes_tested']} "
          f"(L1={s['l1_detections']}, L3={s['l3_detections']}); "
          f"missed={s['missed_ids']}; results={out}")
    return report


def run_single_pass_analysis(
    output_path: Path = SINGLE_PASS_PATH, backend: str = "oxigraph",
) -> dict:
    """Measure single-pass detection + clean-data specificity across all archetypes."""
    from bench.injector import Injector
    clean_frames = Injector(output_dir="bench/output_single_pass")._load_all()
    clean_graph = _frames_to_graph(
        _enrich_rs({k: v.copy() for k, v in clean_frames.items()}))
    clean_flagged = _flagged_subjects_by_archetype(clean_graph, backend)
    clean_flag_counts = _flag_counts_by_archetype(clean_graph, backend)

    results: list[dict] = []
    for aid in ARCHETYPES:
        r = analyze_archetype_single_pass(aid, clean_frames, clean_flagged, backend)
        results.append(asdict(r))
        logger.info("%s single-pass: det=%s src=%s clean_fp=%d", aid,
                    r.detected, r.detection_source, r.clean_fp_subjects)

    detected = [r["archetype_id"] for r in results if r["detected"]]
    clean_fp_total = sum(
        len(v) for k, v in clean_flagged.items() if k.startswith("A"))
    report = {
        "method": "single_pass_no_clean_baseline_delta",
        "backend": backend,
        "archetypes": results,
        "summary": {
            "archetypes_tested": len(results),
            "single_pass_detected": len(detected),
            "single_pass_detected_ids": detected,
            "not_single_pass_detected": [
                r["archetype_id"] for r in results if not r["detected"]],
            "clean_fp_subjects_total": clean_fp_total,
            "clean_fp_by_archetype": {
                k: len(v) for k, v in sorted(clean_flagged.items())
                if k.startswith("A") and v},
            "clean_fp_flags_by_archetype": {
                k: n for k, n in sorted(clean_flag_counts.items())
                if k.startswith("A") and n},
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, default=str),
                           encoding="utf-8")
    s = report["summary"]
    print(f"\nSingle-pass detection: {s['single_pass_detected']}/"
          f"{s['archetypes_tested']} archetypes without a clean-baseline delta; "
          f"clean-data FP subjects={s['clean_fp_subjects_total']} "
          f"({s['clean_fp_by_archetype']}); results={output_path}")
    return report


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Track B novelty analysis.")
    ap.add_argument("--single-pass", action="store_true",
                    help="run single-pass detection (no clean-baseline delta)")
    ap.add_argument("--candidates", action="store_true",
                    help="run candidate-based subject-specific detection")
    ap.add_argument("--k", type=int, default=12,
                    help="max candidate subjects per archetype (--candidates)")
    ap.add_argument("--backend", choices=["pyshacl", "oxigraph"],
                    default="oxigraph")
    args = ap.parse_args()
    if args.candidates:
        run_candidate_analysis(backend=args.backend, k=args.k)
    elif args.single_pass:
        run_single_pass_analysis(backend=args.backend)
    else:
        run_analysis()
