# CAVE-Onc: Graph-Constrained Agentic Validation for CDISC Oncology Submissions

**Pre-registration protocol for OSF**

---

## Abstract

CAVE-Onc is a 2-layer validation engine that combines SHACL graph-shape validation (L1) with a LangGraph-based agentic orchestrator (L3) to detect cross-domain clinical contradictions in CDISC SDTM oncology submissions. This pre-registration documents four hypotheses evaluated against the CDISC Rules Engine (CORE) baseline: (H1) rule-class complementarity measured by Jaccard similarity on clean data, (H2) CAVE-only novelty on 20 frozen contradiction archetypes, (H3) agent-layer value on RECIST Table 7 verification, and (H4) runtime efficiency within 10x of CORE wall-clock time. The evaluation targets RECIST 1.1 oncology domains (TU/TR/RS/EX/DM) using open-source benchmark datasets.

## File Manifest

| File | Description |
|------|-------------|
| `osf_preregistration.md` | Full pre-registration protocol with 4 hypotheses, frozen archetype catalog, datasets, statistical analysis plan, and known limitations |
| `statistical_analysis_plan.md` | Detailed SAP: McNemar's exact test, Holm-Bonferroni correction (60 comparisons), bootstrap CIs, ablation design |
| `frozen_archetype_list.csv` | 20 contradiction archetypes (A01–A20) frozen at Gate B close (2026-05-04) |
| `osf_project_readme.md` | This file — project overview and file manifest |
| `data_integrity_manifest.json` | SHA-256 hashes and sizes for all frozen artifacts |

## Repository

- **Anonymized source code:** [repository URL — to be added after anonymization]
- **Data:** All benchmark datasets are open-source (pharmaversesdtm CRAN package, CDISC Pilot 1)

## License

MIT License. See repository for full text.
