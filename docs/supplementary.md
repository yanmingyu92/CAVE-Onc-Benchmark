# Supplementary Materials — CAVE-Onc

> **Provenance note.** This is an internal working superset of supplementary analyses and uses its own
> table numbering. The **submitted** supplement is `docs/latex/plos_submission/S1_File.tex` (compiled to
> `S1_File.pdf`), which contains Tables **S1–S10** in the exact order referenced by the manuscript
> (S8 = Scaling Analysis, S9 = LLM Verification Agreement Matrix, S10 = Uncertainty Triage Consensus).
> Where numbering differs, **S1_File.tex is authoritative** for anything cited in the manuscript. The
> additional tables here (per-reviewer expert ratings, explainability Likert, negative-delta methodology)
> are extra detail not carried into the submitted PDF.

---

## Table S1: Full 20-Archetype Contradiction Catalog

| ID | Name | Domains | Pattern Description | Layer | CORE Xref |
|----|------|---------|-------------------|-------|-----------|
| A01 | SLD decrease >=30% with RSORRES=PD | RS, TR, TU | Tumor SLD down >=30% but RSORRES = "PD" at same visit | L1 | RECIST_1_1_S3 |
| A02 | New lesion without RS escalation | RS, TU | New lesion (TU.TULNKID added) without RS escalation at corresponding visit | L1 | RECIST_1_1_S6 |
| A03 | EX start after attributed AE | AE, EX | Exposure start date after adverse event attributed to the treatment | L1 | none |
| A04 | Visit-window violation propagated | EX, RS, TR | Visit window violation propagated across TR/RS/EX domains | L1 | none |
| A05 | Conflicting demographics DM vs SUPPDM | DM, SUPPDM | USUBJID with conflicting sex/age across DM and SUPPDM | L1 | none |
| A06 | Non-target PD with RS=SD | RS, TR | Non-target lesion PD without target lesion change but RS = SD | L1 | none |
| A07 | Confirmed PR without confirmation visit | RS | Confirmed PR without required confirmation visit within 28 days | L1 | RECIST_1_1_S7 |
| A08 | ARMCD not in TA valueset | DM | ACTARMCD or ARMCD in DM not present in TA.ARMCD codelist | L1 | CORE-000210 |
| A09 | Assigned subject missing disposition | DM | Subject with populated ACTARMCD has no disposition record in DS | L1 | CORE-000296 |
| A10 | RFXSTDTC mismatch with earliest EXSTDTC | DM, EX | DM.RFXSTDTC does not equal earliest EX.EXSTDTC for the subject | L1 | CORE-000239 |
| A11 | RFXENDTC mismatch with latest EXENDTC | DM, EX | DM.RFXENDTC does not equal latest EX.EXENDTC for the subject | L1 | CORE-000238 |
| A12 | Death flag without death details | DM | DM.DTHFL='Y' but no corresponding record in DD dataset | L1 | CORE-000108 |
| A13 | RACE=MULTIPLE without SUPPDM records | DM, SUPPDM | DM.RACE='MULTIPLE' but SUPPDM has <2 multiple-race records | L1 | CORE-000846 |
| A14 | Assigned arm but no exposure record | DM, EX | Subject assigned to treatment arm (ACTARMCD populated) but no EX record | L1 | CORE-000366 |
| A15 | RFSTDTC mismatch with first EXSTDTC | DM, EX | DM.RFSTDTC does not equal the first EX.EXSTDTC for the subject | L1 | CORE-001044 |
| A16 | Duplicate USUBJID across studies | DM | USUBJID appears more than once in DM across all studies | L1 | CORE-000351 |
| A17 | ARMCD-ARM not one-to-one | DM | ARMCD and ARM in DM do not have a one-to-one relationship | L1 | CORE-000318 |
| A18 | Non-target overall response misclassification | RS, TR | Non-target overall response in RS contradicts individual non-target assessments in TR | L1 | none |
| A19 | Table 7 overall response contradiction | RS, TR, TU | Overall response contradicts the combined target + non-target + new-lesion status per RECIST Table 7 | **L3** | none |
| A20 | iRECIST immune PD confirmation failure | RS, TR, TU | Immune-related PD flagged but no confirmation scan >=4 weeks later per iRECIST | L1 | none |

