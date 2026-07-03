"""Item D — held-out archetype generalization test (R1-2, R1-1).

Injects 5 held-out archetypes (H01-H05) and runs them against the EXISTING L1
SHACL shapes + L3 agent with NO new shape authoring. Reports per-archetype
detection so we can state an honest generalization rate beyond the constructed
A01-A20 patterns. A partial pass directly rebuts the "tailored rule-engine"
critique: the shapes detect some unseen contradictions and miss others, which is
the expected, credible behaviour for a genuine expressiveness test.

Outputs:
    eval/heldout_results.json
    docs/latex/plos_submission/analysis/heldout_table.md

Run:
    .venv/Scripts/python.exe -m scripts.heldout_analysis
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import pyshacl
from rdflib import Graph, RDF, URIRef
from rdflib.namespace import SH

from agent.orchestrator import CaveAgent
from bench.heldout_mutations import HELDOUT_MUTATIONS
from kg.ontology import CAVE
from scripts.track_b_analysis import _frames_to_graph, _enrich_rs, _run_l1, _run_l3

JSON_OUT = _ROOT / "eval" / "heldout_results.json"
MD_OUT = _ROOT / "docs" / "latex" / "plos_submission" / "analysis" / "heldout_table.md"

# Expectation set at design time (BEFORE running), to keep the test honest.
DESIGN_EXPECTATION = {
    "H01": "detect (co-occurrence; A01/A02 shapes exist)",
    "H02": "miss (no consent-ordering shape)",
    "H03": "miss/partial (novel CR+measurable pattern)",
    "H04": "detect (A18 value-robust)",
    "H05": "miss (no exposed-but-unassigned shape)",
}


def _l1_pairs(graph: Graph) -> set[tuple[str, str]]:
    """Return the set of (USUBJID, shape) L1 violation pairs for a graph.

    Subject-specific so we can credit a held-out archetype ONLY when a NEW
    violation appears on the injected subject (not a global flag-count change).
    """
    shapes = Graph()
    for ttl in sorted((_ROOT / "shacl").glob("*.ttl")):
        shapes.parse(str(ttl), format="turtle")
    _, rg, _ = pyshacl.validate(graph, shacl_graph=shapes, inference="none")
    pairs: set[tuple[str, str]] = set()
    if not isinstance(rg, Graph):
        return pairs
    for vr in rg.subjects(RDF.type, SH.ValidationResult):
        focus = rg.value(vr, SH.focusNode)
        shape = rg.value(vr, SH.sourceShape)
        # Blank-node sourceShapes (pyshacl's De Morgan property-shape components)
        # get fresh IDs every run, so set-diff would treat identical CORE shapes as
        # "new". Keep only stable NAMED shape IRIs — meaningful across runs.
        if not isinstance(shape, URIRef):
            continue
        usub = graph.value(focus, URIRef(f"{CAVE}USUBJID")) if focus else None
        subj = str(usub) if usub else (str(focus) if focus else "")
        pairs.add((subj, str(shape)))
    return pairs


def _l3_subjects(graph: Graph) -> set[str]:
    return {t.get("subject", "") for t in CaveAgent().run(graph)}


def run() -> dict:
    from bench.injector import Injector
    clean_frames = Injector(output_dir="bench/output_heldout")._load_all()
    clean_graph = _frames_to_graph(_enrich_rs({k: v.copy() for k, v in clean_frames.items()}))
    base_pairs = _l1_pairs(clean_graph)
    base_l3 = _l3_subjects(clean_graph)
    base_count = len(base_pairs)

    rows = []
    for aid in sorted(HELDOUT_MUTATIONS):
        frames = {k: v.copy() for k, v in clean_frames.items()}
        try:
            frames, meta = HELDOUT_MUTATIONS[aid](frames)
        except Exception as exc:  # noqa: BLE001
            rows.append({"archetype": aid, "injected": False, "error": str(exc)})
            continue
        s = meta.get("usubjid", "")
        graph = _frames_to_graph(_enrich_rs(frames))
        pairs = _l1_pairs(graph)
        l3_subj = _l3_subjects(graph)

        # Rigorous, subject-specific detection
        new_on_subject = {(u, sh) for (u, sh) in (pairs - base_pairs) if u == s}
        l1_det = len(new_on_subject) > 0
        l3_det = s in (l3_subj - base_l3)
        detected = l1_det or l3_det
        # Naive criterion (for transparency — shows why delta over-counts)
        naive_delta = len(pairs) - base_count
        rows.append({
            "archetype": aid, "injected": True, "subject": s,
            "description": meta.get("description", ""),
            "design_expectation": DESIGN_EXPECTATION.get(aid, ""),
            "new_l1_violations_on_subject": sorted(sh for _, sh in new_on_subject),
            "l1_detected_specific": l1_det,
            "l3_detected_specific": l3_det,
            "detected_by_existing": detected,
            "source": "L1" if l1_det and not l3_det else ("L3" if l3_det and not l1_det
                      else ("both" if l1_det and l3_det else "none")),
            "naive_global_delta": naive_delta,
            "naive_would_say_detected": naive_delta != 0 or len(l3_subj) > 0,
        })
    injected = [r for r in rows if r.get("injected")]
    n_det = sum(1 for r in injected if r.get("detected_by_existing"))
    n_naive = sum(1 for r in injected if r.get("naive_would_say_detected"))
    return {
        "clean_baseline_l1_pairs": base_count,
        "clean_baseline_l3_noise_subjects": len(base_l3),
        "detection_criterion": "new (USUBJID, shape) L1 violation on injected subject, OR new L3 trace on injected subject vs clean baseline",
        "n_heldout": len(injected),
        "n_detected_by_existing_shapes": n_det,
        "generalization_rate": round(n_det / len(injected), 3) if injected else 0,
        "n_detected_naive_criterion": n_naive,
        "results": rows,
    }


def main() -> None:
    res = run()
    JSON_OUT.write_text(json.dumps(res, indent=2), encoding="utf-8")
    MD_OUT.write_text(_render_md(res), encoding="utf-8")
    print(_render_md(res))
    print(f"\n[written] {JSON_OUT}\n[written] {MD_OUT}")


def _naive_note(res: dict) -> str:
    """Honest, state-dependent note on the naive global-delta criterion.

    Under the earlier blanket RS-enrichment a naive `delta != 0` criterion over-credited
    detection (inflated by baseline L3 noise subjects). After scoping the enrichment to
    subjects with a measurable target response, that baseline noise is gone, so the naive
    and subject-specific criteria agree. Emit whichever statement the current run supports.
    """
    n_naive = res["n_detected_naive_criterion"]
    n_det = res["n_detected_by_existing_shapes"]
    n_all = res["n_heldout"]
    noise = res["clean_baseline_l3_noise_subjects"]
    if n_naive > n_det:
        return (
            f"> A naive global `delta != 0` criterion (as critiqued by Reviewer #1) would "
            f"have credited **{n_naive}/{n_all}** — inflated by {noise} baseline L3 noise "
            f"subject(s) from fixed RS enrichment. We report the stricter subject-specific "
            f"criterion, which credits {n_det}/{n_all}."
        )
    return (
        f"> With the enrichment scoped to measurable-target subjects (0 baseline L3 noise "
        f"subjects), the naive global `delta != 0` criterion and the stricter "
        f"subject-specific criterion agree at **{n_det}/{n_all}**; we report the "
        f"subject-specific criterion, which does not depend on baseline enrichment."
    )


def _render_md(res: dict) -> str:
    lines = [
        "# Item D — held-out archetype generalization (R1-2, R1-1)",
        "",
        f"**Detection criterion (rigorous, subject-specific):** {res['detection_criterion']}.",
        "",
        f"Held-out archetypes detected by the **existing** A01-A20 shapes + L3, "
        f"no new shapes authored: **{res['n_detected_by_existing_shapes']}/{res['n_heldout']}** "
        f"(generalization rate {res['generalization_rate']:.0%}).",
        "",
        _naive_note(res),
        "",
        "| Archetype | Description | Design expectation | New L1 shape(s) on subject | L3 | Detected? |",
        "|---|---|---|---|---|---|",
    ]
    for r in res["results"]:
        if not r.get("injected"):
            lines.append(f"| {r['archetype']} | (injection error: {r.get('error','')}) | | | | ✗ |")
            continue
        new_shapes = ", ".join(s.split("/")[-1].replace("Shape_Archetype_", "")
                               for s in r["new_l1_violations_on_subject"]) or "—"
        lines.append(
            f"| {r['archetype']} | {r['description']} | {r['design_expectation']} | "
            f"{new_shapes} | {'✓' if r['l3_detected_specific'] else '—'} | "
            f"{'✓' if r['detected_by_existing'] else '✗'} |"
        )
    lines += [
        "",
        "**Reading.** This is a genuine expressiveness test: the shapes were NOT "
        "authored for these patterns, and detection is credited only when a NEW "
        "violation appears on the *injected subject*. A rate strictly between 0% and "
        "100% is the honest, expected outcome and directly addresses Reviewer #1's "
        '"tailored rule-engine" concern. Using a subject-specific delta rather than a '
        "global flag-count delta reflects the specificity discipline Reviewer #1 asked for "
        "(R1-4), since global deltas can over-credit detection when baseline enrichment adds "
        "noise. H01 additionally probes the multi-archetype interaction case Reviewer #2 raised (R2-3).",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
