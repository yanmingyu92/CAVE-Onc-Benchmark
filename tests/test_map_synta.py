"""Tests for the Synta (PDS 123) legacy->SDTM mapper.

The raw PDS data is gitignored (sponsor terms), so these tests SKIP when the
source directory is absent (e.g. CI). When the data is present they assert the
structural invariants the CAVE engine relies on.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts import map_synta_to_sdtm as m

SRC = Path("data/real_oncology_data/AllProvidedFiles_123")
RECIST_CODES = {"CR", "PR", "SD", "PD", "NE", "ND", "NEVAL", ""}

pytestmark = pytest.mark.skipif(
    not (SRC / "rsp.sas7bdat").exists(),
    reason="PDS Synta raw data not present (gitignored)",
)


@pytest.fixture(scope="module")
def frames():
    studyid = m.STUDYID_DEFAULT
    lesles = m._load(SRC, "lesles")
    rsp = m._load(SRC, "rsp")
    dm = m._load(SRC, "dm")
    ds = m._load(SRC, "ds")
    return {
        "lesles": lesles, "rsp": rsp, "dm": dm, "ds": ds,
        "TU": m.build_tu(lesles, studyid),
        "TR": m.build_tr(lesles, studyid),
        "RS": m.build_rs(lesles, rsp, studyid),
        "DM": m.build_dm(dm, studyid),
        "DS": m.build_ds(ds, studyid),
        "TA": m.build_ta(dm, studyid),
    }


def test_all_domains_nonempty(frames):
    for dom in ("TU", "TR", "RS", "DM", "DS"):
        assert not frames[dom].empty, f"{dom} is empty"


def test_subject_conservation(frames):
    src_subjects = frames["dm"]["PT"].nunique()
    assert frames["DM"]["USUBJID"].nunique() == src_subjects


def test_no_orphan_lesion_links(frames):
    """Every TR target-lesion link must exist in TU for the same subject."""
    tu_keys = set(zip(frames["TU"]["USUBJID"], frames["TU"]["TULNKID"]))
    tr_keys = set(zip(frames["TR"]["USUBJID"], frames["TR"]["TRLNKID"]))
    orphans = tr_keys - tu_keys
    assert not orphans, f"orphan TR->TU links: {list(orphans)[:5]}"


def test_trgrpid_codelist(frames):
    assert set(frames["TR"]["TRGRPID"].unique()) <= {"TARGET", "NON-TARGET"}


def test_trtestcd_codelist(frames):
    assert set(frames["TR"]["TRTESTCD"].unique()) <= {"LDIAM", "TUMSTATE", "LNSADIAM"}


def test_rsorres_recist_codelist(frames):
    resp = frames["RS"][frames["RS"]["RSTESTCD"] == "OVRESP"]
    assert set(resp["RSORRES"].unique()) <= RECIST_CODES


def test_sumdiam_rows_exist(frames):
    rs = frames["RS"]
    sumdiam = rs[(rs["RSCAT"] == "TARGET RESPONSE") & (rs["RSTESTCD"] == "SUMDIAM")]
    assert not sumdiam.empty
    assert sumdiam["RSSTRESN"].notna().any()


def test_target_ldiam_measurements_numeric(frames):
    tr = frames["TR"]
    ldiam = tr[tr["TRTESTCD"] == "LDIAM"]
    assert ldiam["TRSTRESN"].notna().any()
    assert (ldiam["TRGRPID"] == "TARGET").all()


def test_new_lesion_first_appearance_matches_flag(frames):
    """Validation lock (E1): TU 'first appearance > baseline' must equal the
    explicit NEWLES flag in the source (287==287). This is the basis for the
    S6/A02 new-lesion->PD detection.
    """
    les = frames["lesles"].copy()
    les["LESID"] = les["LESID"].astype(str).str.strip()
    lesg = les[les["LESID"] != ""]
    first_post_baseline = (
        lesg.groupby(["PT", "LESID"])["VISITNUM"].min() > 0
    ).sum()
    flagged = (les["NEWLES"].astype(str).str.strip() == "NEW LESION").sum()
    assert first_post_baseline == flagged


def test_sld_math_majority_consistent(frames):
    """Validation lock (E1): SUMDIAM should equal sum of target LDIAM for the
    large majority of visits (>=85%); systematic node short-axis mismatches are
    the documented LNSADIAM limitation.
    """
    les = frames["lesles"].copy()
    les["LESID"] = les["LESID"].astype(str).str.strip()
    tgt = les[les["LESID"].str.match(r"^T\d") & les["LNGDIA"].notna()]
    sum_tgt = tgt.groupby(["PT", "VISITNUM"])["LNGDIA"].sum()
    summ = les[(les["LESID"] == "") & les["DIASUM"].notna()].groupby(
        ["PT", "VISITNUM"]
    )["DIASUM"].first()
    import pandas as pd

    cmp = pd.DataFrame({"a": sum_tgt, "b": summ}).dropna()
    match = ((cmp["a"] - cmp["b"]).abs() <= 1.0).mean()
    assert match >= 0.85, f"SLD-math match rate {match:.2%} below 85%"


def test_overall_response_uses_ovrlresp(frames):
    """Hardening lock: overall response must be RSTESTCD='OVRLRESP' so the
    archetype shapes (A01/A02/A06/A07/A20) match overall (not per-category) rows.
    """
    rs = frames["RS"]
    overall = rs[rs["RSCAT"] == "OVERALL RESPONSE"]
    assert not overall.empty
    assert set(overall["RSTESTCD"].unique()) == {"OVRLRESP"}
    # target/non-target must NOT be OVRLRESP (else archetype shapes over-fire)
    non_overall = rs[rs["RSCAT"] != "OVERALL RESPONSE"]
    assert "OVRLRESP" not in set(non_overall["RSTESTCD"].unique())


def test_ta_armcd_matches_dm(frames):
    """A08 lock: every DM.ARMCD must exist in TA.ARMCD (no spurious arm flag)."""
    dm_arm = set(frames["DM"]["ARMCD"].unique())
    ta_arm = set(frames["TA"]["ARMCD"].unique())
    assert dm_arm <= ta_arm, f"DM arms not in TA: {dm_arm - ta_arm}"


def test_enrich_derives_trtargetln():
    """enrich_recist_graph must add cave:TRTARGETLN from cave:TRGRPID."""
    from rdflib import Graph, Literal, XSD
    from kg.ontology import CAVE

    g = Graph()
    s_t, s_nt = CAVE["tr_t"], CAVE["tr_nt"]
    g.add((s_t, CAVE["TRGRPID"], Literal("TARGET")))
    g.add((s_nt, CAVE["TRGRPID"], Literal("NON-TARGET")))
    m.enrich_recist_graph(g)
    assert (s_t, CAVE["TRTARGETLN"], Literal(True, datatype=XSD.boolean)) in g
    assert (s_nt, CAVE["TRTARGETLN"], Literal(False, datatype=XSD.boolean)) in g