---

## Table S2: SHACL Shape Porting Statistics

### Overall porting summary

| Metric | Value |
|--------|-------|
| Total CORE rules in scope (TU/TR/RS/EX/DM) | 122 |
| Classified as single-domain (portable) | 85 |
| Classified as cross-domain (unportable) | 37 |
| Port success rate | 69.7% |
| Expressiveness compromises | 0/85 |
| RECIST derivation shapes (authored, not CORE-sourced) | 8 |
| Archetype-specific SHACL-SPARQL shapes (cross-domain) | 18 |
| **Total published L1 shapes** | **111** |

### Per-domain porting breakdown

| Domain | Inventory Rules | Classified Single-Domain | Published Shapes | Port Rate |
|--------|----------------|-------------------------|-----------------|-----------|
| TU | 0 | 0 | 0 | — |
| TR | 4 | 4 | 4 | 100.0% |
| RS | 2 | 2 | 2 | 100.0% |
| EX | 7 | 5 | 5 | 71.4% |
| DM | 109 | 74 | 74 | 67.9% |
| **Total** | **122** | **85** | **85** | **69.7%** |

### Port-kind distribution

| Transformation | Count | Share of 85 | Share of 122 |
|---------------|-------|------------|-------------|
| De Morgan expansion | 50 | 58.8% | 41.0% |
| Polarity flip | 30 | 35.3% | 24.6% |
| No change | 5 | 5.9% | 4.1% |

### Unportable rule buckets

| Bucket | Sub-category | Count |
|--------|-------------|-------|
| Cross-domain joins | Valueset | 7 |
| Cross-domain joins | Existence | 2 |
| Cross-domain joins | Aggregate | 4 |
| Cross-domain joins | Computed | 18 |
| Row-set uniqueness | — | 6 |
| **Total unportable** | | **37** |

---

## Table S3: Per-Rule Recall for All 18 CORE Rules (Track A)

| CORE Rule | CORE Flag Count | L1 Flag Count | Recall | Domain | Rule Description (inferred) |
|-----------|----------------|--------------|--------|--------|---------------------------|
| CORE-000047 | 52 | 0 | 0.0 | DM | DM field-level conformance |
| CORE-000108 | 1 | 0 | 0.0 | DM | Death flag without death details |
| CORE-000115 | 52 | 0 | 0.0 | DM | DM variable presence/format |
| CORE-000191 | 52 | 0 | 0.0 | DM | DM variable presence/format |
| CORE-000208 | 52 | 0 | 0.0 | DM | ARMCD valueset conformance |
| CORE-000209 | 52 | 0 | 0.0 | DM | ARMCD valueset conformance |
| CORE-000210 | 52 | 0 | 0.0 | DM | ARMCD valueset conformance |
| CORE-000334 | 1 | 0 | 0.0 | DM | DM field-level conformance |
| CORE-000358 | 2 | 0 | 0.0 | DM | DM field-level conformance |
| CORE-000529 | 1 | 0 | 0.0 | DM | DM field-level conformance |
| CORE-000571 | 2 | 0 | 0.0 | DM | DM field-level conformance |
| **CORE-000655** | **12** | **306** | **1.0** | **DM** | **Arm assignment consistency** |
| **CORE-000656** | **12** | **306** | **1.0** | **DM** | **Arm assignment consistency** |
| CORE-000701 | 591 | 0 | 0.0 | EX | EX controlled terminology |
| CORE-000757 | 1 | 0 | 0.0 | DM | DM field-level conformance |
| CORE-000767 | 2 | 0 | 0.0 | DM | DM field-level conformance |
| CORE-000929 | 2 | 0 | 0.0 | DM | DM field-level conformance |
| CORE-001081 | 2 | 0 | 0.0 | DM | DM field-level conformance |

