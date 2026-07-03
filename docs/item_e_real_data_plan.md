# Item E — Real-World Data Validation Plan (Project Data Sphere)

> Created 2026-06-17. Addresses **Item E** (deferred in `tasks.md`): the real-data
> case study that the PLOS ONE manuscript names as the key next validation step.
> Data access is now granted — 5 PDS oncology trials are present under
> `data/real_oncology_data/`.

---

## 1. What arrived

Five Project Data Sphere trial packages (`data/real_oncology_data/AllProvidedFiles_*`):

| Pkg | Trial | Disease | Format | Datasets | Size |
|-----|-------|---------|--------|----------|------|
| 107 | CA012 | Metastatic breast cancer | `.sas7bdat` | 36 | 33 MB |
| 108 | CA031 | NSCLC | `.sas7bdat` | 40 | 282 MB |
| 114 | A6181122 | (sunitinib RCC/GIST era) | `.sas7bdat` | 20 | 186 MB |
| 123 | Synta 4783-08 | Oncology | `.sas7bdat` | 38 | 124 MB |
| 158 | C40502 | Metastatic breast cancer | `.csv` | 3 | 2.7 MB |

Each package also ships a protocol PDF, annotated CRF PDF, and a data
dictionary / SPECS spreadsheet — usable for authoring the mappings.

## 2. The hard constraint

CAVE-Onc's detection engine (SHACL L1 + LangGraph L3) operates on **SDTM**
`TU` / `TR` / `RS` (+ `DM`/`EX`/`DS`/`TA`/`AE`) read from **`.xpt`** via
`kg/xpt_to_rdf.py`. The 20 archetypes (catalog `gate_a/recist_catalog.csv`,
shapes S1–S8) require specifically:

- `TR.TRSTRESN` per target lesion (longest diameter) + target/non-target grouping
- per-visit `RS.RSORRES` with `RSCAT` ∈ {TARGET, NON-TARGET, OVERALL} RESPONSE
- lesion linkage `TU.TULNKID` ↔ `TR.TRLNKID`; new-lesion appearance via `TU`
- `RSDTC` for the 28-day confirmation rule (S7)
- `DM`/`EX`/`DS`/`TA` for the cross-domain archetypes (A03, A05, A08–A11)

**None of the PDS trials are in SDTM.** They are legacy sponsor-defined
formats (e.g. `wclesion`, `targ`, `lesles`, `tmm_p`; columns `TGTSIZE`,
`LNGDIA`, `ORSP`, `IOTATL`). **The gating effort for the entire study is a
per-trial legacy→SDTM (TU/TR/RS) mapping.** This is itself the realistic,
publishable contribution — it is what a sponsor/CRO does before submission.

## 3. Evaluation — which data is usable (verified by column + label inspection)

RECIST content found per trial (labels confirmed from the `.sas7bdat` metadata):

| Trial | Lesion measurements (→TR/TU) | RECIST response (→RS) | Lesion ID (→TULNKID) | DM/DS/EX present | Verdict |
|-------|------------------------------|------------------------|----------------------|------------------|---------|
| **123 Synta** | `lesles`: `LNGDIA` (longest dia), `DIASUM` (sum), `LESSIT`, `NEWLES` | `rsp`: `TRSP`/`NTRSP`/`ORSP` + `PDSPC1` (new lesion), `PDSPC2` (unequiv. PD) | **`lesles.LESID` (explicit)** | `dm`(TRTP,AGE,SEX,RACE), `ds`(DSDECOD), `ec` | **★ BEST — start here** |
| **107 CA012** | `wclesion`: `TGTSIZE` (LD mm), `LESNUM`, `LESTYPE`, `METHOD`; `wcresp`: `SUMTGT` (SLD), `NUMTGT` | `wcresp`: `ALLRESP`/`TGTRESP`/`NTGTRESP` (derived, clean labels) | `wclesion.LESNUM` | `demo`, `eosr`, `dose` | **★ STRONG — 2nd** |
| **108 CA031** | `lesn` (49k rows): `DIAM`, `SUMDIAM`, `LESNUM`, `LESTYP`, `EVALCODE` | `resp`: `TARGRESP`/`NTRGRESP`/`OVERRESP`, `TUMORPD` | `lesn.LESNUM` (no clean cross-visit link) | `demo`, `eos`, `dose`, `foll` | GOOD — heavier mapping (cryptic CPEVENT/VISIT) |
| **114 A6181122** | `tmm_p`: `TMMDIA`, `TMMNLES`, `TMMSITE`, `LESTYPE` | `iota_p`: `IOTATL`/`IOTANTL`/`IOTAALL` (overall investigator assessment) | none explicit | `demog`, `final`, `random` | USABLE — cryptic, weakest lesion linkage |
| **158 C40502** | none (subject-level only) | `efficacy.csv`: `bestresp` only (1 row/subject) | n/a | subject-level covariates | **✗ NOT SUITABLE** — ADaM-like, no per-visit lesion/response; cannot exercise visit-level archetypes |

