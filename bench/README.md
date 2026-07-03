# bench/ — Benchmark Corpus Generator

Contradiction injection corpus generator with RELREC-preserving structural unit tests.

## Scope (T5.6)
- 20 archetypes × ~30 cases each (~500–750 cases total)
- RELREC integrity preserved during injection (proposal §3 item 5)
- Structural unit tests: `core validate` returns no structural errors on injected datasets
- Provenance tracking for each injected contradiction
