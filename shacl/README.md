# shacl/ — SHACL Shape Graph (L1 Layer)

RECIST 1.1 SHACL shapes for deterministic validation. This directory contains
the publishable shapes migrated from `gate_a/shapes/` (T4.2) plus new shapes
authored in T5.2.

## Contents
- `{tu,tr,rs,ex,dm}.ttl` — 85 CORE-ported shapes (polarity-audited + De Morgan expanded)
- `recist_derivation.ttl` — 8 RECIST derivation shapes (S1–S8)

## Source Lineage
- Gate A: `gate_a/shapes/` (frozen, immutable)
- Copied here at T4.2 for Trav-SHACL runner (T5.2) consumption

## Validation
- Trav-SHACL runner (T5.2) loads shapes from this directory
- 19/20 archetypes are L1-expressible (SHACL/SHACL-SPARQL)
