"""Shape IRI → (archetype_id, core_rule_xref) mapping.

Seeded from ``gate_a/xref_table.csv`` and ``gate_b/archetypes.csv``.
"""

from __future__ import annotations

import csv
from pathlib import Path

SHAPE_NS = "https://cave-onc.org/shacl/"


def _build_map(
    xref_path: str | Path = "gate_a/xref_table.csv",
    arch_path: str | Path = "gate_b/archetypes.csv",
) -> dict[str, tuple[str, list[str]]]:
    """Build shape IRI → (archetype_id, [core_rule_xref]) from CSVs."""
    # core_xref → archetype_id
    xref_to_arch: dict[str, str] = {}
    try:
        with open(arch_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                xref_to_arch[row["core_xref"].strip()] = row["archetype_id"].strip()
    except FileNotFoundError:
        pass

    result: dict[str, tuple[str, list[str]]] = {}
    try:
        with open(xref_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                shape_iri = row.get("shape_iri", "").strip()
                if not shape_iri:
                    continue
                core_id = row["core_rule_id"].strip()
                # Expand prefixed form (e.g. "cave:Shape_X" → full IRI)
                if ":" in shape_iri and not shape_iri.startswith("http"):
                    shape_iri = f"{SHAPE_NS}{shape_iri.split(':', 1)[1]}"
                arch_id = xref_to_arch.get(core_id, core_id)
                result[shape_iri] = (arch_id, [core_id])
    except FileNotFoundError:
        pass
    return result


SHAPE_TO_ARCHETYPE: dict[str, tuple[str, list[str]]] = _build_map()

# -- Archetype-specific SHACL-SPARQL shapes (from shacl/archetype_shapes.ttl) --
# These shapes directly target contradiction archetypes A01-A20.
_ARCHETYPE_SHAPES: dict[str, tuple[str, list[str]]] = {
    f"{SHAPE_NS}Shape_Archetype_A{i:02d}": (f"A{i:02d}", [f"archetype_A{i:02d}"])
    for i in list(range(1, 16)) + [17, 18, 20]  # A01-A15, A17, A18, A20 (A16/A19 handled elsewhere)
}
SHAPE_TO_ARCHETYPE.update(_ARCHETYPE_SHAPES)
