"""Map the Synta 4783-08 (PDS package 123) legacy datasets to SDTM TU/TR/RS/DM/DS.

This is the Phase 1 mapper for the Item E real-world validation
(see ``docs/item_e_real_data_plan.md``). It converts the sponsor-defined Synta
RECIST datasets (``lesles``, ``rsp``, ``dm``, ``ds``) into the CAVE-ingestible
SDTM column model that the L1 SHACL shapes and L3 agent consume — the same
``cave:`` property names produced by ``scripts/track_b_analysis._frames_to_graph``
and queried by ``shacl/recist_derivation.ttl``.

Target column model (verified against the production shapes):
  TR : USUBJID STUDYID VISITNUM TRSEQ TRLNKID TRTESTCD{LDIAM|LNSADIAM|TUMSTATE}
       TRTARGETLN(bool) TRSTRESN TRORRES EPOCH
  TU : USUBJID STUDYID VISITNUM TUSEQ TULNKID TUCAT{TARGET LESION|NON-TARGET LESION} TULOC
  RS : USUBJID STUDYID VISITNUM RSSEQ RSCAT{TARGET|NON-TARGET|OVERALL RESPONSE}
       RSTESTCD{OVRESP|SUMDIAM} RSORRES RSSTRESC RSSTRESN
  DM : USUBJID STUDYID SEX RACE AGE ARM ARMCD
  DS : USUBJID STUDYID DSDECOD DSCAT EPOCH DSSEQ

Output: ``data/real_sdtm/synta/{tu,tr,rs,dm,ds}.xpt`` (XPT v5, gitignored via *.xpt).

Mapping decisions (grounded in observed Synta values; flagged TODO where the
CRF/Data_dictionary.xlsx should still confirm):
  * USUBJID  = f"{STUDYID}-{int(PT)}"
  * baseline = VISITNUM == 0  -> EPOCH 'SCREENING'; else 'TREATMENT'
  * target vs non-target lesion = LESID prefix ('T' target, 'NT' non-target)
  * SUMDIAM  = lesles.DIASUM on the per-visit summary row (LESID blank); falls
    back to SUM of target LNGDIA when DIASUM is absent.
  * TODO: lymph-node short axis (LNSADIAM) is NOT distinguished in Synta lesles
    (no short-axis field) -> S2 node rule (LNSADIAM<10mm) is not testable here;
    disclose as a per-trial limitation.
  * TODO: dates are year-only (YRDT) -> RSDTC reconstruction is coarse; S7
    (28-day confirmation) only partially testable. Visit ordering via VISITNUM.

Usage:
    python -m scripts.map_synta_to_sdtm \
        --src "data/real_oncology_data/AllProvidedFiles_123" \
        --out data/real_sdtm/synta
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import pandas as pd
import pyreadstat

logger = logging.getLogger(__name__)

STUDYID_DEFAULT = "SYNTA-4783-08"
UNSCHED_VISITNUM = 996.0  # Synta 'UNSCHED' code; excluded from baseline logic


# -- helpers ------------------------------------------------------------------

def _load(src: Path, name: str) -> pd.DataFrame:
    df, _meta = pyreadstat.read_sas7bdat(str(src / f"{name}.sas7bdat"))
    return df


def _usubjid(studyid: str, pt) -> str:
    try:
        return f"{studyid}-{int(float(pt))}"
    except (TypeError, ValueError):
        return f"{studyid}-{pt}"


def _epoch(visitnum: float) -> str:
    return "SCREENING" if visitnum == 0 else "TREATMENT"


def _is_target(lesid: str) -> bool:
    return lesid.upper().startswith("T") and not lesid.upper().startswith("NT")


def _armcd(trtp: str) -> str:
    """Derive a stable ARMCD from the free-text treatment label (DM and TA must agree)."""
    return str(trtp or "")[:8].upper().replace(" ", "")


# -- domain builders ----------------------------------------------------------

def build_tu(lesles: pd.DataFrame, studyid: str) -> pd.DataFrame:
    """One TU row per first appearance of each (subject, lesion)."""
    rows: list[dict] = []
    seen: set[tuple[str, str]] = set()
    les = lesles[lesles["LESID"].astype(str).str.strip() != ""].copy()
    les = les.sort_values(["PT", "VISITNUM"])
    seq: dict[str, int] = {}
    for _, r in les.iterrows():
        lesid = str(r["LESID"]).strip()
        uid = _usubjid(studyid, r["PT"])
        key = (uid, lesid)
        if key in seen:
            continue
        seen.add(key)
        seq[uid] = seq.get(uid, 0) + 1
        rows.append({
            "STUDYID": studyid, "USUBJID": uid,
            "VISITNUM": float(r["VISITNUM"]), "TUSEQ": seq[uid],
            "TULNKID": lesid,
            "TUCAT": "TARGET LESION" if _is_target(lesid) else "NON-TARGET LESION",
            "TULOC": str(r.get("LESSIT", "") or ""),
        })
    return pd.DataFrame(rows)


def build_tr(lesles: pd.DataFrame, studyid: str) -> pd.DataFrame:
    """Target-lesion LDIAM measurements + non-target TUMSTATE rows."""
    rows: list[dict] = []
    seq: dict[str, int] = {}
    les = lesles[lesles["LESID"].astype(str).str.strip() != ""].copy()
    les = les.sort_values(["PT", "VISITNUM", "LESID"])
    for _, r in les.iterrows():
        lesid = str(r["LESID"]).strip()
        uid = _usubjid(studyid, r["PT"])
        vn = float(r["VISITNUM"])
        target = _is_target(lesid)
        seq[uid] = seq.get(uid, 0) + 1
        # SDTM-standard TRGRPID (<=8 chars, XPT-safe). cave:TRTARGETLN is
        # derived from TRGRPID at graph-build time (see enrich_recist_graph),
        # because XPT v5 caps variable names at 8 chars and has no boolean type.
        base = {
            "STUDYID": studyid, "USUBJID": uid, "VISITNUM": vn,
            "TRSEQ": seq[uid], "TRLNKID": lesid,
            "TRGRPID": "TARGET" if target else "NON-TARGET",
            "EPOCH": _epoch(vn),
        }
        ndone = str(r.get("NDONE", "") or "").strip().upper() == "NOT DONE"
        if target:
            ldiam = r.get("LNGDIA")
            base.update({
                "TRTESTCD": "LDIAM",
                "TRSTRESN": float(ldiam) if pd.notna(ldiam) else None,
                "TRORRES": "" if pd.isna(ldiam) else str(ldiam),
                "TRSTAT": "NOT DONE" if ndone else "",
            })
        else:
            # Non-target lesion state -> TUMSTATE (RECIST qualitative)
            base.update({
                "TRTESTCD": "TUMSTATE",
                "TRORRES": str(r.get("LESEVL", "") or ""),
                "TRSTAT": "NOT DONE" if ndone else "",
            })
        rows.append(base)
    return pd.DataFrame(rows)


def build_rs(lesles: pd.DataFrame, rsp: pd.DataFrame, studyid: str) -> pd.DataFrame:
    """RS rows: target/non-target/overall response + SUMDIAM per visit."""
    rows: list[dict] = []
    seq: dict[str, int] = {}

    def add(uid: str, vn: float, cat: str, testcd: str,
            orres: str = "", stresn=None) -> None:
        seq[uid] = seq.get(uid, 0) + 1
        rows.append({
            "STUDYID": studyid, "USUBJID": uid, "VISITNUM": vn,
            "RSSEQ": seq[uid], "RSCAT": cat, "RSTESTCD": testcd,
            "RSORRES": orres, "RSSTRESC": orres,
            "RSSTRESN": float(stresn) if stresn is not None and pd.notna(stresn) else None,
            "EPOCH": _epoch(vn),
        })

    # Response codes from rsp
    resp = rsp.copy()
    for _, r in resp.iterrows():
        uid = _usubjid(studyid, r["PT"])
        vn = float(r["VISITNUM"])
        trsp = str(r.get("TRSP", "") or "").strip()
        ntrsp = str(r.get("NTRSP", "") or "").strip()
        orsp = str(r.get("ORSP", "") or "").strip()
        # RSTESTCD codes are chosen to match BOTH shape families:
        #   - recist_derivation S1-S8 query RSCAT='TARGET RESPONSE' + RSTESTCD='OVRESP'
        #   - archetype A01/A02/A06/A07/A20 match overall response via RSTESTCD='OVRLRESP'
        # so the overall row MUST be OVRLRESP (not OVRESP) or the archetype shapes
        # over-fire on the per-category rows (E1 finding, docs/item_e_e1_findings.md).
        if trsp:
            add(uid, vn, "TARGET RESPONSE", "OVRESP", trsp)
        if ntrsp:
            add(uid, vn, "NON-TARGET RESPONSE", "NTRGRESP", ntrsp)
        if orsp:
            add(uid, vn, "OVERALL RESPONSE", "OVRLRESP", orsp)

    # SUMDIAM per (subject, visit) from lesles summary rows (LESID blank) or
    # fallback to SUM of target LDIAM.
    les = lesles.copy()
    summ = les[les["LESID"].astype(str).str.strip() == ""]
    sum_by: dict[tuple[str, float], float] = {}
    for _, r in summ.iterrows():
        ds = r.get("DIASUM")
        if pd.notna(ds):
            sum_by[(_usubjid(studyid, r["PT"]), float(r["VISITNUM"]))] = float(ds)
    tgt = les[les["LESID"].astype(str).str.strip() != ""]
    tgt = tgt[tgt["LESID"].astype(str).map(_is_target)]
    for (pt, vn), grp in tgt.groupby(["PT", "VISITNUM"]):
        uid = _usubjid(studyid, pt)
        key = (uid, float(vn))
        if key not in sum_by:
            vals = grp["LNGDIA"].dropna()
            if not vals.empty:
                sum_by[key] = float(vals.sum())
    for (uid, vn), sld in sum_by.items():
        add(uid, vn, "TARGET RESPONSE", "SUMDIAM", "", sld)

    return pd.DataFrame(rows)


def build_dm(dm: pd.DataFrame, studyid: str) -> pd.DataFrame:
    rows: list[dict] = []
    for _, r in dm.drop_duplicates(subset=["PT"]).iterrows():
        uid = _usubjid(studyid, r["PT"])
        rows.append({
            "STUDYID": studyid, "USUBJID": uid,
            "AGE": r.get("AGE"), "SEX": str(r.get("SEX", "") or ""),
            "RACE": str(r.get("RACE", "") or ""),
            "ARM": str(r.get("TRTP", "") or ""),
            "ARMCD": _armcd(r.get("TRTP", "")),
            # NB: ACTARM/ACTARMCD are intentionally NOT mapped. Synta provides no
            # EX domain, so emitting ACTARMCD would make the actual-arm/exposure
            # archetypes (A09, A14) fire on every subject as false positives
            # (verified: +325 A14 FPs). The actual-arm/exposure family is
            # therefore out of scope for this trial (see item_e_e2_findings.md).
        })
    return pd.DataFrame(rows)


def build_ta(dm: pd.DataFrame, studyid: str) -> pd.DataFrame:
    """Trial Arms domain — one row per distinct arm, ARMCD matching DM (for A08)."""
    arms = {}
    for _, r in dm.iterrows():
        trtp = str(r.get("TRTP", "") or "")
        if trtp and trtp not in arms:
            arms[trtp] = _armcd(trtp)
    rows = []
    for i, (arm, armcd) in enumerate(sorted(arms.items()), start=1):
        rows.append({
            "STUDYID": studyid, "ARMCD": armcd, "ARM": arm,
            "TAETORD": 1, "ETCD": f"EL{i:02d}", "ELEMENT": "Treatment",
            "TASEQ": i,
        })
    return pd.DataFrame(rows)


def build_ds(ds: pd.DataFrame, studyid: str) -> pd.DataFrame:
    rows: list[dict] = []
    seq: dict[str, int] = {}
    sub = ds[ds.get("DSDECOD").astype(str).str.strip() != ""] if "DSDECOD" in ds else ds
    for _, r in sub.iterrows():
        uid = _usubjid(studyid, r["PT"])
        seq[uid] = seq.get(uid, 0) + 1
        rows.append({
            "STUDYID": studyid, "USUBJID": uid, "DSSEQ": seq[uid],
            "DSDECOD": str(r.get("DSDECOD", "") or ""),
            "DSCAT": str(r.get("DSCAT", "") or ""),
            "EPOCH": str(r.get("EPOCH", "") or ""),
        })
    return pd.DataFrame(rows)


# -- graph enrichment ---------------------------------------------------------

def enrich_recist_graph(graph) -> None:
    """Derive ``cave:TRTARGETLN`` (bool) from ``cave:TRGRPID`` in place.

    The S1-S8 RECIST-derivation shapes query ``cave:TRTARGETLN true`` for the
    target-lesion SLD join. We store the SDTM-standard ``TRGRPID`` in the XPT
    (8-char limit, no boolean) and add the boolean flag here, mirroring the
    in-memory enrichment pattern used by ``track_b_analysis._enrich_rs``.
    """
    from rdflib import Literal, XSD
    from kg.ontology import CAVE

    for subj, grp in list(graph.subject_objects(CAVE["TRGRPID"])):
        is_target = str(grp).upper() == "TARGET"
        graph.add((subj, CAVE["TRTARGETLN"], Literal(is_target, datatype=XSD.boolean)))


# -- write --------------------------------------------------------------------

def _write_xpt(df: pd.DataFrame, path: Path, domain: str) -> None:
    if df.empty:
        logger.warning("domain %s is empty — skipping write", domain)
        return
    df = df.copy()
    df.insert(0, "DOMAIN", domain)
    # deterministic ordering
    sort_cols = [c for c in ("USUBJID", "VISITNUM", f"{domain}SEQ") if c in df.columns]
    if sort_cols:
        df = df.sort_values(sort_cols).reset_index(drop=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    pyreadstat.write_xport(df, str(path), file_format_version=5, table_name=domain)
    logger.info("wrote %s rows=%d -> %s", domain, len(df), path)


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Map Synta 123 legacy -> SDTM.")
    parser.add_argument(
        "--src", type=Path,
        default=Path("data/real_oncology_data/AllProvidedFiles_123"),
    )
    parser.add_argument("--out", type=Path, default=Path("data/real_sdtm/synta"))
    parser.add_argument("--studyid", default=STUDYID_DEFAULT)
    args = parser.parse_args(argv)

    src: Path = args.src
    lesles = _load(src, "lesles")
    rsp = _load(src, "rsp")
    dm = _load(src, "dm")
    ds = _load(src, "ds")

    tu = build_tu(lesles, args.studyid)
    tr = build_tr(lesles, args.studyid)
    rs = build_rs(lesles, rsp, args.studyid)
    dm_o = build_dm(dm, args.studyid)
    ds_o = build_ds(ds, args.studyid)
    ta_o = build_ta(dm, args.studyid)

    _write_xpt(tu, args.out / "tu.xpt", "TU")
    _write_xpt(tr, args.out / "tr.xpt", "TR")
    _write_xpt(rs, args.out / "rs.xpt", "RS")
    _write_xpt(dm_o, args.out / "dm.xpt", "DM")
    _write_xpt(ds_o, args.out / "ds.xpt", "DS")
    _write_xpt(ta_o, args.out / "ta.xpt", "TA")

    print(
        f"Synta -> SDTM: TU={len(tu)} TR={len(tr)} RS={len(rs)} "
        f"DM={len(dm_o)} DS={len(ds_o)} TA={len(ta_o)} "
        f"subjects={dm_o['USUBJID'].nunique()}"
    )


if __name__ == "__main__":
    main()
