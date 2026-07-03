"""Empirical CORE / Pinnacle 21 baseline on the Track B archetype benchmark.

Pinnacle 21 Community wraps the CDISC Open Rules Engine (CORE) as its validation
backend (Certara, "P21 adds support for CDISC CORE"), so CORE's detection on the
Track B archetypes is Pinnacle 21's detection ceiling. This script measures that
ceiling *empirically* by running the real CORE engine (``vendor/core``, v0.15) on
the same injected corpus the 20/20 CAVE result uses.

Pipeline
--------
``build``   : write a CORE-readable (SAS V5 XPORT) clean corpus plus one injected
              corpus per archetype, mutating only the archetype's own domain(s)
              via ``bench.mutations`` (the *validated* Track B mutators — untouched).
``compare`` : diff each injected CORE report against the clean report, restricted
              to the archetype's target subject, and decide detection.

CORE itself is invoked between the two steps by ``scripts/run_core_p21_baseline.sh``
(it lives in its own venv: ``vendor/core/.venv``).

Detection criterion (mirrors the subject-specific delta used in sec:heldout):
an archetype is "detected by CORE" iff CORE raises a NEW violation on the injected
subject that did not fire on the clean baseline. CORE's rules are domain-scoped and
structural, so cross-domain RECIST contradictions produce no such new violation.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd
import pyreadstat
import xport
import xport.v56

from bench.injector import Injector
from bench.mutations import MUTATIONS

logger = logging.getLogger(__name__)

# Archetype-relevant SDTM domains (lower-case stems). Excludes large irrelevant
# domains (QS/LB/VS/...) that only slow CORE and carry no RECIST archetype.
LEAN_DOMAINS = ["dm", "ds", "ex", "ae", "ta", "relrec", "suppdm", "suppae",
                "rs", "tr", "tu"]

ROOT = Path(__file__).resolve().parents[1]
CORPUS_DIR = ROOT / "bench" / "core_lean"
REPORT_DIR = ROOT / "eval" / "core_benchmark"


# -- XPORT writing (CORE reads via pandas.read_sas(format="xport")) -----------

def _write_xport(df: pd.DataFrame, domain: str, path: Path) -> None:
    """Write *df* as a SAS V5 XPORT file readable by ``pandas.read_sas``."""
    ds = xport.Dataset(df, name=domain.upper()[:8], label=domain.upper()[:40])
    for col in ds.columns:
        ds[col].label = str(col)[:40]
    library = xport.Library({domain.upper()[:8]: ds})
    with path.open("wb") as fh:
        xport.v56.dump(library, fh)


def _load_lean_frames() -> dict[str, pd.DataFrame]:
    """Load the lean-domain frames via the benchmark's own Injector merge."""
    inj = Injector()
    frames = inj._load_all()
    return {k: v for k, v in frames.items()
            if k.lower() in LEAN_DOMAINS and v is not None and not v.empty}


