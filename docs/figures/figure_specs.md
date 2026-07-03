# Figure Specifications — CAVE-Onc Manuscript

## Figure 1: Architecture Diagram

**Title:** CAVE-Onc two-layer validation architecture.

**Description:** A left-to-right flow diagram showing the CAVE-Onc pipeline:

```
XPT Files        RDF Knowledge        Layer 1           Layer 3          Audit
(TU/TR/RS/       Graph                SHACL             LangGraph        Store
EX/DM)    --->   (CAVE         --->   (93 shapes:  --->  CaveAgent  --->  (SQLite
                  namespace,           85 CORE-ported    (RECIST           WAL +
                  Oxigraph)            + 8 RECIST)       Table 7           Merkle
                                                         lookup)          hash
                                                                          chain)
                         |                                   |
                         v                                   v
                    L1 Violation                      L3 Trace
                    Report (5803 flags)              (A19 detected)
```

**Key elements:**
- Input: 5 oncology domain XPT files (TU, TR, RS, EX, DM)
- Adapter: Custom XPT-to-RDF adapter with CAVE namespace, preserving variable labels, controlled terminology, and RELREC foreign keys
- L1: Trav-SHACL engine validating against 93 SHACL shapes (85 CORE-ported + 8 RECIST-SPARQL)
- L3: LangGraph state machine with SPARQL query tools and RECIST Table 7 lookup; invoked selectively based on routing heuristics
- Output: Append-only audit store with Merkle hash chain
- Arrows should show data flow direction (left-to-right)
- Use blue tones for L1 components, green tones for L3 components, grey for infrastructure

**Format suggestion:** Vector SVG or high-resolution PNG (300 DPI), column width (~180 mm).

---

## Figure 2: Detection Heatmap

**Title:** Contradiction archetype detection across configurations.

**Description:** A 20-row × 3-column heatmap showing detection status for each of 20 archetypes under three configurations:

- Column 1: CORE (B2 baseline)
- Column 2: L1-only (B3 ablation)
- Column 3: CAVE L1+L3 (full pipeline)

**Color encoding:**
- **Dark red (detected):** Binary detection = true
- **Light grey (not detected):** Binary detection = false

**Data source:** `detection_heatmap.csv` in this directory.

**Key annotations:**
- A16 row: L1-only and CAVE columns should be dark red (detected), CORE column light grey
- A19 row: Only CAVE column should be dark red (L3-only detection), CORE and L1-only light grey
- All other rows: All three columns light grey (0/0/0 detection)

**Format suggestion:** Seaborn heatmap with archetype IDs on y-axis, configuration labels on x-axis. Font size readable at column width.

**CSV data file:** `detection_heatmap.csv` — see below.

---

## Figure 3: Timing Comparison Bar Chart

**Title:** Mean validation time per archetype by component.

**Description:** A horizontal bar chart comparing wall-clock execution time for each pipeline component:

| Component | Mean time (s) |
|-----------|--------------|
| L1 SHACL | 20.318 |
| L3 Agent | 0.025 |
| Full CAVE (L1+L3) | 20.343 |
| CORE baseline | ~19.871 |

**Key elements:**
- Bars colored by component: blue (L1), green (L3), purple (Full CAVE), orange (CORE)
- X-axis: time in seconds (linear scale, or broken axis if needed to show L3)
- Annotation: "CAVE/CORE = 1.02x" above the full CAVE bar
- Annotation: "25 ms" label on the L3 bar to highlight negligible overhead
- Y-axis: component labels

**Alternative:** Two-panel figure with (a) full scale showing L1/CORE/Full CAVE comparison, and (b) zoomed scale (0–0.1 s) showing L3 agent overhead.

**Format suggestion:** Matplotlib horizontal bar chart, 300 DPI, column width.

---

*Generated for CAVE-Onc manuscript (P9), 2026-05-07.*
