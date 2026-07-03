# Empirical CORE / Pinnacle 21 baseline — per-archetype adjudication

> **Generated 2026-06-25.** First *real* run of the CDISC Open Rules Engine (CORE)
> on the Track B archetype benchmark. Reproduce with
> `bash scripts/run_core_p21_baseline.sh` → `eval/core_p21_benchmark.json`.

## TL;DR (the finding)

The manuscript states **"CORE detected 0/20"** on Track B (Results Table 3, Abstract,
Limitations point 3). A real CORE v0.15 run does **not** reproduce this:

| Group (from `docs/frozen_archetype_list.csv` `core_xref`) | n | CORE detects (direct) |
|---|---|---|
| **non-CORE cross-domain** (RECIST/semantic; `core_xref`=none or a RECIST shape) | 10 | **0/10** ✓ |
| **CORE-derived structural** (A08–A17, each *seeded from a CORE rule*) | 10 | **8/10** (9/10 incl. 1 indirect) |
| **Overall** | 20 | **8/20** (9/20 incl. indirect; 12/20 raise *any* flag) |

**The "0/20" is contradicted by the benchmark's own design.** Ten archetypes (A08–A17)
were explicitly seeded from CORE rules (`seed_source = gap_rules_bucket*`,
`core_xref = CORE-000xxx`); CORE's rules express them by construction, and a real run
confirms CORE catches 8 of them. The **0/10 on the non-CORE cross-domain contradictions
is robust** and is exactly the paper's thesis — graph constraints express patterns CORE
structurally cannot.

## Why the manuscript says 0/20

`B2_CORE` (`eval/baselines/b2_core.py`) only ever parsed cached CORE output for **pilot1**
(`eval/core_pilot1_raw.json`, Track A clean complementarity). **CORE was never run on the
mutated Track B corpus** — the "0/20" was an analytic assumption (per `EXECUTION_TRACKER.md`:
"P21 wraps CORE ⇒ 0/20, already reported"), not an empirical measurement. This run is the
first empirical CORE-on-Track-B evaluation.

## Method

`scripts/run_core_p21_baseline.py` + `.sh`:
1. **build** — from the validated `bench.mutations` mutators (untouched), write a clean
   corpus + one injected corpus per archetype as **CORE-readable SAS V5 XPORT** (the
   `xport` lib; pyreadstat's XPORT is unreadable by CORE's `pandas.read_sas` reader).
   Lean domain set (DM/DS/EX/AE/TA/RELREC/SUPPDM/SUPPAE/RS/TR/TU) — archetype-relevant only.
2. **run** — real CORE v0.15 (`vendor/core`, own venv): `validate -s sdtmig -v 3-4` on
   all 21 corpora → raw JSON reports.
3. **compare** — per archetype, NEW CORE violations on the injected subject vs the clean
   baseline. Detection = a NEW violation whose **rule semantics ARE the injected
   contradiction** (`direct`); `indirect` = flagged only via a generic derived-variable
   rule any edit would trip; collateral flags and silence = not detected.

## Per-archetype adjudication