def build() -> None:
    """Write the clean corpus + one injected corpus per archetype (all XPORT)."""
    base = _load_lean_frames()
    logger.info("Lean clean frames: %s", sorted(base))

    clean_dir = CORPUS_DIR / "clean"
    clean_dir.mkdir(parents=True, exist_ok=True)
    for dom, df in base.items():
        _write_xport(df, dom, clean_dir / f"{dom.lower()}.xpt")
    logger.info("Wrote clean corpus -> %s", clean_dir)

    manifest: dict[str, Any] = {}
    for aid in sorted(MUTATIONS):
        frames = {k: v.copy() for k, v in base.items()}
        # mutators expect the full merged dict (uppercase domain keys)
        mutated, meta = MUTATIONS[aid](frames, usubjid=None)
        out = CORPUS_DIR / aid
        out.mkdir(parents=True, exist_ok=True)
        for dom, df in mutated.items():
            if dom.lower() not in LEAN_DOMAINS or df is None or df.empty:
                continue
            _write_xport(df, dom, out / f"{dom.lower()}.xpt")
        manifest[aid] = {
            "usubjid": meta.get("usubjid", ""),
            "description": meta.get("description", ""),
            "domains_modified": [d for d in meta.get("domains_modified", [])
                                 if d.lower() in LEAN_DOMAINS],
        }
        logger.info("Injected %s (subj %s)", aid, meta.get("usubjid", ""))

    (CORPUS_DIR / "manifest.json").write_text(
        json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    logger.info("Wrote manifest with %d archetypes", len(manifest))


# -- comparison ---------------------------------------------------------------

def _load_core_xref() -> dict[str, str | None]:
    """Read docs/frozen_archetype_list.csv -> {archetype: core_xref or None}.

    An archetype whose ``core_xref`` begins with 'CORE-' was *designed* as a
    structural contradiction seeded from an existing CORE rule (so CORE's rules
    express it by construction); otherwise it is a non-CORE cross-domain pattern.
    """
    import csv
    path = ROOT / "docs" / "frozen_archetype_list.csv"
    out: dict[str, str | None] = {}
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            x = (row.get("core_xref") or "").strip()
            out[row["archetype_id"]] = x if x.startswith("CORE-") else None
    return out


def _real_issues(report: Path) -> list[dict]:
    """Return CORE Issue_Details rows that are genuine validations (not build errors)."""
    data = json.loads(report.read_text(encoding="utf-8"))
    out = []
    for row in data.get("Issue_Details", []):
        if "failed to build" in row.get("message", "").lower():
            continue
        out.append(row)
    return out


def _issue_key(row: dict) -> tuple:
    return (row.get("core_id", ""), row.get("dataset", ""),
            row.get("USUBJID", ""), row.get("message", "")[:120],
            str(row.get("variables", "")), str(row.get("values", "")))


# Auditable classification of each archetype: its category and, if CORE's rule
# set genuinely expresses the injected contradiction, the matching CORE rule id.
# "recist_semantic" = cross-domain RECIST overall-response / confirmation logic
# (the paper's novelty); "structural_consistency" = cross-domain conformance that
# overlaps CORE's existing rules. Derived from the per-archetype new-flag analysis.
# (category, matched_core_rule, confidence, rationale)
#   confidence: "direct"   = the CORE rule's semantics ARE the injected contradiction
#                            (would NOT fire on a benign edit of the same field)
#               "indirect" = CORE flags the subject via a derived-variable rule that
#                            any edit of that field would trip (specificity not shown)
#               "none"     = no flag, or only collateral flags unrelated to the contradiction
CLASSIFICATION = {
    "A01": ("recist_semantic", None, "none", "RSORRES=PD vs >=30% SLD decrease; CORE silent"),
    "A02": ("recist_semantic", None, "none", "new lesion vs RSORRES=SD; CORE silent"),
    "A03": ("structural_consistency", None, "none", "exposure-after-attributed-AE; CORE flags only collateral date errors (EXSTDY miscalc, RFXSTDTC ref, EXSTDTC>EXENDTC), none of which expresses the AE-temporal contradiction"),
    "A04": ("recist_semantic", None, "none", "VISITNUM shift TR/RS vs EX; CORE silent"),
    "A05": ("structural_consistency", None, "none", "SUPPDM SEX vs DM SEX; CORE flags SUPP.QNAM naming collision (fires regardless of value agreement), not the M-vs-F conflict"),
    "A06": ("recist_semantic", None, "none", "non-target PD vs RSORRES=SD; CORE silent"),
    "A07": ("recist_semantic", None, "none", "PR without 28d confirmation; CORE silent"),
    "A08": ("structural_consistency", "CORE-000210", "direct", "ARMCD not in TA.ARMCD — rule semantics ARE the contradiction; a valid ARMCD would not fire"),
    "A09": ("structural_consistency", "CORE-000296", "direct", "no DS records for a treated subject — rule semantics ARE the contradiction"),
    "A10": ("structural_consistency", "CORE-000239", "direct", "RFXSTDTC != earliest EXSTDTC — rule semantics ARE the contradiction"),
    "A11": ("structural_consistency", "CORE-000238", "direct", "RFXENDTC != latest EX date — rule semantics ARE the contradiction"),
    "A12": ("structural_consistency", "CORE-000705", "direct", "DTHFL=Y but DTHDTC missing — death-flag consistency rule; fires on the injected inconsistency, not a benign edit"),
    "A13": ("structural_consistency", "CORE-000846", "direct", "RACE=MULTIPLE w/o SUPPDM — rule semantics ARE the contradiction"),
    "A14": ("structural_consistency", None, "none", "EX removed for treated subject; CORE raised no new flag on subject"),
    "A15": ("structural_consistency", "CORE-000529", "indirect", "RFSTDTC shift surfaced only via DMDY/EXSTDY/AEENDY study-day miscalc — a generic derived-variable rule that ANY date edit would trip; specificity to the contradiction not shown"),
    "A16": ("structural_consistency", "CORE-000351", "direct", "duplicated DM row -> USUBJID not unique — rule semantics ARE the contradiction"),
    "A17": ("structural_consistency", "CORE-000318", "direct", "ARMCD-ARM not 1:1 — rule semantics ARE the contradiction"),
    "A18": ("recist_semantic", None, "none", "non-target PD vs RS=SD; CORE silent"),
    "A19": ("recist_semantic", None, "none", "RSORRES=CR vs target PR (Table 7); CORE silent"),
    "A20": ("recist_semantic", None, "none", "iCPD without confirmation; CORE flags only incidental RSSEQ uniqueness, not the iRECIST temporal contradiction"),
}

# SDTM domains the paper's B2_CORE baseline scopes to (eval/baselines/b2_core.py).
ONCOLOGY_DATASETS = {"DM", "EX", "TU", "TR", "RS"}


def compare() -> dict:
    """Diff each injected CORE report vs clean on the target subject."""
    manifest = json.loads((CORPUS_DIR / "manifest.json").read_text(encoding="utf-8"))
    clean = _real_issues(REPORT_DIR / "lean_clean.json")
    clean_keys = {_issue_key(r) for r in clean}
    xref = _load_core_xref()  # archetype -> design-time CORE rule seed (or None)

    results = []
    flags_subject = 0
    direct = indirect = 0
    sem_total = sem_direct = 0
    struct_total = struct_direct = struct_indirect = 0
    direct_oncology = 0  # direct detections whose rule fired on an oncology-domain dataset
    for aid in sorted(manifest):
        rep = REPORT_DIR / f"lean_{aid}.json"
        if not rep.is_file():
            results.append({"archetype": aid, "error": "no CORE report"})
            continue
        subj = manifest[aid]["usubjid"]
        inj = _real_issues(rep)
        new = [r for r in inj if _issue_key(r) not in clean_keys]
        new_subj = [r for r in new if str(r.get("USUBJID", "")) == str(subj)]
        new_cids = sorted({r.get("core_id", "") for r in new_subj})

        _, matched_rule, confidence, rationale = CLASSIFICATION.get(
            aid, ("unknown", None, "none", ""))
        # Authoritative category from the project's own frozen archetype list:
        design_core_seed = xref.get(aid)
        category = ("core_derived_structural" if design_core_seed
                    else "noncore_crossdomain")
        core_flags_subject = len(new_subj) > 0
        rule_fired = bool(matched_rule) and matched_rule in new_cids
        # domains where the matched rule fired (oncology-filter sensitivity)
        matched_domains = {r.get("dataset", "").split(".")[0].upper()
                           for r in new_subj if r.get("core_id") == matched_rule}
        in_oncology = bool(matched_domains & ONCOLOGY_DATASETS)

        is_direct = rule_fired and confidence == "direct"
        is_indirect = rule_fired and confidence == "indirect"
        flags_subject += int(core_flags_subject)
        direct += int(is_direct)
        indirect += int(is_indirect)
        if category == "noncore_crossdomain":
            sem_total += 1
            sem_direct += int(is_direct)
        else:
            struct_total += 1
            struct_direct += int(is_direct)
            struct_indirect += int(is_indirect)
        if is_direct and in_oncology:
            direct_oncology += 1

        results.append({
            "archetype": aid,
            "usubjid": subj,
            "description": manifest[aid]["description"],
            "category": category,
            "design_core_seed": design_core_seed,
            "domains_modified": manifest[aid]["domains_modified"],
            "core_new_issues_on_target_subject": len(new_subj),
            "core_flags_subject": core_flags_subject,
            "detection_confidence": confidence if rule_fired else "none",
            "core_detects_contradiction": is_direct,
            "matched_core_rule": matched_rule if rule_fired else None,
            "matched_rule_in_oncology_domain": in_oncology if rule_fired else False,
            "new_issue_core_ids": new_cids,
            "rationale": rationale,
        })

    n = len(results)
    summary = {
        "engine": "CDISC CORE (cdisc-rules-engine) v0.15 — the engine Pinnacle 21 Community 4.0 can execute",
        "standard": "sdtmig 3-4",
        "corpus": "Track B lean benchmark (pilot1 + pharmaversesdtm_recist), per-archetype injection, CORE-readable XPORT",
        "clean_real_issues": len(clean),
        "archetypes_total": n,
        "detection_criterion": ("CORE detects an archetype iff a NEW CORE violation whose "
                                "rule semantics ARE the injected contradiction ('direct') "
                                "fires on the injected subject. 'indirect' = flagged only via "
                                "a generic derived-variable rule any edit would trip. "
                                "'collateral' flags (wrong reason) and silence both = not detected."),
        "grouping": ("Authoritative split from docs/frozen_archetype_list.csv core_xref: "
                     "10 'core_derived_structural' archetypes (A08-A17, each SEEDED from a "
                     "CORE rule) vs 10 'noncore_crossdomain' archetypes (A01-A07/A18-A20, "
                     "core_xref=none or a RECIST shape)."),
        "HEADLINE": {
            "core_detects_DIRECT": f"{direct}/{n}",
            "core_detects_direct_plus_indirect": f"{direct + indirect}/{n}",
            "core_flags_subject_any_reason": f"{flags_subject}/{n}",
            "noncore_crossdomain_detected": f"{sem_direct}/{sem_total}",
            "core_derived_structural_detected_direct": f"{struct_direct}/{struct_total}",
            "core_derived_structural_detected_incl_indirect": f"{struct_direct + struct_indirect}/{struct_total}",
            "direct_under_paper_oncology_domain_filter": f"{direct_oncology}/{n}",
        },
        "note": ("A real CORE run does NOT give 0/20. CORE detects "
                 f"{sem_direct}/{sem_total} of the non-CORE cross-domain archetypes (the "
                 "RECIST/semantic contradictions CORE structurally cannot express) but "
                 f"directly detects {struct_direct}/{struct_total} of the archetypes the "
                 "benchmark itself SEEDED from CORE rules (frozen_archetype_list.csv core_xref: "
                 "ARMCD-not-in-TA, RFXSTDTC/RFXENDTC, RACE=MULTIPLE, duplicate USUBJID, "
                 f"ARM-not-1:1, ...). Even under the paper's oncology-domain (DM/EX/TU/TR/RS) "
                 f"filter CORE directly detects {direct_oncology}/{n}. The {sem_direct}/{sem_total} "
                 "non-CORE result is robust and supports the central thesis; the blanket "
                 "'CORE 0/20' contradicts the benchmark's own design and is not reproducible."),
        "per_archetype": results,
    }
    out = ROOT / "eval" / "core_p21_benchmark.json"
    out.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    logger.info("CORE direct %d/%d (+indirect %d) | semantic %d/%d | structural %d/%d | oncology-filter %d -> %s",
                direct, n, indirect, sem_direct, sem_total,
                struct_direct, struct_total, direct_oncology, out)
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("command", choices=["build", "compare"])
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if args.command == "build":
        build()
    else:
        summary = compare()
        print(json.dumps({k: v for k, v in summary.items()
                          if k != "per_archetype"}, indent=2))


if __name__ == "__main__":
    main()
