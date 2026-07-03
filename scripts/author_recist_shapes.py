"""Author RECIST 1.1 derivation shapes (S1-S8) as SHACL-SPARQL.

Reads gate_a/recist_catalog.csv, emits gate_a/shapes/recist_derivation.ttl.
Round-trip self-validation against 3 synthetic subject trajectories.
"""

import argparse, re
from pathlib import Path

import rdflib
from rdflib.namespace import RDF, RDFS, SH, XSD, Namespace
from pyshacl import validate as shacl_validate

CAVE = Namespace("https://cave-onc.org/shacl/")
PROV = Namespace("http://www.w3.org/ns/prov#")

# ── SPARQL fragments (single braces — used via string concatenation) ───
# pyshacl requires $this projected from every sub-SELECT.
# S2-S8 filter RSTESTCD='OVRESP' to match response-category records only.

_R = ("$this cave:RSCAT 'TARGET RESPONSE' ;"
      " cave:RSTESTCD 'OVRESP' ; cave:RSORRES ?resp ;"
      " cave:USUBJID ?u ; cave:VISITNUM ?v .")

_TSUM = ("{ SELECT $this ?u ?v (SUM(?d) AS ?sld) WHERE {"
         " $this cave:USUBJID ?u ; cave:VISITNUM ?v ."
         " ?tr a cave:TR ; cave:USUBJID ?u ; cave:VISITNUM ?v ;"
         " cave:TRTESTCD 'LDIAM' ; cave:TRTARGETLN true ; cave:TRSTRESN ?d ."
         " } GROUP BY $this ?u ?v }")

_BVN = ("{ SELECT $this ?u (MIN(?bv) AS ?baseline_vn) WHERE {"
        " $this cave:USUBJID ?u ."
        " ?btr a cave:TR ; cave:USUBJID ?u ; cave:TRTARGETLN true ;"
        " cave:VISITNUM ?bv ; cave:EPOCH 'SCREENING' ."
        " } GROUP BY $this ?u }")

_BSLD = ("{ SELECT $this ?u ?baseline_vn (SUM(?d) AS ?base_sld) WHERE {"
         " $this cave:USUBJID ?u ."
         " ?btr a cave:TR ; cave:USUBJID ?u ; cave:TRTESTCD 'LDIAM' ;"
         " cave:TRTARGETLN true ; cave:TRSTRESN ?d ; cave:VISITNUM ?baseline_vn ."
         " } GROUP BY $this ?u ?baseline_vn }")

# Nadir: min SLD from baseline up to current visit ?v (visit-relative)
_NDR = ("{ SELECT $this ?u ?v (MIN(?sld_val) AS ?nadir) WHERE {"
        " $this cave:VISITNUM ?v ."
        " { SELECT $this ?u ?vv (SUM(?d) AS ?sld_val) WHERE {"
        " $this cave:USUBJID ?u ."
        " ?tr a cave:TR ; cave:USUBJID ?u ; cave:TRTESTCD 'LDIAM' ;"
        " cave:TRTARGETLN true ; cave:TRSTRESN ?d ; cave:VISITNUM ?vv ."
        " } GROUP BY $this ?u ?vv }"
        " { SELECT $this ?u (MIN(?bv2) AS ?bl2) WHERE {"
        " $this cave:USUBJID ?u ."
        " ?btr2 a cave:TR ; cave:USUBJID ?u ; cave:TRTARGETLN true ;"
        " cave:VISITNUM ?bv2 ; cave:EPOCH 'SCREENING' ."
        " } GROUP BY $this ?u }"
        " FILTER(?vv >= ?bl2 && ?vv <= ?v)"
        " } GROUP BY $this ?u ?v }")

# No new lesion at this visit (exclusion for S5)
_NNL = ("FILTER NOT EXISTS { ?tu a cave:TU ; cave:USUBJID ?u ;"
        " cave:TUCAT 'TARGET LESION' ; cave:TULNKID ?lid ;"
        " cave:VISITNUM ?tu_v ."
        " FILTER(?tu_v = ?v && ?tu_v > ?baseline_vn)"
        " FILTER NOT EXISTS { ?tu_pre a cave:TU ; cave:USUBJID ?u ;"
        " cave:TULNKID ?lid ; cave:VISITNUM ?pre_v ."
        " FILTER(?pre_v <= ?baseline_vn) } }")

