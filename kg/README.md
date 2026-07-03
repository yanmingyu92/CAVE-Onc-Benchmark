# kg/ — Knowledge Graph Layer

XPT→RDF adapter, ontology definitions, and RDF graph construction for SDTM oncology data.

## Scope (T5.1)

- **`ontology.py`** — CDISC-aligned namespace and IRI definitions for oncology domains (DM, EX, TU, TR, RS)
- **`xpt_to_rdf.py`** — XPT→RDF adapter: reads SDTM XPT files via `pyreadstat`, maps each record to RDF triples using a CDISC-aligned ontology, preserving variable labels, USUBJID cross-domain linkage, and RELREC relationships
- Output: `rdflib.Graph` (in-memory); Oxigraph integration deferred to T5.2

## Usage

```python
from kg.xpt_to_rdf import load_xpt_to_graph

# Load specific domains from multiple sources
graph = load_xpt_to_graph(
    "data/pilot1/dm.xpt",
    "data/pilot1/ex.xpt",
    "data/pharmaversesdtm_onco",       # directory → scans *.xpt
    "data/pilot1/relrec.xpt",          # RELREC relationships
    domains=["DM", "EX", "TU", "TR", "RS"],
)

print(f"Triples: {len(graph)}")
```

### Domain coverage

| Domain | Source | Description |
|--------|--------|-------------|
| DM | `pilot1/dm.xpt` | Demographics |
| EX | `pilot1/ex.xpt` | Exposure |
| TU | `pharmaversesdtm_onco/tu.xpt` | Tumor Identification |
| TR | `pharmaversesdtm_onco/tr.xpt` | Tumor Results |
| RS | `pharmaversesdtm_onco/rs.xpt` | Disease Response |
| RELREC | `pilot1/relrec.xpt` | Related Records |

### Notes

- `ts.xpt` requires `encoding='latin1'` (handled automatically)
- RELREC has no DOMAIN column; detected by file stem
- Each row gets a stable IRI: `cave:<domain>/<usubjid>/<seq>`
- Variable labels are emitted as annotation triples
