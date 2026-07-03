# Item E — Phase 3 (E2) Mutation-Transfer Findings: Synta 4783-08

> 2026-06-23. Quantitative external-validity companion to E1. Where E1 asked
> *"does the engine stay quiet on clean real data?"* (specificity), E2 asks
> *"when a known contradiction is injected into real trial topology, does the
> engine still catch it?"* (recall on real structure). Companion to
> `docs/item_e_real_data_plan.md` (Phase 3) and `docs/item_e_e1_findings.md`.
> Runner: `scripts/run_e2_real_data.py`. Raw result: `eval/real_data_e2_synta.json`.

## Method (per-subject targeted — same false-positive discipline as E1)

For each archetype Ai we draw candidate subjects from the **full 325-subject**
real cohort that are *not* already Ai-flagged on clean data, inject one
contradiction (the Track-B `bench.mutations`, unchanged), and re-run detection.
Because the archetype SHACL-SPARQL shapes are USUBJID-scoped joins, detection is
run on a **per-subject subgraph** (the injected subject's rows + trial-design
domains) — correct *and* fast, so the candidate pool can span the whole cohort.
The one genuinely cross-subject archetype (A17: ARMCD↔ARM one-to-one) is run on
the full graph.

**Detection criterion (rigorous):** Ai is *detected* iff its own shape fires on
the injected subject in the mutated subgraph but **not** in that subject's clean
subgraph — a newly-induced, subject-specific catch, never a coarse total-flag
delta. Trying several candidates (default 10) removes the artifact of an
auto-picked subject that happens not to satisfy the archetype's precondition.

Backend: **Oxigraph hybrid (G2)**. Full sweep: **244 s** (107 s clean baseline +
fast subgraphs + 103 s for the one full-graph A17 run).

## Headline

| | value |
|---|---|
| Archetypes injected | 20 |
| **Applicable on the Synta RECIST package** | **11** |
| **Detected on real trial structure** | **10 / 11 (90.9%)** |
| Missed | 1 (A18 — explained below; its contradiction *class* still transfers) |
| Not applicable (data availability) | 9 |

**Detected (10):** A01, A02, A04, A05, A06, A08, A12, A13, A16, A17.
**Missed (1):** A18.
**Not applicable (9):** A03, A07, A09, A10, A11, A14, A15, A19, A20.

The contradiction archetypes that depend only on the domains this trial actually
provides (TU/TR/RS/DM/DS/TA) **transfer to real trial topology** — detection is
not an artifact of the pharmaverse synthetic benchmark.

### Detection robustness (how many of 10 candidates each archetype caught)

| Archetype | candidates detected / tried | note |
|---|---|---|
| A04, A05, A08, A13, A16 | **10 / 10** | fires on every subject (cross-domain / structural) |
| A02, A06, A12 | 5 / 10 | needs the relevant RECIST precondition (new lesion / non-target row / etc.) |
| A01 | 1 / 10 | only subjects with a genuine ≥30% SLD decrease can host the contradiction — realistic |
| A17 | cohort-level | single full-graph run (cross-subject) |

## The one miss — A18 — is an injector visit-selection artifact, not a detector gap

A18 ("non-target shows UNEQUIVOCAL PROGRESSION but overall RS = SD") is the
**same contradiction class as A06**, which *detects* (5/10). The difference is
purely where each injector places the mutation:

- A06 targets a real **response visit** (an SD overall-response visit) → the
  `OVRLRESP` row exists → the shape joins → detected.
- A18's injector targets the subject's **first** RS visit. On real Synta the
  first visit is **screening (VISITNUM 0)**, which carries only a `SUMDIAM` row —
  **there is no `OVRLRESP` row at baseline** (overall responses begin at the
  on-treatment visits). The A18 shape requires `RSTESTCD='OVRLRESP'` at the same
  visit, so it cannot join, and the injected UNEQUIVOCAL-PROGRESSION non-target
  row at V0 goes uncaught (verified: targeted visit = 0; OVRLRESP visits =
  {200, 201}).

This is a **benchmark-shaped injector assumption** (first RS row = an overall
response), true on pharmaverse but not on real trial structure where baseline
carries only the diameter sum. The A18 **shape itself is sound** — its sibling
A06 proves the non-target-PD-vs-RS=SD pattern is detected on real data. We did
**not** modify the validated `bench.mutations` code (it would risk the Track-B
20/20 backward-compatibility gate); A18 is reported honestly as missed-by-injector.

## Why 9 archetypes are *not applicable* (data availability, not detection failure)

Excluded from the recall denominator, each with a concrete reason:

| Archetype(s) | Reason |
|---|---|
| A03, A10, A11, A14, A15 | require **EX**/**AE** domains absent from the Synta RECIST package |
| A09 | requires `DM.ACTARMCD`; mapping it on this trial (which has **no EX**) makes **A14 fire on all 325 subjects** as false positives (empirically verified: +325 A14 FPs, +1.3k structural). The actual-arm/exposure family is therefore out of scope for this trial — see the explicit note in `scripts/map_synta_to_sdtm.build_dm`. |
| A07, A20 | require fine-grained `RSDTC` dates for the 28-day / iRECIST confirmation rules; Synta dates are **year-only** (the disclosed S7 limitation from E1) |
| A19 | the L3 Table-7 detector needs the benchmark's **single** overall-response RS row plus `NTOVRLRESP`/`NEWLEC` test codes; real Synta RS is **multi-row** and lacks them, so detection would depend on synthetic enrichment — defeating the real-data purpose (consistent with the E1 RS-cardinality finding) |

This is the same honest external-validity message as E1, now quantified on
recall: the engine's RECIST/cross-domain contradiction logic **generalizes to
real trial structure**, and the boundaries are nameable data-availability gaps
(EX/AE domains, coarse dates, benchmark-shaped RS cardinality), not detector
weaknesses.

## Relationship to the benchmark (Track B)

Track B reports **20/20** on the pharmaverse synthetic corpus. E2 does **not**
contradict that: it measures how many of those 20 archetypes can even be
*exercised* on one real trial's provided datasets, and of the 11 that can, 10
detect. The gap (9 N/A + 1 injector-shape miss) is entirely attributable to (a)
domains/dates the trial did not provide and (b) two injectors/decoders that
assume the benchmark's simplified RS model — both already disclosed limitations.

## Artifacts

| Path | What |
|---|---|
| `scripts/run_e2_real_data.py` | E2 runner (subgraph multi-candidate detection, Oxigraph) |
| `tests/test_run_e2_synta.py` | classification + per-subject-targeted detection tests (skip if data absent) |
| `eval/real_data_e2_synta.json` | full per-archetype result (status, candidates, timing) |

## Recommended next steps
1. **(Phase 4)** Repeat E1+E2 on **107 CA012** (`scripts/map_ca012_to_sdtm.py`).
   CA012 ships `wcresp` derived responses + EX (`dose`) — so the EX-family
   (A03/A10/A11/A14/A15) and A09 may become exercisable there, widening the
   applicable set and strengthening external validity.
2. **(Phase 5)** Fold E1 (specificity) + E2 (recall on real structure) into the
   PLOS manuscript: reconcile the "no real-world validation" Limitations sentence,
   add a real-data subsection, and frame honestly — **10/11 applicable archetypes
   transfer**, with the boundaries above stated plainly.
