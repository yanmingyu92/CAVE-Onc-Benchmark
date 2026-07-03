"""XPT → RDF adapter: converts SDTM XPT files into an in-memory rdflib Graph.

Preserves variable labels, codelists, USUBJID cross-domain linkage, and
RELREC relationships using a CDISC-aligned ontology.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable

import pyreadstat
from rdflib import BNode, Graph, Literal, RDF, RDFS, XSD

from kg.ontology import (
    CAVE,
    CDISC,
    DOMAINS,
    domain_class,
    domain_property,
    label_property,
    record_iri,
    relrec_iri,
)

logger = logging.getLogger(__name__)

# -- Public API ----------------------------------------------------------------

def load_xpt_to_graph(
    *paths: str | Path,
    graph: Graph | None = None,
    domains: Iterable[str] | None = None,
) -> Graph:
    """Load one or more XPT files into an RDF graph.

    Parameters
    ----------
    paths:
        XPT file paths (directories are scanned for ``*.xpt``).
    graph:
        Existing graph to extend; a fresh one is created if *None*.
    domains:
        Optional domain filter (e.g. ``["DM", "EX"]``).  *None* → all.

    Returns
    -------
    rdflib.Graph
    """
    g = graph or _fresh_graph()
    target_domains = set(d.upper() for d in (domains or DOMAINS))

    resolved = _resolve_paths(paths)
    for p in resolved:
        _load_one(g, p, target_domains)

    return g


# -- Internal ------------------------------------------------------------------

def _fresh_graph() -> Graph:
    g = Graph()
    g.bind("cdisc", CDISC)
    g.bind("cave", CAVE)
    return g


def _resolve_paths(paths: tuple[str | Path, ...]) -> list[Path]:
    out: list[Path] = []
    for p in paths:
        p = Path(p)
        if p.is_dir():
            out.extend(sorted(p.glob("*.xpt")))
        elif p.suffix.lower() == ".xpt":
            out.append(p)
    return out


def _load_one(g: Graph, path: Path, target_domains: set[str]) -> None:
    enc = "latin1" if path.stem == "ts" else None
    kw: dict = {"encoding": enc} if enc else {}
    df, meta = pyreadstat.read_xport(str(path), **kw)
    if df.empty:
        return

    # Derive domain from the DOMAIN column (first value) or file stem
    stem = path.stem.upper()
    if "DOMAIN" in df.columns:
        domain = str(df["DOMAIN"].iloc[0]).upper()
    elif stem == "RELREC":
        domain = "RELREC"
    elif stem in DOMAINS:
        domain = stem
    else:
        domain = ""
    if not domain:
        return
    # If domain is in our target set, emit; otherwise skip
    is_target = domain in target_domains

    # Also check for RELREC
    is_relrec = domain == "RELREC"

    if not is_target and not is_relrec:
        return

    col_names = list(meta.column_names)
    col_labels = dict(zip(meta.column_names, meta.column_labels))

    # Emit variable-label annotations once per domain
    for col in col_names:
        if col in ("STUDYID", "DOMAIN") or col not in col_labels:
            continue
        prop = domain_property(domain, col)
        g.add((prop, label_property(col), Literal(col_labels.get(col, col))))

    if is_relrec:
        _emit_relrec(g, df, col_names)
    else:
        _emit_domain_rows(g, df, domain, col_names)


def _emit_domain_rows(
    g: Graph, df, domain: str, col_names: list[str],
) -> None:
    seq_col = f"{domain}SEQ"
    is_supp = domain.startswith("SUPP")
    for _, row in df.iterrows():
        usubjid = str(row.get("USUBJID", ""))
        # Trial design domains (TA, TE, etc.) have no USUBJID — use row hash
        if not usubjid:
            seq = row.get(seq_col, _row_hash(row, col_names))
            subj = record_iri(domain, "_trial_", seq)
        else:
            seq = row.get(seq_col, _row_hash(row, col_names))
            subj = record_iri(domain, usubjid, seq)

        # Use CAVE namespace for type and properties — matches SHACL shapes
        g.add((subj, RDF.type, CAVE[domain]))
        if usubjid:
            g.add((subj, CDISC.USUBJID, Literal(usubjid)))
            g.add((subj, CAVE.USUBJID, Literal(usubjid)))  # shapes reference cave:USUBJID
        g.add((subj, CDISC.STUDYID, Literal(str(row.get("STUDYID", "")))))

        for col in col_names:
            if col in ("STUDYID", "DOMAIN", "USUBJID", seq_col):
                continue
            val = row.get(col)
            if val is None or (isinstance(val, float) and val != val):
                continue
            prop = CAVE[col]  # bare variable path: cave:AGE, cave:ARMCD, etc.
            g.add((subj, prop, _to_literal(val)))

        # Supplemental qualifier expansion: emit cave:SUPP_{QNAM} = QVAL
        # so SPARQL shapes can query e.g. cave:SUPP_SEX instead of
        # filtering on cave:QNAM='SEX' && cave:QVAL=?val
        if is_supp:
            qnam = str(row.get("QNAM", "")).strip()
            qval = row.get("QVAL")
            if qnam and qval is not None:
                g.add((subj, CAVE[f"SUPP_{qnam}"], _to_literal(qval)))


def _emit_relrec(g: Graph, df, col_names: list[str]) -> None:
    for _, row in df.iterrows():
        relid = str(row.get("RELID", ""))
        if not relid:
            continue
        rdomain = str(row.get("RDOMAIN", ""))
        usubjid = str(row.get("USUBJID", ""))
        idvar = str(row.get("IDVAR", ""))
        idvarval = str(row.get("IDVARVAL", ""))

        rel = relrec_iri(relid)
        g.add((rel, RDF.type, CDISC.RelatedRecords))
        g.add((rel, CDISC.RDOMAIN, Literal(rdomain)))
        g.add((rel, CDISC.USUBJID, Literal(usubjid)))
        g.add((rel, CDISC.IDVAR, Literal(idvar)))
        g.add((rel, CDISC.IDVARVAL, Literal(idvarval)))
        reltype = row.get("RELTYPE")
        if reltype is not None and str(reltype).strip():
            g.add((rel, CDISC.RELTYPE, _to_literal(reltype)))


def _to_literal(val) -> Literal:
    if isinstance(val, bool):
        return Literal(val, datatype=XSD.boolean)
    if isinstance(val, int):
        return Literal(val, datatype=XSD.integer)
    if isinstance(val, float):
        return Literal(val, datatype=XSD.double)
    return Literal(str(val))


def _row_hash(row, col_names: list[str]) -> str:
    """Deterministic fallback when no SEQ column exists."""
    import hashlib
    payload = "|".join(str(row.get(c, "")) for c in col_names)
    return hashlib.md5(payload.encode()).hexdigest()[:12]