SHAPES = [
    ("S1", "Shape_RECIST_S1_sld_math", SH.Violation,
     "RS.SUMDIAM does not equal SUM of target-lesion TR.TRSTRESN at this visit",
     "SELECT $this ?expected ?got WHERE {"
     " $this cave:RSCAT 'TARGET RESPONSE' ; cave:RSTESTCD 'SUMDIAM' ;"
     " cave:RSSTRESN ?got ; cave:USUBJID ?u ; cave:VISITNUM ?v ."
     " { SELECT $this ?u ?v (SUM(?d) AS ?expected) WHERE {"
     " $this cave:USUBJID ?u ; cave:VISITNUM ?v ."
     " ?tr a cave:TR ; cave:USUBJID ?u ; cave:VISITNUM ?v ;"
     " cave:TRTESTCD 'LDIAM' ; cave:TRTARGETLN true ; cave:TRSTRESN ?d ."
     " } GROUP BY $this ?u ?v }"
     " FILTER(?expected != ?got) }"),
    ("S2", "Shape_RECIST_S2_target_cr", SH.Violation,
     "All target-lesion diameters are 0 and no lymph-node short-axis >= 10 mm but RSORRES is not CR",
     "SELECT $this WHERE { " + _R +
     " FILTER(?resp != 'CR')"
     " { SELECT $this ?u ?v WHERE {"
     " $this cave:USUBJID ?u ; cave:VISITNUM ?v ."
     " ?tr a cave:TR ; cave:USUBJID ?u ; cave:VISITNUM ?v ;"
     " cave:TRTESTCD 'LDIAM' ; cave:TRTARGETLN true ; cave:TRSTRESN ?d ."
     " } GROUP BY $this ?u ?v"
     " HAVING (COUNT(?tr) > 0 && SUM(IF(?d > 0, 1, 0)) = 0) }"
     " FILTER NOT EXISTS {"
     " ?node a cave:TR ; cave:USUBJID ?u ; cave:VISITNUM ?v ;"
     " cave:TRTESTCD 'LNSADIAM' ; cave:TRTARGETLN true ; cave:TRSTRESN ?nsa ."
     " FILTER(?nsa >= 10) } }"),
    ("S3", "Shape_RECIST_S3_target_pr", SH.Violation,
     "SLD decreased >= 30% from baseline but RSORRES is neither PR nor CR",
     "SELECT $this WHERE { " + _R +
     " FILTER(?resp != 'PR' && ?resp != 'CR')"
     " " + _TSUM + " " + _BVN + " " + _BSLD +
     " FILTER(?v > ?baseline_vn && ?sld <= 0.70 * ?base_sld) }"),
    ("S4", "Shape_RECIST_S4_target_pd", SH.Violation,
     "SLD increased >= 20% over nadir with >= 5 mm absolute increase but RSORRES is not PD",
     "SELECT $this WHERE { " + _R +
     " FILTER(?resp != 'PD')"
     " " + _TSUM + " " + _BVN + " " + _NDR +
     " FILTER(?v > ?baseline_vn && ?sld >= 1.20 * ?nadir && (?sld - ?nadir) >= 5) }"),
    ("S5", "Shape_RECIST_S5_target_sd", SH.Violation,
     "Not CR/PR/PD by SLD criteria and no new lesion but RSORRES is not SD",
     "SELECT $this WHERE { " + _R +
     " FILTER(?resp != 'SD')"
     " " + _TSUM + " " + _BVN + " " + _BSLD + " " + _NDR +
     " FILTER(?v > ?baseline_vn)"
     " FILTER(?sld > 0.70 * ?base_sld)"
     " FILTER(?sld < 1.20 * ?nadir || (?sld - ?nadir) < 5)"
     " " + _NNL + " }"),
    ("S6", "Shape_RECIST_S6_new_lesion_pd", SH.Violation,
     "New target lesion appeared post-baseline but RSORRES is not PD",
     "SELECT $this WHERE { " + _R +
     " FILTER(?resp != 'PD')"
     " " + _BVN +
     " ?tu a cave:TU ; cave:USUBJID ?u ; cave:TUCAT 'TARGET LESION' ;"
     " cave:TULNKID ?lid ; cave:VISITNUM ?tu_v ."
     " FILTER(?tu_v > ?baseline_vn && ?tu_v = ?v)"
     " FILTER NOT EXISTS { ?tu_pre a cave:TU ; cave:USUBJID ?u ;"
     " cave:TULNKID ?lid ; cave:VISITNUM ?pre_v ."
     " FILTER(?pre_v <= ?baseline_vn) } }"),
    ("S7", "Shape_RECIST_S7_confirmation", SH.Warning,
     "CR or PR at visit V not confirmed by CR/PR at a subsequent visit >= 28 days later",
     "SELECT $this WHERE { $this cave:RSCAT 'TARGET RESPONSE' ;"
     " cave:RSTESTCD 'OVRESP' ; cave:RSORRES ?resp ;"
     " cave:RSDTC ?dt_v ; cave:USUBJID ?u ; cave:VISITNUM ?v ."
     " FILTER(?resp = 'CR' || ?resp = 'PR')"
     " FILTER NOT EXISTS { ?later a cave:RS ; cave:USUBJID ?u ;"
     " cave:RSCAT 'TARGET RESPONSE' ; cave:RSTESTCD 'OVRESP' ;"
     " cave:RSORRES ?later_resp ; cave:RSDTC ?dt_later ."
     " FILTER(?later_resp = 'CR' || ?later_resp = 'PR')"
     " FILTER(?dt_later > ?dt_v"
     " && ((?dt_later - ?dt_v) >= 'P28D'^^xsd:dayTimeDuration))"
     " } }"),
    ("S8", "Shape_RECIST_S8_ne_propagation", SH.Violation,
     "Target-lesion TR missing or NOT DONE but RSORRES is not NE",
     "SELECT $this WHERE { " + _R +
     " FILTER(?resp != 'NE')"
     " " + _BVN +
     " FILTER(?v > ?baseline_vn)"
     " FILTER NOT EXISTS { ?tr a cave:TR ; cave:USUBJID ?u ;"
     " cave:VISITNUM ?v ; cave:TRTESTCD 'LDIAM' ;"
     " cave:TRTARGETLN true ; cave:TRSTRESN ?dval ."
     " FILTER(?dval >= 0) } }"),
]