**Bottom line:** 4 of 5 trials carry genuine per-visit lesion + RECIST response
data and are usable. **123 (Synta)** is the best entry point: explicit `LESID`
lesion linkage, clean target/non-target/overall response, explicit new-lesion &
unequivocal-PD flags, and it already ships partly SDTM-named (`STUDYID`,
`VISITNUM`, `DSDECOD`). **107** is the strong second (cleanest labels, derived
SLD). **158** is excluded for the contradiction-detection purpose.

## 4. Two scientific uses (both valuable, both gated on §2 mapping)

- **(E1) Naturalistic specificity** — run CAVE-Onc on the *unmutated* mapped
  real data. Does the engine stay quiet (high specificity) on real
  submission-grade data, and does any genuine flag correspond to a real
  data-quality issue? This is the most honest real-world signal and directly
  rebuts "tailored rule-engine" / addresses the "no real-world validation"
  caveat. **Bonus:** real data carries *genuine* `RS` records, so the synthetic
  `_enrich_rs` limitation (baseline Table-7 contradictions on clean data,
  disclosed in Limitations) disappears for this arm.
- **(E2) Mutation transfer / external validity** — re-inject the 20 archetypes
  into the real-data-derived SDTM and confirm detection holds on real data
  structure (not just pharmaverse synthetic). Demonstrates the benchmark
  transfers to real trial topology.

## 5. Forward plan (phased)

### Phase 0 — Provenance & access hygiene (0.5 day) ✅ DONE 2026-06-17
- [x] **Gitignore raw PDS data.** `data/real_oncology_data/` added to
      `.gitignore` (verified: raw `.sas7bdat` ignored; artifacts stageable).
- [x] **Committed provenance:** `gate_a/real_data_manifest.sha256` (155-file
      SHA-256, via `scripts/build_data_manifest.py`) + `data/PROVENANCE.md` entry.
- [x] **Inventory:** `scripts/explore_real_data.py` → `gate_a/real_data_inventory.csv`
      (2464 column rows across 138 datasets).

### Phase 1 — Map ONE trial (123 Synta) to SDTM TU/TR/RS 🟡 IN_PROGRESS (first cut done)
- [x] **`scripts/map_synta_to_sdtm.py`** authored → `data/real_sdtm/synta/{tu,tr,rs,dm,ds}.xpt`
      (gitignored). Output: TU=2300, TR=5302 (LDIAM 3276 + TUMSTATE 2026),
      RS=2265 (TARGET/NON-TARGET/OVERALL RESPONSE + SUMDIAM), DM=325, DS=1173.
      Mappings: `lesles.LESID`→`TULNKID`/`TRLNKID`; `LNGDIA`→`TRSTRESN`(LDIAM);
      `DIASUM`→`RS` SUMDIAM(TARGET); `rsp.{TRSP,NTRSP,ORSP}`→`RSORRES` by `RSCAT`;
      `PT`→`USUBJID`; baseline `VISITNUM=0`→`EPOCH='SCREENING'`.
- [x] **Engine ingestion verified** — `kg.xpt_to_rdf` loads 119,909 triples;
      all shape-required predicates present.
- [x] **XPT-limit fix:** store SDTM-standard `TRGRPID` (8-char) + derive
      `cave:TRTARGETLN` at graph-build via `enrich_recist_graph()` (XPT v5 caps
      names at 8 chars / no boolean — `TRTARGETLN` is 10).