**Summary:** 2/18 rules at recall = 1.0; 16/18 rules at recall = 0.0. Rules at perfect recall (CORE-000655, CORE-000656) both address arm assignment consistency, where L1 SHACL shapes encode equivalent structural constraints.

---

## Table S4: Per-Archetype Detailed Results (Track B Final)

| ID | Detected | Detection Source | L1 Flag Delta | L3 Traces | Description |
|----|----------|-----------------|--------------|-----------|-------------|
| **A01** | **Yes** | **L1** | **+3** | 0 | SLD ≥30% decrease but RSORRES=PD |
| **A02** | **Yes** | **L1** | **+1** | 0 | New lesion T09 at V2, RS=SD |
| **A03** | **Yes** | **L1** | **+3** | 0 | EX start 14d after AE onset |
| **A04** | **Yes** | **L1** | **+5** | 0 | Fractional VISITNUM (visit misalignment) |
| **A05** | **Yes** | **L1** | **+1** | 0 | SUPPDM vs DM sex conflict |
| **A06** | **Yes** | **L1** | **+36** | 0 | Non-target PD but RS=SD |
| **A07** | **Yes** | **L1** | **+3** | 0 | PR without 28d confirmation |
| **A08** | **Yes** | **L1** | **+1** | 0 | ARMCD not in TA |
| **A09** | **Yes** | **L1** | **+1** | 0 | Missing DS for assigned subject |
| **A10** | **Yes** | **L1** | **+1** | 0 | RFXSTDTC derivation mismatch |
| **A11** | **Yes** | **L1** | **+1** | 0 | RFXENDTC derivation mismatch |
| **A12** | **Yes** | **L1** | **+1** | 0 | DTHFL=Y without death DS |
| **A13** | **Yes** | **L1** | **+1** | 0 | RACE=MULTIPLE without SUPPDM |
| **A14** | **Yes** | **L1** | **−1** | 0 | Missing EX for assigned subject |
| **A15** | **Yes** | **L1** | **+1** | 0 | RFSTDTC derivation mismatch |
| **A16** | **Yes** | **L1** | **+16** | 0 | Duplicate USUBJID across studies |
| **A17** | **Yes** | **L1** | **+86** | 0 | ARMCD→ARM not 1:1 |
| **A18** | **Yes** | **L1** | **+36** | 0 | Non-target response misclassification |
| **A19** | **Yes** | **L3** | **0** | **1** | Table 7 contradiction (CR ≠ expected) |
| **A20** | **Yes** | **L1** | **+1** | 0 | iCPD without ≥4wk confirmation |

**Summary statistics:**
- L1 detection rate: 19/20 (95%)
- L3 detection rate: 1/20 (5%)
- CAVE detection rate: **20/20 (100%)**
- CAVE-only catches: [A19]
- 95% CI (Clopper-Pearson): [83.2%, 100.0%]
- McNemar p-value (CAVE vs CORE): p < 0.001
- Clean baseline: 5,957 L1 violations

---

## Table S5: Archetype Shape False Positive Analysis on Clean Data

Three of 18 archetype-specific SHACL-SPARQL shapes initially produced violations on the clean (unmutated) reference dataset. Shape A03 was refined in v2 with a 7-day temporal gap threshold. In v3, shapes A01 and A07 were further refined: A01 now requires same-lesion TRLNKID comparison (reducing cross-lesion LDIAM matches from 4 to 2), and A07 excludes the subject's last visit (where no confirmation is possible).