# ── Deterministic serialization ────────────────────────────────────────

def _det_turtle(g):
    ttl = g.serialize(format="turtle")
    mapping, ctr = {}, [0]
    def repl(m):
        l = m.group(0)
        if l not in mapping: mapping[l] = f"_:b{ctr[0]}"; ctr[0] += 1
        return mapping[l]
    return re.sub(r'_:N[a-zA-Z0-9]+', repl, ttl)

def build_shapes(ns=CAVE):
    shapes = []
    for key, local, sev, msg, sel in SHAPES:
        sn = ns[local]; sg = rdflib.Graph()
        for pfx, uri in [("cave",ns),("sh",SH),("prov",PROV),("rdf",RDF),("rdfs",RDFS)]:
            sg.bind(pfx, uri)
        sg.add((sn, RDF.type, SH.NodeShape))
        sg.add((sn, SH.targetClass, ns["RS"]))
        sg.add((sn, RDFS.label, rdflib.Literal("RECIST 1.1 derivation")))
        sg.add((sn, RDFS.comment, rdflib.Literal(f"RECIST 1.1 derivation shape; {local}")))
        sg.add((sn, PROV.wasDerivedFrom, rdflib.Literal(f"RECIST_1_1_{key}")))
        bn = rdflib.BNode()
        sg.add((sn, SH.sparql, bn))
        sg.add((bn, RDF.type, SH.SPARQLConstraint))
        sg.add((bn, SH.message, rdflib.Literal(msg)))
        sg.add((bn, SH.select, rdflib.Literal(sel)))
        if sev == SH.Warning:
            sg.add((sn, SH.severity, SH.Warning))
        shapes.append((local, sn, sg))
    return shapes

# ── Fixture helpers ────────────────────────────────────────────────────

def _san(s): return re.sub(r'[^a-zA-Z0-9_]', '_', s)