- [x] **`tests/test_map_synta.py`** — 9 invariant tests pass (subject
      conservation, no orphan lesion links, RECIST codelists, SUMDIAM present,
      TRTARGETLN derivation). Skips when gitignored data absent.
- [ ] **Remaining (before Phase 2):** validate mapped `.xpt` against CDISC-CORE
      structural rules; reconcile RSTESTCD codes for non-target/overall vs
      shapes; confirm mapping decisions against the CRF PDF + `Data_dictionary.xlsx`
      (esp. LESCOD location coding, NEWLES→new-lesion TU rows, date reconstruction).
- [ ] **Known limitations to disclose:** no lymph-node short-axis (`LNSADIAM`)
      in Synta → S2 node rule not testable; dates year-only → S7 confirmation
      only partial.

### Phase 2 — E1 naturalistic run on Synta ✅ DONE 2026-06-17 (n=50 subset)
- [x] `scripts/run_e1_real_data.py` runs L1 on unmutated mapped Synta, buckets
      flags (recist_derivation / archetype / core_structural / anon_property).
      Result: `eval/real_data_e1_synta_n50.json`.
- [x] **Full triage → `docs/item_e_e1_findings.md`.** Headline: RECIST-derivation
      shapes are highly specific (20 semantic flags/50 subj, all explainable);
      archetype detectors over-fire (A02: 380) — **verified false positive** (all
      287 source new lesions have ORSP=PD; A02 lacks an `RSCAT` filter so the
      multi-row real RS trips it). SLD-math holds in 760/815 (93%) visits; the 55
      mismatches are systematic node short-axis (`LNSADIAM` limitation).
- [x] **Mapping validated** against `Data_dictionary.xlsx` + source (new-lesion
      equivalence 287==287, SLD-math 93%) — locked as regression tests
      (`tests/test_map_synta.py`, 11 pass).
- [ ] **Perf caveat:** full 325-subject run is hours under rdflib (super-linear
      `GROUP BY`) — ties to G2 (Oxigraph future work). n=50 is representative.

### Phase 2.5 — Hardening (from E1 findings) ✅ DONE 2026-06-17 (verified at shape+mapper level)
- [x] Added `cave:RSTESTCD 'OVRLRESP'` to RS-overall-matching archetype shapes
      **A01/A02/A06/A07/A20** (`shacl/archetype_shapes.ttl`). Backward-compatible:
      benchmark RS is 100% OVRLRESP → no-op there (verified).
- [x] Mapper aligned: overall→`OVRLRESP`, non-target→`NTRGRESP`; **`TA` domain
      added** (ARMCD=`PACLITAX` matches DM) → fixes A08.
- [x] Verified: A02 FP **69→0** on real data (10-subj); A02 still **detected** on
      mutated pharmaverse; 13 mapper tests pass.
- [x] **Backward-compat gate GREEN:** `test_track_b` **4 passed (44 min)** with
      hardened shapes — all 20 archetypes' detection preserved.
- [ ] **Gated on Oxigraph (G2):** full hardened **50-subject** E1 re-run on real
      data — recist `GROUP BY` shapes blew up to 14 GB on the real-trial graph.
      See `docs/item_e_e1_findings.md` §Phase 2.5.

### Phase 3 — E2 mutation transfer on Synta ✅ DONE 2026-06-23 (full 325-subj, Oxigraph)
- [x] `scripts/run_e2_real_data.py` injects the 20 Track-B archetypes into the
      mapped Synta SDTM and measures **per-subject targeted** detection on real
      trial structure (per-subject subgraph + multi-candidate; A17 full-graph).
      Result: `eval/real_data_e2_synta.json`; triage in `docs/item_e_e2_findings.md`.
- [x] **Headline: 10/11 applicable archetypes detected (90.9% recall on real
      structure)** in 244 s. Detected: A01,A02,A04,A05,A06,A08,A12,A13,A16,A17.
- [x] **9 not-applicable (data availability, excluded from denominator):**
      A03/A10/A11/A14/A15 (no EX/AE), A09 (ACTARMCD would flood A14, no EX),
      A07/A20 (year-only dates), A19 (L3 needs single-row RS + NTOVRLRESP/NEWLEC).