| Shape | Clean FP (v1) | Clean FP (v2) | Clean FP (v3) | Mutated Violations | Delta | Change | Cause |
|-------|:---:|:---:|:---:|:---:|:---:|--------|-------|
| **A01** | 4 | 4 | **2** | 5 | +3 | ↓ (v3: TRLNKID constraint) | v3 eliminates cross-lesion matches; 2 remaining are genuine same-lesion PD-at-shrinkage contradictions in reference data (subject 01-701-1028, V3/V5) |
| **A03** | 146 | 121 | **121** | 124 | +3 | ↓ (v2: 7-day filter) | v2 requires EX start >7 days after AE onset; short-gap overlaps remain |
| **A07** | 4 | 4 | **0** | 3 | +3 | ↓ (v3: exclude last visit) | v3 excludes PR at subject's final visit where no confirmation possible |
| A02 | 0 | 0 | 0 | ≥1 | +1 | — | No FP |
| A04–A20 (other 15) | 0 | 0 | 0 | ≥1 each | +1 to +86 | — | No FP |

**Total clean-data violations from archetype shapes**: 123 (v3, down from 154 in v1 and 129 in v2). Of these, 121 are A03 temporal overlaps and 2 are A01 genuine same-lesion PD-at-shrinkage contradictions in the pharmaversesdtm reference data. Does not include CORE-ported shape violations in the 5,932 baseline.

**Note on A01 clean-data violations**: The 2 remaining A01 violations represent genuine RECIST inconsistencies in the reference dataset where RSORRES=PD is recorded at a visit where same-lesion LDIAM decreased ≥30% from a prior visit. These are *true positives on clean data* rather than shape logic errors — the reference data contains real cross-domain contradictions that the A01 shape correctly identifies.

**Note on detection methodology**: The delta-based detection method (Δ = mutated_L1 − clean_L1) is used for Track B evaluation. Because the same shapes fire on both clean and mutated data, the false positives cancel in the delta calculation, and detection relies only on the *incremental* violations caused by the mutation. In production deployment where absolute violation counts are used, shapes A01 and A03 would require further specificity refinement or protocol-specific configuration.

---

## Table S6: 21 CFR Part 11 Compatibility Checklist

CAVE-Onc provides an audit trail *foundation* compatible with 21 CFR Part 11 requirements. The following checklist evaluates the current implementation against the 14 key Part 11 requirements. Items marked "Foundation" are partially implemented; "Out of scope" items require additional engineering for full compliance.

| # | Part 11 Requirement | CAVE-Onc Implementation | Status |
|---|---------------------|------------------------|--------|
| 1 | **Audit trail** — record creation, modification, deletion of electronic records | SQLite WAL append-only store; every TraceEntry logged with timestamp | ✅ Implemented |
| 2 | **Tamper evidence** — detect unauthorized modifications | Merkle hash chain linking consecutive TraceEntry records; SHA-256 per entry | ✅ Implemented |
| 3 | **Record integrity** — ensure data has not been altered | `entry_hash` (SHA-256 of canonicalized entry) + `prev_hash` chain | ✅ Implemented |
| 4 | **Timestamp accuracy** — independent, reliable timestamps | ISO 8601 UTC timestamps from system clock; no NTP sync verification | ⚠️ Foundation |
| 5 | **User attribution** — identify who performed each action | `layer` field (L1/L3) recorded; no user identity or login | ⚠️ Foundation |
| 6 | **Electronic signatures** — legally binding, linked to records | Not implemented | ❌ Out of scope |
| 7 | **Signature manifestation** — printed name, date/time, meaning | Not implemented | ❌ Out of scope |
| 8 | **Signature linking** — signatures bound to respective records | Not implemented | ❌ Out of scope |
| 9 | **Access controls (RBAC)** — limit access to authorized individuals | No RBAC; all operations run as local process | ❌ Out of scope |
| 10 | **Operational system checks** — enforce permitted sequencing of steps | Pipeline enforces L1→L3 order; no user-workflow enforcement | ⚠️ Foundation |
| 11 | **Authority checks** — ensure only authorized individuals can use the system | No authentication; local execution only | ❌ Out of scope |
| 12 | **Device checks** — verify source of data input | XPT file SHA-256 checksums in `data/MANIFEST.sha256` | ⚠️ Foundation |
| 13 | **Training documentation** — personnel training records | Not applicable for research prototype | ❌ Out of scope |
| 14 | **Validation documentation (IQ/OQ/PQ)** — documented evidence that system meets requirements | 125 automated tests; reproducibility crosscheck script; no formal IQ/OQ/PQ | ⚠️ Foundation |

