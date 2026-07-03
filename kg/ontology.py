"""CDISC-aligned namespace and IRI definitions for SDTM oncology domains."""

from __future__ import annotations

from rdflib import Namespace, URIRef

# -- Namespaces ---------------------------------------------------------------

CDISC: Namespace = Namespace("http://www.cdisc.org/ns/sdtm#")
CAVE: Namespace = Namespace("https://cave-onc.org/shacl/")
RDFS = Namespace("http://www.w3.org/2000/01/rdf-schema#")
SDTMV = Namespace("http://www.cdisc.org/ns/sdtm-variant#")

DOMAINS = ("DM", "EX", "TU", "TR", "RS", "AE", "DS", "TA", "SUPPDM")

# -- Helper -------------------------------------------------------------------

def domain_class(domain: str) -> URIRef:
    """Return the CDISC class IRI for a SDTM domain code (e.g. ``DM`` → ``cdisc:DM``)."""
    return CDISC[domain]


def domain_property(domain: str, var: str) -> URIRef:
    """Return a property IRI for ``<domain>.<var>`` (e.g. ``DM.USUBJID`` → ``cdisc:DM-USUBJID``)."""
    return CDISC[f"{domain}-{var}"]


def label_property(var: str) -> URIRef:
    """Return an IRI for the variable *label* annotation."""
    return CDISC[f"{var}-label"]


def record_iri(domain: str, usubjid: str, seq: str | int) -> URIRef:
    """Construct a stable record IRI: ``cave:<domain>/<usubjid>/<seq>``."""
    return CAVE[f"{domain}/{usubjid}/{seq}"]


def relrec_iri(relid: str) -> URIRef:
    """Construct a RELREC relationship IRI."""
    return CAVE[f"relrec/{relid}"]