- [x] **1 miss (A18):** injector targets the *baseline* visit (screening, only a
      SUMDIAM row, no OVRLRESP) — its sibling A06 (same contradiction class)
      detects, so the shape is sound; the miss is a benchmark-shaped injector,
      not a detector gap. Track-B `bench.mutations` left **unmodified**.
- [x] Tests: `tests/test_run_e2_synta.py` (6 pass; skip if data absent).

### Phase 4 — Scale to 107 CA012 ✅ DONE 2026-06-23 (cross-trial external validity)
- [x] **`scripts/map_ca012_to_sdtm.py`** — maps PDS 107 (227-subj mBC) to SDTM
      TU/TR/RS/DM/DS/TA **+ EX** with **real day-offset dates**. Fidelity locked
      by `tests/test_map_ca012.py` (8 pass): **SLD-math 549/549 (100%)**, 0 orphan
      lesion links, RECIST codelist 100%, EX/DM reference dates ISO.
- [x] **E1 (naturalistic):** 227 subj in 34.5 s → `eval/real_data_e1_ca012.json`.
      Highly specific (archetype FPs 0.09/subj); S1 SLD-math 92, **S7 28-day
      confirmation 46 now exercised** (real dates).
- [x] **E2 (mutation transfer):** **16/18 applicable detected (88.9%)** in 121.6 s
      → `eval/real_data_e2_ca012.json`. The **EX-family (A10/A11/A14/A15) + A09**
      and **A18** are now detected (not-applicable on Synta); A18 detection
      confirms the Synta A18 miss was an injector artifact. Missed: A07/A20
      (temporal-confirmation injectors vs the sparse 4-visit schedule; A07's
      *shape* still fires naturally on clean CA012). N/A: A03 (no AE), A19 (L3).
- [x] **Cross-trial:** **16 distinct archetypes detected on ≥1 real trial**; a
      richer trial widens the applicable set (11→18). Triage:
      `docs/item_e_ca012_findings.md`.
- [ ] (Optional) 108 CA031 if a 3rd trial strengthens the claim; skip 114/158.

### Phase 5 — Manuscript integration ✅ DONE 2026-06-23
- [x] New Results subsection **"Real-world data validation"** (`sec:realdata`) with
      Synta+CA012 E1 (specificity) + E2 (cross-trial recall) and Table `tab:realdata`.
- [x] **Limitations** reconciled: "not validated on real data" → reports the real-data
      validation with remaining honest caveats (mapped-not-raw; recall-not-prevalence;
      applicability conditioned on data availability).
- [x] **Conclusion** updated (real-data first step). `manuscript.pdf` recompiles
      **19 pp, 0 undefined refs**; `manuscript_diff.pdf` regenerated (latexdiff).
- [x] **Response letter** (`response_to_reviewers.md`) R1-1 + R2-3 updated to report
      the completed real-data validation instead of "in progress".
- [ ] **Author-only (remaining):** decide whether to add a one-line real-data clause
      to the abstract (+ `abstract_for_submission_form.txt`); the abstract is at the
      300-word PLOS limit and form-synced, so this is left as an author framing call.

## 6. Key risks / decisions
- **Mapping fidelity is the validity threat**, not detection code. Every SDTM
  mapping decision must be auditable and protocol/CRF-grounded (the PDFs +
  SPECS spreadsheets are the source of truth). Treat the mapper as a reviewable
  artifact, not a throwaway.
- **Dates are coarse** (123 = year-only `YRDT`; 107/108 = day-offsets). S7
  (28-day confirmation) may be only partially testable on some trials — disclose.
- **No ground-truth contradiction labels** in real data → E1 is
  specificity/qualitative; quantitative recall claims come from E2 (injected).
- **Scope discipline:** 1 trial end-to-end (123) is a complete, publishable
  result. 2–3 trials strengthen external validity. 158 is out; 114 is lowest
  priority.

## 7. Recommended immediate next step
Start **Phase 0 + Phase 1 on trial 123 (Synta)** — it is the cleanest path from
raw to a CAVE-ingestible SDTM triplet and exercises the full archetype set.