**Summary**: 3/14 fully implemented, 4/14 foundation level, 7/14 out of scope for this research prototype. Full Part 11 compliance requires e-signatures, RBAC, and IQ/OQ/PQ validation documentation.

---

## Table S7: Bootstrap Confidence Intervals

Bootstrap 95% CIs (n=1,000 resamples, seed=42) for primary metrics:

| Metric | Point Estimate | Bootstrap 95% CI | Clopper-Pearson 95% CI |
|--------|---------------|-------------------|----------------------|
| Detection rate | 100.0% (20/20) | [100.0%, 100.0%] | [83.2%, 100.0%] |
| F1 score | 1.000 | [1.000, 1.000] | — |

Note: With perfect detection (20/20), bootstrap CIs are degenerate at 100%. The Clopper-Pearson exact binomial CI provides a more conservative estimate accounting for the finite sample size.

---

## Table S8: Expert Archetype Validity Ratings (G8)

Three domain experts independently rated each archetype as valid, invalid, or uncertain. Fleiss' κ = 0.705 (substantial agreement). No archetype was rated invalid by any reviewer.

| ID | Archetype | R1 | R2 | R3 | Consensus | Agreement |
|----|-----------|:--:|:--:|:--:|-----------|:---------:|
| A01 | SLD decrease ≥30% with RSORRES=PD | V | V | U | Valid | 67% |
| A02 | New lesion without RS escalation | V | V | V | Valid | 100% |
| A03 | EX start after attributed AE | V | V | V | Valid | 100% |
| A04 | Visit-window violation propagated | U | U | U | Uncertain | 100% |
| A05 | Conflicting demographics DM vs SUPPDM | V | V | V | Valid | 100% |
| A06 | Non-target PD with RS=SD | V | V | V | Valid | 100% |
| A07 | Confirmed PR without confirmation visit | U | U | U | Uncertain | 100% |
| A08 | ARMCD not in TA valueset | V | V | V | Valid | 100% |
| A09 | Assigned subject missing disposition | V | V | V | Valid | 100% |
| A10 | RFXSTDTC mismatch with earliest EXSTDTC | V | V | V | Valid | 100% |
| A11 | RFXENDTC mismatch with latest EXENDTC | V | V | V | Valid | 100% |
| A12 | Death flag without death details | V | U | U | Uncertain | 67% |
| A13 | RACE=MULTIPLE without SUPPDM records | V | V | V | Valid | 100% |
| A14 | Assigned arm but no exposure record | V | V | U | Valid | 67% |
| A15 | RFSTDTC mismatch with first EXSTDTC | V | V | V | Valid | 100% |
| A16 | Duplicate USUBJID across studies | V | V | V | Valid | 100% |
| A17 | ARMCD-ARM not one-to-one | V | V | V | Valid | 100% |
| A18 | Non-target overall response misclassification | V | V | V | Valid | 100% |
| A19 | Table 7 overall response contradiction | V | V | V | Valid | 100% |
| A20 | iRECIST immune PD confirmation failure | U | U | U | Uncertain | 100% |

**Key**: V = valid, U = uncertain. R1/R2/R3 = three independent domain experts, each with ≥10 years of oncology CDISC experience (statistical programming / data-standards review at pharmaceutical or biotech companies); reviewer identities and affiliations are withheld.

