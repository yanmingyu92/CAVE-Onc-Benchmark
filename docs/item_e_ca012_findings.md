# Item E — Phase 4 (CA012) Cross-Trial Findings: E1 + E2 on PDS 107

> 2026-06-23. Second real trial for **cross-trial external validity**
> (`docs/item_e_real_data_plan.md` Phase 4). CA012 is a 227-subject metastatic
> breast-cancer trial whose RECIST package is richer than Synta's: clean
> target/non-target/overall response labels, a derived SLD, **day-offset dates**
> (`EXAMDAY`/`DOSEDAY`/`EOSRDAY`), and a **`dose`** domain. That lets us map an
> `EX` domain and real (relative) dates, so CA012 exercises the EX-family and
> date archetypes that the Synta RECIST package could not.
>
> Mapper: `scripts/map_ca012_to_sdtm.py` · tests: `tests/test_map_ca012.py` (8
> pass) · results: `eval/real_data_e1_ca012.json`, `eval/real_data_e2_ca012.json`.

## Mapping & fidelity (the validity threat — locked by tests)

| Check | Result |
|---|---|
| Subjects mapped | **227** (TU=926, TR=2884, RS=1892, DM=227, DS=225, TA=1, **EX=1175**, **AE=1404**) |
| **SLD-math** (`SUMDIAM == Σ target LDIAM` per visit) | **549/549 (100%)** — CA012's derived `SUMTGT` matches exactly (cf. Synta 93%; no node short-axis ambiguity here) |
| Orphan lesion links (TR→TU) | **0** |
| RECIST codelist conformance (RS responses) | **100%** |
| Dates | `EXAMDAY`/`DOSEDAY` day-offsets anchored at a fixed reference → valid ISO dates; intervals preserved (S7/A07/A20 testable) |

Disclosed, auditable assumptions (in the mapper docstring): single arm `B`
(`ELIG_007`='B' for all 227); `SEX='F'` (mBC trial, child-bearing-potential CRF
field, no sex variable provided); `RACE_GEN` 1/2/9 → WHITE/BLACK/UNKNOWN; lesion
identity = (LESTYPE, LESNUM), verified stable across visits; non-target TUMSTATE
from `QUAN` (never UNEQUIVOCAL PROGRESSION, so E1 specificity is not tripped).
`ACTARM/ACTARMCD` are mapped here (safe, unlike Synta) **because CA012 has an EX
domain** — every treated subject has both a disposition and an exposure record,
so A09/A14 do not false-fire on clean data.

## E1 — naturalistic specificity (unmutated, full 227-subject cohort, 34.5 s)

| Bucket | Flags | Per subj | Reading |
|--------|------:|---------:|---------|
| `recist_derivation` (S1–S8) | **171** | 0.75 | genuine semantic signal |
| `archetype` (A01/A02/A07/A09/A14) | **20** | 0.09 | low; the date/EX-family archetypes have a few clean-data FPs |
| `core_structural` | 2764 | — | partial-mapping SDTM-conformance noise |
| `anon_property` | 1824 | — | blank-node structural constraints |

RECIST-derivation breakdown: **S1 SLD-math 92**, **S7 28-day confirmation 46**
(now exercised — CA012 has real dates, unlike Synta), S3 PR 16, S8 NE 13, S5 SD 3,
S4 PD 1. The engine stays highly specific on real data (0.09 archetype flags/subj),
consistent with the Synta E1 result, and now additionally exercises the temporal
S7 rule. The small clean-data archetype flags (A07=4, A09=2, A14=2) are the
date/EX-family analogues of the disclosed clean-data FPs and are exactly the
detectors that the richer CA012 mapping newly activates.

## E2 — mutation transfer (per-subject targeted, full cohort, 121.6 s)

**16 / 18 applicable archetypes detected (88.9% recall on real structure).**

| | archetypes |
|---|---|
| **Detected (16)** | A01, A02, A04, A05, A06, A08, **A09**, **A10**, **A11**, A12, A13, **A14**, **A15**, A16, A17, **A18** |
| **Missed (2)** | A07, A20 (temporal-confirmation; see below) |
| **Not applicable (2)** | A03 (AE domain *is* mapped from `toxy`, but it carries no causality attribution, which the attributed-AE join requires — see below), A19 (L3 needs single-row RS + NTOVRLRESP/NEWLEC) |

**The EX-family (A10/A11/A14/A15) and A09 are now detected** — they were
not-applicable on Synta (no EX/ACTARMCD) and are exercisable here because CA012
ships exposure + reference dates. **A18 also detects on CA012** (1/10 candidates),
where it was the lone Synta miss: CA012 subjects do carry an overall-response row
at the injected visit, so the A18 shape can join (confirming the Synta A18 miss
was an injector visit-selection artifact, not a detector gap — exactly as
predicted in `item_e_e2_findings.md`).