def _tr(g, uid, vn, testcd, val, target=True, epoch=None):
    n = CAVE[f"TR_{uid}_V{vn}_{testcd}_{abs(hash(str(val)))%10000}"]
    g.add((n, RDF.type, CAVE["TR"]))
    g.add((n, CAVE["USUBJID"], rdflib.Literal(uid)))
    g.add((n, CAVE["VISITNUM"], rdflib.Literal(vn, datatype=XSD.integer)))
    g.add((n, CAVE["TRTESTCD"], rdflib.Literal(testcd)))
    g.add((n, CAVE["TRTARGETLN"], rdflib.Literal(target, datatype=XSD.boolean)))
    if val is not None:
        g.add((n, CAVE["TRSTRESN"], rdflib.Literal(val, datatype=XSD.decimal)))
    if epoch:
        g.add((n, CAVE["EPOCH"], rdflib.Literal(epoch)))

def _rs(g, uid, vn, testcd, cat, orres, stresn=None, rsdtc=None):
    n = CAVE[f"RS_{uid}_V{vn}_{_san(cat)}_{testcd}_{abs(hash(orres))%10000}"]
    g.add((n, RDF.type, CAVE["RS"]))
    g.add((n, CAVE["USUBJID"], rdflib.Literal(uid)))
    g.add((n, CAVE["VISITNUM"], rdflib.Literal(vn, datatype=XSD.integer)))
    g.add((n, CAVE["RSTESTCD"], rdflib.Literal(testcd)))
    g.add((n, CAVE["RSCAT"], rdflib.Literal(cat)))
    g.add((n, CAVE["RSORRES"], rdflib.Literal(orres)))
    if stresn is not None:
        g.add((n, CAVE["RSSTRESN"], rdflib.Literal(stresn, datatype=XSD.decimal)))
    if rsdtc:
        g.add((n, CAVE["RSDTC"], rdflib.Literal(rsdtc, datatype=XSD.date)))

def _tu(g, uid, vn, lnkid, tucat="TARGET LESION"):
    n = CAVE[f"TU_{uid}_V{vn}_{lnkid}"]
    g.add((n, RDF.type, CAVE["TU"]))
    g.add((n, CAVE["USUBJID"], rdflib.Literal(uid)))
    g.add((n, CAVE["VISITNUM"], rdflib.Literal(vn, datatype=XSD.integer)))
    g.add((n, CAVE["TULNKID"], rdflib.Literal(lnkid)))
    g.add((n, CAVE["TUCAT"], rdflib.Literal(tucat)))

# ── Synthetic subjects ─────────────────────────────────────────────────

def build_subject_a():
    """CR trajectory: baseline SLD=50 -> V2 PR (SLD=25) -> V3 CR (SLD=0)."""
    g = rdflib.Graph(); g.bind("cave", CAVE)
    _tr(g,"SUBJ-A",1,"LDIAM",30,target=True,epoch="SCREENING")
    _tr(g,"SUBJ-A",1,"LDIAM",20,target=True,epoch="SCREENING")
    _rs(g,"SUBJ-A",1,"SUMDIAM","TARGET RESPONSE","NA",stresn=50)
    _rs(g,"SUBJ-A",1,"OVRESP","TARGET RESPONSE","NA")
    _tr(g,"SUBJ-A",2,"LDIAM",15); _tr(g,"SUBJ-A",2,"LDIAM",10)
    _rs(g,"SUBJ-A",2,"SUMDIAM","TARGET RESPONSE","PR",stresn=25)
    _rs(g,"SUBJ-A",2,"OVRESP","TARGET RESPONSE","PR",rsdtc="2025-02-01")
    _tr(g,"SUBJ-A",3,"LDIAM",0); _tr(g,"SUBJ-A",3,"LDIAM",0)
    _rs(g,"SUBJ-A",3,"SUMDIAM","TARGET RESPONSE","CR",stresn=0)
    _rs(g,"SUBJ-A",3,"OVRESP","TARGET RESPONSE","CR",rsdtc="2025-03-15")
    return g