**Cross-reviewer consensus**: All reviewers consider the archetype library clinically meaningful. The 4 uncertain archetypes (A04, A07, A12, A20) reflect protocol-dependent interpretation rather than invalidity. Reviewers recommend protocol-level configuration for visit windows, response confirmation requirements, death-record source selection, and iRECIST confirmation rules.

---

## Table S9: Explainability Likert Scores (G9)

| Question | R1 | R2 | R3 | Mean | Median |
|----------|:--:|:--:|:--:|:----:|:------:|
| Trace readability (1–5) | 4 | 4 | 4 | 4.0 | 4 |
| System confidence (1–5) | 4 | 4 | 4 | 4.0 | 4 |

**Scale**: 1 = Incomprehensible/Not useful, 5 = Fully transparent/Essential.

**Common improvement recommendations**: (1) Add subject/visit identifiers and source record references to traces; (2) Include explicit RECIST Table 7 rule row used; (3) Add query result row counts for audit replay; (4) Classify findings by severity tier (hard error vs. review query); (5) State controlled terminology versions; (6) Support protocol-level configuration for exception handling.

---

## Table S10: L1 Scale Benchmark (G3)

L1 SHACL validation was benchmarked at 1x, 5x, and 10x scale by replicating the pharmaversesdtm_recist dataset with unique subject identifiers. All 111 shapes (85 CORE-ported + 8 RECIST derivation + 18 archetype-specific) were applied at each scale.

| Scale | Subjects | RDF Triples | Validation Time (s) | Time/Subject (s) | Ratio vs 1x |
|:-----:|:--------:|:-----------:|:-------------------:|:-----------------:|:-----------:|
| 1x | 8 | 12,463 | 42.2 | 5.28 | 1.00 |
| 5x | 40 | 62,315 | 114.7 | 2.87 | 2.72 |
| 10x | 80 | 124,630 | 326.9 | 4.09 | 7.75 |

**Key findings**:
- **Sub-linear scaling**: 10x data produces only 7.75x wall-clock time, confirming that PySHACL+rdflib validation overhead grows sub-linearly with graph size.
- **Violation stability**: All three scale factors produced exactly 2 violations (the A01 same-lesion contradictions for subject 01-701-1028), confirming that shape behavior is deterministic across replicated graphs.
- **Per-subject time**: Time per subject is not constant due to SPARQL query overhead amortization. The 5x sweet spot (2.87s/subject) suggests batch processing yields efficiency gains.

**Source**: `eval/g3_scale_benchmark.json`, generated by `scripts/run_scale_benchmark.py` (seed=42, pharmaversesdtm_recist base data).

---

## Table S11: Negative-Delta Detection Methodology (A14)

Archetype A14 (Assigned arm but no exposure record) is the only archetype with a **negative** flag delta (Δ = −1). This occurs because the A14 mutation removes EX records for a subject, which simultaneously:

1. **+1**: The A14 shape fires (detecting the assigned subject with no exposure)
2. **−2**: Two EX-dependent shapes (RFXSTDTC/RFXENDTC date derivation checks) lose their trigger because the EX records no longer exist

Net result: 5,956 − 5,957 = **−1**

The detection logic uses `flag_delta != 0` (any non-zero delta indicates detection), which is methodologically sound: any change in the violation landscape after mutation signals that the shapes are sensitive to the injected contradiction. The *direction* of the delta (positive or negative) is not relevant for detection — what matters is that the SHACL validation state changed.

**Verification**: A14 was confirmed as detected in all evaluation runs (P8, Track B). The archetype was also independently rated as "valid" by 2 of 3 expert reviewers (1 uncertain), with the uncertain rating reflecting protocol-dependent interpretation rather than questioning detection validity.

---

*Supplementary materials for: CAVE-Onc: Graph-Constrained Agentic Validation for Cross-Domain Contradictions in CDISC Oncology Submissions. Pre-registered at OSF (https://osf.io/fx2ky), protocol version 1.0, frozen 2026-05-06.*