| Archetype | Group | `core_xref` (design) | CORE result | Verdict |
|---|---|---|---|---|
| A01 SLD↓≥30% vs RSORRES=PD | non-CORE | RECIST_S3 | silent | not detected ✓ |
| A02 new lesion vs RS=SD | non-CORE | RECIST_S6 | silent | not detected ✓ |
| A03 EX start after attributed AE | non-CORE | none | collateral date errors only | not detected ✓ |
| A04 visit-window propagated | non-CORE | none | silent | not detected ✓ |
| A05 DM vs SUPPDM sex conflict | non-CORE | none | SUPP.QNAM naming (collateral) | not detected ✓ |
| A06 non-target PD vs RS=SD | non-CORE | none | silent | not detected ✓ |
| A07 PR without confirmation | non-CORE | RECIST_S7 | silent | not detected ✓ |
| A18 non-target overall misclass | non-CORE | none | silent | not detected ✓ |
| A19 Table 7 contradiction | non-CORE | none | silent | not detected ✓ |
| A20 iRECIST PD no confirmation | non-CORE | none | RSSEQ uniqueness (collateral) | not detected ✓ |
| **A08 ARMCD not in TA** | core-derived | CORE-000210 | **CORE-000210 fires** | **detected (direct)** |
| **A09 assigned subj no disposition** | core-derived | CORE-000296 | **CORE-000296 fires** | **detected (direct)** |
| **A10 RFXSTDTC ≠ min EXSTDTC** | core-derived | CORE-000239 | **CORE-000239 fires** | **detected (direct)** |
| **A11 RFXENDTC ≠ max EXENDTC** | core-derived | CORE-000238 | **CORE-000238 fires** | **detected (direct)** |
| **A12 DTHFL=Y no death details** | core-derived | CORE-000108 | **CORE-000705/001078 fire** | **detected (direct)** |
| **A13 RACE=MULTIPLE no SUPPDM** | core-derived | CORE-000846 | **CORE-000846 fires** | **detected (direct)** |
| A14 assigned arm no EX record | core-derived | CORE-000366 | no new flag on subject | not detected |
| A15 RFSTDTC ≠ first EXSTDTC | core-derived | CORE-001044 | DMDY/EXSTDY/AEENDY study-day miscalc | detected (indirect) |
| **A16 duplicate USUBJID** | core-derived | CORE-000351 | **CORE-000351 fires** | **detected (direct)** |
| **A17 ARMCD-ARM not 1:1** | core-derived | CORE-000318 | **CORE-000318 fires** | **detected (direct)** |

## Sensitivity / robustness

- **Specificity:** every `direct` detection matches a CORE rule whose semantics ARE the
  contradiction (e.g. CORE-000210 = "ARMCD not present in TA.ARMCD"); it would not fire on a
  benign edit. Verified absent-in-clean / present-in-injected for the exact target subject.
- **Paper's own oncology-domain filter** (`b2_core.py` → DM/EX/TU/TR/RS): CORE still directly
  detects **8/20** (A09's DS flag is reported on DM; it survives).
- **0/10 non-CORE result holds** under every criterion (direct, +indirect, any-flag).

## Implications for the resubmission

The repo is public and CORE is open-source/runnable, so a reviewer can reproduce `8/20`.
The blanket "CORE detected 0/20" (Abstract, Results Table 3, Limitations) is **not
defensible** and conflicts with `frozen_archetype_list.csv`. Honest, *stronger* framings:

1. **Report the real split.** CORE detects **0/10** of the non-CORE cross-domain RECIST
   contradictions (CAVE 10/10) and 8/10 of the archetypes seeded from CORE rules — so the
   uniquely-graph-expressible advantage is precisely the 0/10 semantic class. Replace the
   inferred 0/20 with this empirical CORE run as the B2 baseline.
2. **Scope the novelty claim** to the 10 non-CORE archetypes (CORE 0 vs CAVE 10) and present
   the 10 core-derived ones as a complementary/overlap set (CAVE re-expresses CORE rules as
   SHACL — a portability result, not a novelty one).

Either way the central thesis survives intact and is now **empirically** grounded; the
overclaim is removed.

## Real branded Pinnacle 21 (for completeness)

Pinnacle 21 Community **4.0** (Apr 2022) can *execute* this same CORE engine, but Certara
states running CORE through P21 is **not** equivalent to P21's own production (FDA/PMDA)
engine — CORE is an additional, experimental option. To run the *branded* P21 Community CLI
(`p21-client-<ver>.jar`, **Java 8 only**) the author must install P21 Community (proprietary,
registration-gated) and run e.g.
`java -jar p21-client.jar --standard=sdtm --standard.version=3.4 --source.sdtm=<dir> --report=<xlsx>`,
then point `eval/baselines/b1_p21.py` at the report. P21's own engine is also a domain-scoped
structural validator, so the **0/10 non-CORE result is expected to transfer**, but that claim
should be hedged unless run.
