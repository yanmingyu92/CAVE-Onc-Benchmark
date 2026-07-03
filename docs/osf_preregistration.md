# CAVE-Onc Pre-Registration Protocol

**Protocol version:** 1.0  
**Date frozen:** 2026-05-06  
**Registration target:** Open Science Framework (osf.io)

---

## 1. Study Information

**Title:** CAVE-Onc: A Graph-Constrained Agentic Validation Engine for CDISC Oncology Submissions

**Description:** This study evaluates CAVE-Onc, a 2-layer validation system combining SHACL graph-shape validation (L1) with a LangGraph-based agentic orchestrator (L3), against the CDISC Rules Engine (CORE) industry baseline. The system targets RECIST 1.1 oncology domains (TU/TR/RS/EX/DM) and aims to detect cross-domain clinical contradictions that imperative rule engines structurally cannot express.

**Research question:** Anchored to the CORE rule corpus for TU/TR/RS/EX/DM, can a graph-constrained agentic validator (i) characterize the complementarity between declarative SHACL shapes and CORE's imperative rule engine, and (ii) detect cross-domain clinical contradictions in CDISC SDTM oncology submissions that CORE and Pinnacle 21 structurally cannot express, with bounded throughput cost and a tamper-evident audit trail compatible with 21 CFR Part 11?

---

## 2. Hypotheses

### H1 — Rule-class complementarity (Track A)
CAVE L1 SHACL shapes and CORE operate on largely distinct rule classes. The Jaccard similarity of their flag sets on clean data, computed over (USUBJID, rule_id) tuples on oncology-scoped domains, is expected to be low (< 0.10), reflecting complementary — not redundant — coverage.

- **Metric:** Jaccard(L1_flags, CORE_flags) on (USUBJID, rule_id) pairs
- **Pilot result:** Jaccard = 0.004, 24 overlapping pairs, 2/18 CORE rules at 100% recall
- **Interpretation:** Low Jaccard confirms the systems check different aspects of data quality

### H2 — CAVE novelty (Track B)
CAVE detects at least one class of cross-domain contradiction that CORE structurally cannot express, as measured by CAVE-only catches (flags with `core_rule_xref == []`) on the injected archetype corpus.

- **Metric:** Number of archetypes with CAVE-only detection > 0
- **Threshold:** ≥ 1 archetype detected by CAVE but not by CORE
- **Pilot result:** 1/20 archetypes detected (A16 duplicate USUBJID via L1)

### H3 — Agent layer value (L3 contribution)
The L3 agent layer adds detection capability beyond L1 SHACL alone, specifically for A19 (RECIST Table 7 overall response verification), which requires multi-domain reasoning not expressible as SHACL property constraints.

- **Metric:** L3-only detection count on A19-injected data
- **Threshold:** ≥ 1 L3 trace emitted for A19
- **Prerequisite:** RS dataset must contain NTOVRLRESP and NEWLEC test codes (see §6 Known Limitations)
- **Pilot result:** L3 detection proven in unit test with augmented RS data; 0/1 on pharmaversesdtm demo data (missing test codes)

### H4 — Runtime efficiency
Full CAVE pipeline (L1 + L3) completes within 10× CORE wall-clock time on scoped oncology domains for datasets ≤ 10,000 subjects.

- **Metric:** Median wall-clock ratio (CAVE / CORE) across 3 runs
- **Threshold:** ≤ 10.0
- **Note:** Not tested in pilot; to be measured in P8

---

## 3. Frozen Archetype Catalog

20 contradiction archetypes enumerated in Gate B (closed 2026-05-04). Full catalog at `gate_b/archetypes.csv`.

| ID | Name | Domains | Layer | CORE Xref |
|----|------|---------|-------|-----------|
| A01 | SLD decrease ≥30% with RSORRES=PD | RS, TR, TU | L1 | RECIST_1_1_S3 |
| A02 | New lesion without RS escalation | RS, TU | L1 | RECIST_1_1_S6 |
| A03 | EX start after attributed AE | AE, EX | L1 | none |
| A04 | Visit-window violation propagated | EX, RS, TR | L1 | none |
| A05 | Conflicting demographics DM vs SUPPDM | DM, SUPPDM | L1 | none |
| A06 | Non-target PD with RS=SD | RS, TR | L1 | none |
| A07 | Confirmed PR without confirmation visit | RS | L1 | RECIST_1_1_S7 |
| A08 | ARMCD not in TA valueset | DM | L1 | CORE-000210 |
| A09 | Assigned subject missing disposition | DM | L1 | CORE-000296 |
| A10 | RFXSTDTC mismatch with earliest EXSTDTC | DM, EX | L1 | CORE-000239 |
| A11 | RFXENDTC mismatch with latest EXENDTC | DM, EX | L1 | CORE-000238 |
| A12 | Death flag without death details | DM | L1 | CORE-000108 |
| A13 | RACE=MULTIPLE without SUPPDM records | DM, SUPPDM | L1 | CORE-000846 |
| A14 | Assigned arm but no exposure record | DM, EX | L1 | CORE-000366 |
| A15 | RFSTDTC mismatch with first EXSTDTC | DM, EX | L1 | CORE-001044 |
| A16 | Duplicate USUBJID across studies | DM | L1 | CORE-000351 |
| A17 | ARMCD-ARM not one-to-one | DM | L1 | CORE-000318 |
| A18 | Non-target overall response misclassification | RS, TR | L1 | none |
| A19 | Table 7 overall response contradiction | RS, TR, TU | **L3** | none |
| A20 | iRECIST immune PD confirmation failure | RS, TR, TU | L1 | none |