def build_subject_b():
    """PD by new lesion: baseline SLD=40 -> V2 SD (35) -> V3 PD (new T03)."""
    g = rdflib.Graph(); g.bind("cave", CAVE)
    _tr(g,"SUBJ-B",1,"LDIAM",40,target=True,epoch="SCREENING")
    _rs(g,"SUBJ-B",1,"SUMDIAM","TARGET RESPONSE","NA",stresn=40)
    _rs(g,"SUBJ-B",1,"OVRESP","TARGET RESPONSE","NA")
    _tu(g,"SUBJ-B",1,"T01"); _tu(g,"SUBJ-B",1,"T02")
    _tr(g,"SUBJ-B",2,"LDIAM",35)
    _rs(g,"SUBJ-B",2,"SUMDIAM","TARGET RESPONSE","SD",stresn=35)
    _rs(g,"SUBJ-B",2,"OVRESP","TARGET RESPONSE","SD")
    _tr(g,"SUBJ-B",3,"LDIAM",38)
    _rs(g,"SUBJ-B",3,"SUMDIAM","TARGET RESPONSE","PD",stresn=38)
    _rs(g,"SUBJ-B",3,"OVRESP","TARGET RESPONSE","PD")
    _tu(g,"SUBJ-B",3,"T03")
    return g

def build_subject_c():
    """PR not confirmed: baseline SLD=50 -> V2 PR (30) -> V3 SD (35)."""
    g = rdflib.Graph(); g.bind("cave", CAVE)
    _tr(g,"SUBJ-C",1,"LDIAM",50,target=True,epoch="SCREENING")
    _rs(g,"SUBJ-C",1,"SUMDIAM","TARGET RESPONSE","NA",stresn=50)
    _rs(g,"SUBJ-C",1,"OVRESP","TARGET RESPONSE","NA")
    _tr(g,"SUBJ-C",2,"LDIAM",30)
    _rs(g,"SUBJ-C",2,"SUMDIAM","TARGET RESPONSE","PR",stresn=30)
    _rs(g,"SUBJ-C",2,"OVRESP","TARGET RESPONSE","PR",rsdtc="2025-01-15")
    _tr(g,"SUBJ-C",3,"LDIAM",35)
    _rs(g,"SUBJ-C",3,"SUMDIAM","TARGET RESPONSE","SD",stresn=35)
    _rs(g,"SUBJ-C",3,"OVRESP","TARGET RESPONSE","SD",rsdtc="2025-03-01")
    return g

def build_violate(g, orres_from, orres_to, stresn_from=None, stresn_to=None):
    """Create variant by changing an RS response value."""
    g2 = rdflib.Graph()
    for pfx, ns in g.namespaces(): g2.bind(pfx, ns)
    for t in g: g2.add(t)
    for rs in g2.subjects(CAVE["RSORRES"], rdflib.Literal(orres_from)):
        g2.remove((rs, CAVE["RSORRES"], rdflib.Literal(orres_from)))
        g2.add((rs, CAVE["RSORRES"], rdflib.Literal(orres_to)))
        if stresn_from is not None and stresn_to is not None:
            g2.remove((rs, CAVE["RSSTRESN"], rdflib.Literal(stresn_from, datatype=XSD.decimal)))
            g2.add((rs, CAVE["RSSTRESN"], rdflib.Literal(stresn_to, datatype=XSD.decimal)))
    return g2

# ── Main pipeline ──────────────────────────────────────────────────────

def run(out_path, date_str=None):
    shapes = build_shapes()
    combined = rdflib.Graph()
    for pfx, uri in [("cave",CAVE),("sh",SH),("prov",PROV),("rdf",RDF),("rdfs",RDFS),("xsd",XSD)]:
        combined.bind(pfx, uri)
    for _, _, sg in shapes:
        for t in sg: combined.add(t)
    ttl = _det_turtle(combined)
    out_path = Path(out_path); out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(ttl, encoding="utf-8")
    return len(shapes)

def main():
    p = argparse.ArgumentParser(description="Author RECIST 1.1 derivation shapes")
    p.add_argument("--out", default="gate_a/shapes/recist_derivation.ttl", type=Path)
    p.add_argument("--date", default=None)
    a = p.parse_args()
    print(f"RECIST shapes authored: {run(a.out, date_str=a.date)}")

if __name__ == "__main__":
    main()
