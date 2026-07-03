# CAVE-Onc: Graph-Constrained Agentic Validation for Cross-Domain Contradictions

Reference implementation, benchmark data, and evaluation harness for **CAVE-Onc**,
a two-layer graph-constrained validation engine that detects **cross-domain
contradictions** in CDISC SDTM oncology submissions — for example a RECIST 1.1
overall response that contradicts the combined target-lesion, non-target-lesion,
and new-lesion status. Such contradictions pass structural (single-domain)
validators undetected.

Companion code + data for the manuscript submitted to *PLOS ONE*
(`docs/paper/CAVE-Onc_manuscript.pdf`, supplementary `docs/paper/S1_File_supplementary.pdf`).

> **Scope of the claim (please read).** The headline Track B result is a
> **construction validation of expressiveness**: the 20 contradiction archetypes
> were authored knowing the injected patterns, so 20/20 detection demonstrates that
> the shape language *can express* this class of cross-domain contradiction — it is
> **not** a real-world detection-rate estimate. The decisive comparison is that two
> industry validators (CDISC CORE 8/20; Pinnacle 21 FDA 6/20) each detect **0/10**
> of the non-CORE cross-domain RECIST contradictions they structurally cannot
> express, versus CAVE **10/10**. External-validity evidence (held-out archetypes,
> two real trials, adversarial robustness) is reported honestly with its limits.

## Architecture

- **Layer 1 (L1):** declarative SHACL shapes (`shacl/`). 85 CORE-ported +
  8 RECIST 1.1 derivation + 18 archetype-specific cross-domain `sh:sparql` shapes.
  Runs on rdflib/pyShACL (reference) or a **~35× faster Oxigraph backend**
  (`shacl/oxigraph_runner.py`).
- **Layer 3 (L3):** a `CaveAgent` (`agent/orchestrator.py`) performing the RECIST
  Table-7 overall-response derivation via structured tool calls (deterministic by
  design for 21 CFR Part 11 auditability).
- **Audit:** every flag is emitted as a hash-chained trace (`audit/store.py`).

## Repository layout

```
kg/            RDF ontology + XPT→RDF adapter
shacl/         L1 shapes (*.ttl) + pyShACL/Oxigraph runners
agent/         L3 CaveAgent (Table 7) + LLM verifier/explainer
audit/         hash-chained trace store
bench/         contradiction injector + the 20 archetype mutations
cave_onc/      package config
scripts/       analysis + reproduction pipeline (incl. CORE→SHACL porting tools)
eval/          committed result JSONs (every manuscript number traces here)
tests/         unit + integration tests
data/          public CDISC SDTM Pilot 1 + pharmaversesdtm RECIST (integrity-locked)
docs/          reproduction findings, figures, preregistration, paper PDFs
```

## Install

Requires Python ≥3.11. Using [uv](https://docs.astral.sh/uv/) (recommended):

```bash
uv sync            # installs from pyproject.toml + uv.lock (pinned, reproducible)
```

or with pip:

```bash
pip install -e .
```

## Reproduce the results

Every headline number in the manuscript traces to a committed file in `eval/`;
`scripts/audit_crosscheck.py` verifies that mapping:

```bash
uv run python scripts/audit_crosscheck.py         # 24 core checks + Gate-1/2 guards
uv run python -m pytest -q                         # test suite
```

Key analyses (Oxigraph backend; results written to `eval/`):

```bash
# Track B detection (subject-specific criterion, reproducible 20/20)
uv run python -m scripts.track_b_analysis --candidates --backend oxigraph
# Single-pass specificity (no clean-baseline delta): 17/20, 4 genuine clean flags
uv run python -m scripts.track_b_analysis --single-pass --backend oxigraph
# Adversarial robustness sweep on the mapped real trials
uv run python -m scripts.run_robustness_sweep --backend oxigraph
# Large-scale efficiency benchmark (1k–5k synthetic subjects)
uv run python -m scripts.run_scale_benchmark_large
```

## Results at a glance (all reproducible from `eval/`)

| Metric | Result |
|--------|--------|
| Track B (construction validation) | CAVE 20/20 · CORE 8/20 · Pinnacle 21 FDA 6/20 |
| Non-CORE cross-domain class | CAVE **10/10** · CORE **0/10** · P21 FDA **0/10** (McNemar p=0.002) |
| Held-out archetypes (generalization probe) | 3/5 detected (2/5 via intended mechanism) |
| Real trials (mutation-transfer recall) | Synta 10/11 · CA012 16/18 applicable |
| Single-pass specificity (no delta) | 17/20 detected · 4 clean-data flags total (all genuine) |
| Adversarial robustness | specificity holds under missingness; no crashes; co-occurrence recall 1.00 |
| Efficiency (Oxigraph) | detection scales sub-linearly (exp 0.982); ~4,900 subjects in ~24 s |

## Data provenance

`data/` contains only **public** corpora — the CDISC SDTM/ADaM Pilot Project data
and the open-source `pharmaversesdtm` RECIST package — integrity-locked by
`data/MANIFEST.sha256` (verified by `tests/test_data_smoke.py`). See
`data/PROVENANCE.md`. The real-world Project Data Sphere oncology trials used for
external validation are **not** redistributed (sponsor data-use terms); only the
derived hashes/inventories and the mapping code are included.

## License & citation

MIT License (`LICENSE`). If you use this work, please cite the CAVE-Onc manuscript
(*PLOS ONE*, PONE-D-26-23449). The preregistration is in `docs/osf_preregistration.md`.