**Architecture note:** L2 (probabilistic DAG) was dropped per T3.3 decision (only 1/20 archetypes required probabilistic reasoning, below the 10-archetype threshold). A19 was rerouted to L3 (deterministic agent logic).

---

## 4. Datasets

### Clean reference data
| Dataset | Source | Subjects | SHA-256 |
|---------|--------|----------|---------|
| pharmaversesdtm RECIST (TU/TR/RS) | CRAN pharmaversesdtm package | 6 | See `data/manifest.json` |
| CDISC Pilot 1 (DM/EX/RELREC) | cdisc-org/sdtm-adam-pilot-project | 52 | See `data/manifest.json` |

### Injected contradiction corpus
Generated by `bench/injector.py` (20 archetypes × N subjects per archetype). RELREC integrity preserved — structural validators (P21/CORE) produce no additional structural errors on injected data.

---

## 5. Statistical Analysis Plan

See companion document `docs/statistical_analysis_plan.md` for full details.

### Primary analyses
1. **Track A (complementarity):** Compute Jaccard similarity between CAVE L1 and CORE flag sets on clean data. Report per-rule recall for all firing CORE rules. No hypothesis test — descriptive comparison.

2. **Track B (novelty):** For each archetype, compute detection status (detected/not) for each baseline (CAVE full, B3 L1-only, B2 CORE). Paired comparison via McNemar's exact test.

### Multiple comparison correction
- Family: 3 baselines × 20 archetypes = 60 paired tests
- Method: Holm-Bonferroni sequential correction
- Family-wise α = 0.05

### Effect sizes
- Bootstrap 95% CIs (n=1000) for per-archetype detection rates
- Overall detection rate with exact binomial CI

### Ablation
- L1-only vs L1+L3 (isolates agent contribution)
- Primary test case: A19 (only archetype requiring L3)

---

## 6. Known Limitations (Pre-registered)

1. **CORE-ported SHACL shapes are structural/metadata checks.** The 85 CORE-ported shapes check field-level constraints (length limits, required fields, arm consistency). They were NOT designed to detect the 20 contradiction archetypes, which are semantic-level clinical inconsistencies. The P6 pilot detection rate of 1/20 reflects this design gap, not a system failure.

2. **A19 L3 detection requires specific RS test codes.** The L3 agent (CaveAgent) performs RECIST Table 7 lookup using OVRLRESP (target), NTOVRLRESP (non-target), and NEWLEC (new lesion) test codes. The pharmaversesdtm demo dataset only contains OVRLRESP. P8 benchmarking with enriched RS data is required for A19 evaluation.

3. **L2 (DAG) layer dropped.** The 2-layer architecture (L1 SHACL + L3 Agent) reflects the T3.3 decision. Causal DAG reasoning is deferred to v2.

4. **B1 (P21) and B4 (Isolation Forest) baselines are stubs.** Only B2 (CORE CLI) and B3 (L1-only) are functional baselines for P8.

5. **Synthetic contradiction corpus.** All contradictions are injected into clean demo data, not sourced from real FDA submissions. Clinical ecological validity is mitigated by archetype review with a domain expert.

6. **Single therapeutic area.** Results are specific to RECIST 1.1 oncology (TU/TR/RS/EX/DM). Generalization to iRECIST, hematological response criteria, or non-oncology domains is future work.

---

## 7. Transparency and Data Availability

- **Code:** Full source code available at [repository URL — to be added after anonymization]
- **Data:** All benchmark datasets are open-source (pharmaversesdtm, CDISC Pilot 1)
- **Injector:** `bench/injector.py` with unit tests; reproducible corpus generation
- **Audit trail:** All validation traces stored in tamper-evident SQLite WAL + Merkle hash chain

---

## 8. Timeline

| Phase | Description | Status |
|-------|-------------|--------|
| P0–P4 | Infrastructure + Gate A/B | ✅ Complete |
| P5 | Layer implementation (L1+L3) | ✅ Complete |
| P6 | Evaluation harness + pilot results | ✅ Complete |
| **P7** | **OSF pre-registration (this document)** | **Current** |
| P8 | Extended benchmarking | Planned |
| P9 | Manuscript submission | Planned |
