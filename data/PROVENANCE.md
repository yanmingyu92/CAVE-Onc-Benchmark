# Data Provenance

All corpora are **public or synthetic**. No sponsor-internal data is included.

---

## pilot1 — CDISC SDTM Pilot 1

- **Source URL:** <https://github.com/cdisc-org/sdtm-adam-pilot-project>
  (path: `updated-pilot-submission-package/900172/m5/datasets/cdiscpilot01/tabulations/sdtm/`)
- **Files:** 18 XPT (ae, cm, dm, ds, ex, mh, relrec, sc, se, suppae, suppdm, suppds, sv, ta, te, ti, ts, tv). The four large domains not used by this RECIST oncology benchmark — `lb` (labs), `qs` (questionnaires), `supplb`, `vs` (vitals) — were omitted from this release to keep the repository lightweight; retrieve them from the source URL above if needed. The engine uses only DM/EX/TU/TR/RS/AE/DS/TA/SUPPDM (+ RS/TR/TU from pharmaversesdtm).
- **Subjects:** ~306 (DM domain)
- **Retrieval date:** 2026-05-01
- **License:** CDISC public data — "clinical test data for informational purposes and the convenience of the public"
- **Notes:** Files downloaded verbatim from the cdisc-org GitHub repository via raw.githubusercontent.com.
  The `ts.xpt` file uses Windows-1252 encoding (byte `0x92` in TSVAL); `pyreadstat.read_xport(encoding='latin1')` is required.

---

## pharmaversesdtm_onco — Pilot 7 Substitute (pharmaversesdtm oncology general)

- **Status:** NOT_AVAILABLE (CDISC "Pilot 7" does not exist as a public resource).
  Searched cdisc-org GitHub organization, cdisc.org standards pages, and CRAN/package registries.
  No "Pilot 7" numbered dataset was found. Substituted per T2 substitution rule.
- **Substitute source:** `pharmaversesdtm` R package, oncology general datasets (`tu_onco`, `tr_onco`, `rs_onco`).
- **Package version:** pharmaversesdtm 1.4.1 (CRAN, 2026-03-31)
- **Package URL:** <https://github.com/pharmaverse/pharmaversesdtm>
- **Export method:** `Rscript scripts/export_pharmaversesdtm.R onco` using `haven::write_xpt(version=5)`
  with rows sorted by `(USUBJID, VISITNUM, <domain>SEQ)`.
- **Files:** 3 XPT (tu, tr, rs)
- **Subjects:** 254 (TU domain), 205 (RS domain)
- **Retrieval date:** 2026-05-01
- **Notes:** These datasets are synthetic/oncology-specific test data from the pharmaverse ecosystem.
  They differ from the RECIST-specific subsets in `pharmaversesdtm_recist/` (larger subject count,
  broader oncology scope). Some USUBJIDs may overlap with the RECIST subset.

---

## pharmaversesdtm_recist — RECIST 1.1 Oncology Response

- **Source:** `pharmaversesdtm` R package, RECIST-specific datasets
  (`tu_onco_recist`, `tr_onco_recist`, `rs_onco_recist`).
- **Package version:** pharmaversesdtm 1.4.1 (CRAN, 2026-03-31)
- **Package URL:** <https://github.com/pharmaverse/pharmaversesdtm>
- **Export method:** `Rscript scripts/export_pharmaversesdtm.R recist` using `haven::write_xpt(version=5)`
  with rows sorted by `(USUBJID, VISITNUM, <domain>SEQ)`.
- **Files:** 3 XPT (tu, tr, rs)
- **Subjects:** 8
- **Retrieval date:** 2026-05-01
- **Notes:** These are the RECIST 1.1 specific test datasets. They serve as the oncology-specific
  positive control for Gate E (agent eval, T7.x). Rows are deterministically sorted for byte-stable output.

---

## real_oncology_data — Project Data Sphere (PDS) real-world trials (Item E)

- **Status:** RAW DATA NOT COMMITTED. The directory `data/real_oncology_data/` is
  gitignored under sponsor data-use terms. Committed provenance:
  `gate_a/real_data_manifest.sha256` (155-file SHA-256 manifest) and
  `gate_a/real_data_inventory.csv` (column/label inventory, 138 datasets).
- **Source:** Project Data Sphere (<https://data.projectdatasphere.org>) — de-identified
  comparator-arm oncology trial data shared for secondary research.
- **Packages (5):** 107 CA012 (mBC), 108 CA031 (NSCLC), 114 A6181122,
  123 Synta 4783-08, 158 C40502 (mBC).
- **Format:** legacy sponsor-defined `.sas7bdat` (4 trials) + `.csv` (158) —
  **not SDTM**; requires per-trial legacy->SDTM (TU/TR/RS) mapping before ingestion.
- **Retrieval date:** 2026-06-17
- **License/terms:** PDS Data Use Agreement — secondary research use; no
  redistribution of raw subject-level data. Manifest + inventory only in git.
- **Usage:** drives the Item E real-world validation. See
  `docs/item_e_real_data_plan.md` for the usability evaluation and mapping plan.
  Entry point trial: **123 Synta** (explicit lesion linkage, full RECIST response).
