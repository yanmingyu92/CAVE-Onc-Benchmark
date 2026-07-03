"""Build Gate B archetype catalog — deterministic generator.

Single source of truth: embedded SEEDS tuple.
Outputs: gate_b/archetypes.md, gate_b/archetypes.csv
"""

import argparse
import csv
from pathlib import Path

# ── 12-field card schema (frozen) ──────────────────────────────────────────
FIELDS = (
    "archetype_id", "name", "domains", "pattern", "example",
    "seed_source", "core_xref", "shacl_expressible",
    "probabilistic_required", "l1_l2_hypothesis",
    "relrec_preserving", "ming_decision",
)

# ── Frozen seed list — do NOT reorder or paraphrase A01–A07 ───────────────
SEEDS: tuple[tuple[str, ...], ...] = (
    # A01–A07: proposal §3 verbatim (lines 81–87)
    ("A01", "SLD decrease >=30% with RSORRES=PD", "RS,TR,TU",
     'Tumor SLD down >=30% but RSORRES = "PD" same visit',
     "SLD=45mm baseline -> 30mm at V3 (-33%); RSORRES='PD'",
     "proposal_§3", "RECIST_1_1_S3", "yes", "no", "L1", "yes", "tbd"),
    ("A02", "New lesion without RS escalation", "RS,TU",
     "New lesion (TU.TULNKID added) without RS escalation at the corresponding visit",
     "TULNKID='TL009' first appears at V4; RSORRES='SD'",
     "proposal_§3", "RECIST_1_1_S6", "yes", "no", "L1", "yes", "tbd"),
    ("A03", "EX start after attributed AE", "AE,EX",
     "EX (exposure) start *after* AE attributed to it (CMACTRL/AERELID timing violation)",
     "AESTDTC='2024-03-01' AEREL='Y'; EXSTDTC='2024-03-15'",
     "proposal_§3", "none", "yes", "no", "L1", "yes", "tbd"),
    ("A04", "Visit-window violation propagated", "EX,RS,TR",
     "Visit window violation propagated across TR/RS/EX",
     "V3 due Day 42 actual Day 56; TR/RS Day 56, EX Day 42",
     "proposal_§3", "none", "partial", "tbd", "tbd", "yes", "tbd"),
    ("A05", "Conflicting demographics DM vs SUPPDM", "DM,SUPPDM",
     "USUBJID with conflicting sex/age across DM and SUPPDM",
     "DM.SEX='M'; SUPPDM QNAM='SEX' QVAL='F' same USUBJID",
     "proposal_§3", "none", "yes", "no", "L1", "yes", "tbd"),
    ("A06", "Non-target PD with RS=SD", "RS,TR",
     "Non-target lesion PD without target lesion change but RS = SD",
     "Non-target 'UNEQUIVOCAL PROGRESSION'; RSORRES='SD'",
     "proposal_§3", "none", "yes", "no", "L1", "yes", "tbd"),
    ("A07", "Confirmed PR without confirmation visit", "RS",
     "Confirmed PR without required confirmation visit",
     "RSORRES='PR' at V3; no visit within 28d confirming PR/CR",
     "proposal_§3", "RECIST_1_1_S7", "yes", "no", "L1", "yes", "tbd"),
    # A08–A09: gap_rules bucket 1 — valueset / existence
    ("A08", "ARMCD not in TA valueset", "DM",
     "ACTARMCD or ARMCD in DM not present in TA.ARMCD codelist",
     "DM.ARMCD='TRTARMX'; TA has no 'TRTARMX' entry",
     "gap_rules_bucket1_valueset", "CORE-000210", "yes", "no", "L1", "yes", "tbd"),
    ("A09", "Assigned subject missing disposition", "DM",
     "Subject with populated ACTARMCD has no disposition record in DS",
     "DM.ACTARMCD='TRT A'; DS has no records for USUBJID",
     "gap_rules_bucket1_existence", "CORE-000296", "yes", "no", "L1", "yes", "tbd"),
    # A10–A11: gap_rules bucket 1 — aggregate
    ("A10", "RFXSTDTC mismatch with earliest EXSTDTC", "DM,EX",
     "DM.RFXSTDTC does not equal earliest EX.EXSTDTC for the subject",
     "DM.RFXSTDTC='2024-01-15'; min(EX.EXSTDTC)='2024-01-10'",
     "gap_rules_bucket1_aggregate", "CORE-000239", "partial", "no", "L2", "yes", "tbd"),
    ("A11", "RFXENDTC mismatch with latest EXENDTC", "DM,EX",
     "DM.RFXENDTC does not equal latest EX.EXENDTC for the subject",
     "DM.RFXENDTC='2024-06-30'; max(EX.EXENDTC)='2024-07-15'",
     "gap_rules_bucket1_aggregate", "CORE-000238", "partial", "no", "L2", "yes", "tbd"),
    # A12–A15: gap_rules bucket 1 — computed
    ("A12", "Death flag without death details", "DM",
     "DM.DTHFL='Y' but no corresponding record exists in DD dataset for the subject",
     "DM.DTHFL='Y'; DD has no records for USUBJID",
     "gap_rules_bucket1_computed", "CORE-000108", "partial", "no", "L2", "yes", "tbd"),
    ("A13", "RACE=MULTIPLE without SUPPDM records", "DM,SUPPDM",
     "DM.RACE='MULTIPLE' but SUPPDM has no or insufficient multiple-race records",
     "DM.RACE='MULTIPLE'; SUPPDM RACE has only 1 record (need >=2)",
     "gap_rules_bucket1_computed", "CORE-000846", "partial", "no", "L2", "yes", "tbd"),
    ("A14", "Assigned arm but no exposure record", "DM,EX",
     "Subject assigned to treatment arm (ACTARMCD populated) but has no EX record",
     "DM.ACTARMCD='TRT A'; EX has no records for USUBJID",
     "gap_rules_bucket1_computed", "CORE-000366", "partial", "no", "L2", "yes", "tbd"),
    ("A15", "RFSTDTC mismatch with first EXSTDTC", "DM,EX",
     "DM.RFSTDTC does not equal the first EX.EXSTDTC for the subject",
     "DM.RFSTDTC='2024-02-01'; min(EX.EXSTDTC)='2024-01-28'",
     "gap_rules_bucket1_computed", "CORE-001044", "partial", "no", "L2", "yes", "tbd"),
    # A16–A17: gap_rules bucket 2 — uniqueness / multiplicity
    ("A16", "Duplicate USUBJID across studies", "DM",
     "USUBJID appears more than once in DM across all studies",
     "USUBJID='S040' has 2 DM records with different STUDYID",
     "gap_rules_bucket2", "CORE-000351", "yes", "no", "L1", "yes", "tbd"),
    ("A17", "ARMCD-ARM not one-to-one", "DM",
     "ARMCD and ARM in DM do not have a one-to-one relationship",
     "ARMCD='A' maps to ARM='Treatment A' and 'Treatment B'",
     "gap_rules_bucket2", "CORE-000318", "yes", "no", "L1", "yes", "tbd"),
    # A18–A20: RECIST v2 extensions (Ming B.7, B.8, B.11)
    ("A18", "Non-target overall response misclassification", "RS,TR",
     "Non-target overall response in RS contradicts individual non-target lesion assessments in TR",
     "TR shows 'UNEQUIVOCAL PROGRESSION'; RS non-target='STABLE'",
     "recist_extension", "none", "no", "tbd", "L2", "yes", "tbd"),
    ("A19", "Table 7 overall response contradiction", "RS,TR,TU",
     "Overall response contradicts the combined target + non-target + new-lesion status per RECIST Table 7",
     "Target=PR, Non-target=SD, No new lesion; RSORRES='CR'",
     "recist_extension", "none", "no", "tbd", "L2", "yes", "tbd"),
    ("A20", "iRECIST immune PD confirmation failure", "RS,TR,TU",
     "Immune-related PD flagged but no confirmation scan >=4 weeks later per iRECIST",
     "iRECIST PD at V5; no follow-up scan within 4+ weeks",
     "recist_extension", "none", "no", "tbd", "L2", "yes", "tbd"),
)