### The two misses are *injector* artifacts, confirmed by a schedule-aware variant (T3)
- **A07** ("confirmed PR without a confirmation visit") **fires naturally on
  clean CA012 — 4 flags in E1** — so the *detector transfers to real data*. The
  validated `bench.mutations` injector could not manufacture an *additional* fresh
  instance: it deletes every assessment >28 days after an induced PR, and because
  CA012's four visits (IDs 1/5/8/12) are themselves >28 days apart this removes
  *all* later visits, so the A07 shape's "a later visit exists" precondition no
  longer holds.
- **A20** (iRECIST immune-PD confirmation) misses because `mutate_A20` copies the
  subject's **first** RS row as the iCPD record; on CA012's multi-row RS that
  first row is a *target* response (`OVRESP`), so the injected iCPD carries the
  wrong test code and the A20 shape (keyed on `OVRLRESP`) cannot match. On the
  benchmark every RS row is `OVRLRESP`, so the same code path works there.

**T3 robustness check — both detectors transfer.** A schedule-aware variant
injector (`bench/variant_injectors.py`, used only by
`scripts/run_e2_variant_check.py`; the validated `bench.mutations` and the Track-B
20/20 result are left untouched) reproduces *the same two contradictions* in a
schedule- and RS-cardinality-agnostic way — A07 by setting an early overall PR
with later non-confirming visits, A20 by appending a correctly-typed `OVRLRESP`
iCPD row. On real CA012 structure **both fire**: A07 detected on 6/10 candidates,
A20 on 9/10 (`eval/real_data_e2_ca012_variant.json`). This isolates the two
headline misses as benchmark-shaped *injector* assumptions, not detector gaps.
The **headline E2 recall stays 16/18** (validated injector); the variant is a
robustness companion, not the reported number.

Track-B `bench.mutations` was left **unmodified** throughout.

### A03 — AE domain now mapped, but honestly not exercisable (T2)
CA012's `toxy` solicited-toxicity assessments are now mapped to a faithful **AE
domain** (1404 records: nausea, vomiting, diarrhea, mucositis, alopecia,
infection; `AESTDTC` from the day-offset; `AETOXGR`/`AESEV` from the grade).
Crucially, `toxy` records **no drug-causality / relationship variable**, so
`AEREL` is *not* fabricated. Archetype A03 (exposure-start-after-*attributed*-AE)
requires an attributed AE (`AEREL` ∈ {Y, PROBABLE, POSSIBLE}) for its SHACL join,
so it remains **not-applicable** — now for the precise reason "AE present but no
causality attribution" rather than "no AE domain". Adding AE leaves E1 specificity
and E2 recall unchanged (the AE rows trip no L1 shape); the applicability boundary
is encoded data-drivenly in `run_e2_real_data.not_applicable`.

## Cross-trial synthesis (Synta + CA012)

| | Synta (sparse: no EX, year-only dates) | CA012 (rich: EX + day-offset dates) |
|---|---|---|
| Subjects | 325 | 227 |
| E1 archetype FPs / subj | ~0.06 (21/325) | ~0.09 (20/227) |
| E2 applicable | 11 | 18 |
| E2 detected | 10 (90.9%) | 16 (88.9%) |
| Newly exercisable here | — | A09, A10, A11, A14, A15, A18, + S7 temporal |

**Distinct archetypes detected on ≥1 real trial: 16** — A01, A02, A04, A05, A06,
A08, A09, A10, A11, A12, A13, A14, A15, A16, A17, A18. Not detected on either:
A03 (requires an AE domain neither trial's RECIST package provided), A19 (L3 RS
cardinality), A07/A20 (temporal-confirmation injectors vs sparse real schedules —
though A07's *shape* demonstrably fires on clean CA012).

**External-validity message:** the engine's contradiction-detection logic
generalizes across two independent real oncology trials; **every archetype family
transfers wherever the trial actually provides the supporting domain**, and the
boundaries are nameable data-availability gaps (missing AE domain, sparse visit
schedules, benchmark-shaped RS cardinality), not detector weaknesses. A richer
trial (CA012) automatically widens the applicable set, demonstrating the result
scales with data completeness rather than being tailored to one corpus.

## Next
- **(Phase 5) — DONE.** E1 (specificity) + E2 (cross-trial recall) folded into the
  PLOS manuscript real-data subsection; the "no real-world validation" Limitations
  sentence reconciled.
- **(T2) — DONE.** CA012 `toxy` → AE mapped faithfully; A03 stays not-applicable
  for the precise, honest reason that `toxy` carries no causality attribution.
- **(T3) — DONE.** Schedule-aware variant injector confirms the A07/A20 *detectors*
  transfer to real CA012 structure (6/10, 9/10), isolating the headline misses as
  injector artifacts. Headline recall unchanged (16/18, validated injector).
