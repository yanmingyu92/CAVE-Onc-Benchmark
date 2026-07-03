# eval/ — Evaluation Harness

Baseline harness per proposal §4 specification.

## Scope (T6.x)
- `run_baseline.py` — common dispatcher
- Baseline wrappers: B1 (P21), B2 (CORE), B3 (L1-only), B4 (IF+ESD), B5 (GPT+RAG supplementary)
- Track A: CORE regression (Jaccard ≥0.95)
- Track B: CAVE-only novelty catches