def build_md(seeds: tuple, date: str) -> str:
    """Render markdown catalog with one H3 per archetype."""
    lines = [
        "# Gate B — Contradiction Archetype Catalog",
        f"Generated: {date} | Count: {len(seeds)}",
        "",
    ]
    for s in seeds:
        card = dict(zip(FIELDS, s))
        lines.append(f"### {card['archetype_id']} — {card['name']}")
        for f in FIELDS:
            if f not in ("archetype_id", "name"):
                lines.append(f"- **{f}**: {card[f]}")
        lines.append("")
    return "\n".join(lines) + "\n"


def build_csv(seeds: tuple, path: Path) -> None:
    """Write flattened CSV for downstream T3.2/T3.3 consumption."""
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(FIELDS)
        for s in seeds:
            w.writerow(s)


def main() -> None:
    ap = argparse.ArgumentParser(description="Build Gate B archetype catalog")
    ap.add_argument("--date", required=True, help="Generation date YYYY-MM-DD")
    ap.add_argument("--out-dir", default="gate_b")
    args = ap.parse_args()
    out = Path(args.out_dir)
    out.mkdir(exist_ok=True)
    (out / "archetypes.md").write_text(build_md(SEEDS, args.date), encoding="utf-8")
    build_csv(SEEDS, out / "archetypes.csv")
    print(f"wrote {out / 'archetypes.md'} ({len(SEEDS)} archetypes)")
    print(f"wrote {out / 'archetypes.csv'}")


if __name__ == "__main__":
    main()
