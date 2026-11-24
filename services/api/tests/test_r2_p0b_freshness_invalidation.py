from __future__ import annotations

import io
import json
from pathlib import Path

import openpyxl
import pytest

from app.models import Approval, BriefVersion, ContentBrief, ExportRecord, MappingRevision


def _setup_two_kw_project(tc, code: str = "F01") -> str:
    tc.put("/api/v1/settings/ai", json={"provider": "mock", "set_active": True})
    pid = tc.post(
        "/api/v1/projects",
        json={
            "code": code,
            "name": f"Freshness Project {code}",
            "topic_pillar_code": code,
            "topic_pillar_name": f"Freshness Pillar {code}",
            "primary_keyword": "quyết toán thuế tncn",
            "secondary_keywords": ["công cụ tính thuế tncn"],
            "business_goal": "Tăng khách hàng tư vấn thuế SME",
            "target_audience": "Kế toán & HR SME",
            "market": "VN",
        },
    ).json()["project"]["id"]
    tc.post(f"/api/v1/projects/{pid}/analyze-topic")
    return pid


def _upload_and_confirm(tc, pid: str, filename: str, csv_text: str, *, report_type: str, market: str = "VN"):
    prev = tc.post(
        f"/api/v1/projects/{pid}/imports/preview",
        data={"report_type": report_type, "locale": "en-US"},
        files={"file": (filename, csv_text.encode("utf-8"), "text/csv")},
    )
    assert prev.status_code == 200, prev.text
    pbody = prev.json()
    conf = tc.post(
        f"/api/v1/projects/{pid}/imports/confirm",
        json={
            "upload_id": pbody["upload_id"],
            "report_type": report_type,
            "market": market,
            "locale": "en-US",
            "column_mapping": pbody["suggested_mapping"],
        },
    )
    assert conf.status_code == 200, conf.text
    return conf.json()


def _approve_all(tc, pid: str):
    for a in tc.get(f"/api/v1/projects/{pid}/approvals").json()["approvals"]:
        if a["status"] == "PENDING":
            r = tc.post(f"/api/v1/projects/{pid}/approvals/{a['id']}", json={"decision": "APPROVED", "decided_by": "QA"})
            assert r.status_code == 200, r.text


def _serp_csv(keyword: str, positions: list[int], prefix: str, path_prefix: str = "blog") -> str:
    lines = ["Keyword,Position,URL,Title"]
    for p in positions:
        lines.append(f"{keyword},{p},https://{prefix}{p}.vn/{path_prefix}/bai-{p},Title {p}")
    return "\n".join(lines) + "\n"


def test_f01_f06_f07_serp_change_after_approval_auto_invalidates_without_mapping_rerun(client):
    """
    F01: Create OFFICIAL brief for A; upload new conflicting SERP for A WITHOUT clicking mapping/preview.
         GET opportunities / briefs / POST briefs/generate / POST exports/download MUST immediately reflect stale/not-official & require reapproval.
    F06: allow_draft=True, direct brief endpoint, and direct historical export download CANNOT bypass stale check.
    F07: Historical BriefVersion, Approval, MappingRevision, and ExportRecord remain intact and truthfully labeled.
    """
    tc, _ = client
    from app import db as db_mod

    pid = _setup_two_kw_project(tc, "F01")
    metrics_csv = (
        "Keyword,Volume,KD,Intent\n"
        "quyết toán thuế tncn,2200,26,Informational\n"
        "cách xử lý quyết toán thuế tncn,600,19,Informational\n"
    )
    _upload_and_confirm(tc, pid, "m.csv", metrics_csv, report_type="KEYWORD_OVERVIEW")
    _upload_and_confirm(tc, pid, "s_a1.csv", _serp_csv("quyết toán thuế tncn", list(range(1, 11)), "a1"), report_type="ORGANIC_RESULTS")
    _upload_and_confirm(tc, pid, "s_b1.csv", _serp_csv("cách xử lý quyết toán thuế tncn", list(range(1, 11)), "b1"), report_type="ORGANIC_RESULTS")

    tc.post(f"/api/v1/projects/{pid}/mapping/preview")
    _approve_all(tc, pid)

    opps_ok = tc.get(f"/api/v1/projects/{pid}/opportunities").json()
    m_a = next(m for m in opps_ok["mappings"] if m["primary_keyword"] == "quyết toán thuế tncn")
    m_b = next(m for m in opps_ok["mappings"] if m["primary_keyword"] == "cách xử lý quyết toán thuế tncn")
    assert m_a["eligibility"]["eligible_official"] is True
    assert m_b["eligibility"]["eligible_official"] is True

    # Generate OFFICIAL briefs for both A and B and export an OFFICIAL XLSX snapshot
    br_gen = tc.post(f"/api/v1/projects/{pid}/briefs/generate", json={"allow_draft": False, "mapping_ids": [m_a["id"], m_b["id"]]})
    assert br_gen.status_code == 200
    assert br_gen.json()["official_count"] == 2

    exp_official = tc.post(f"/api/v1/projects/{pid}/exports/download", json={"format": "xlsx"})
    assert exp_official.status_code == 200
    assert "_OFFICIAL_" in exp_official.headers["X-FinZ-Export-Filename"]
    exports_before = tc.get(f"/api/v1/projects/{pid}/exports").json()["exports"]
    old_export_id = exports_before[0]["id"]
    assert exports_before[0]["freshness_status"] == "CURRENT"

    # NOW: Upload NEW conflicting SERP for A ONLY — DO NOT call /mapping/preview!
    _upload_and_confirm(
        tc, pid, "s_a2_conflict.csv",
        _serp_csv("quyết toán thuế tncn", list(range(1, 11)), "a2new", path_prefix="cong-cu"),
        report_type="ORGANIC_RESULTS",
    )

    # F01 + F03 check immediately WITHOUT calling /mapping/preview:
    opps_after = tc.get(f"/api/v1/projects/{pid}/opportunities").json()
    m_a_after = next(m for m in opps_after["mappings"] if m["primary_keyword"] == "quyết toán thuế tncn")
    m_b_after = next(m for m in opps_after["mappings"] if m["primary_keyword"] == "cách xử lý quyết toán thuế tncn")
    assert m_a_after["eligibility"]["eligible_official"] is False
    assert m_a_after["is_approved"] is False
    assert m_a_after["eligibility"]["approval_state"] == "STALE_SUPERSEDED"
    # F03: B MUST remain approved and eligible_official!
    assert m_b_after["eligibility"]["eligible_official"] is True
    assert m_b_after["is_approved"] is True

    # Brief for A must immediately appear stale & non-OFFICIAL!
    briefs_after = {b["primary_keyword"]: b for b in tc.get(f"/api/v1/projects/{pid}/briefs").json()["briefs"]}
    assert briefs_after["quyết toán thuế tncn"]["is_stale"] is True
    assert briefs_after["quyết toán thuế tncn"]["brief_mode"] == "DRAFT"
    assert briefs_after["cách xử lý quyết toán thuế tncn"]["is_stale"] is False
    assert briefs_after["cách xử lý quyết toán thuế tncn"]["brief_mode"] == "OFFICIAL"

    # F06: Direct allow_draft=False for A blocked; allow_draft=True produces DRAFT for A (NEVER OFFICIAL)!
    assert tc.post(f"/api/v1/projects/{pid}/briefs/generate", json={"allow_draft": False, "mapping_ids": [m_a["id"]]}).status_code == 400
    gen_mixed = tc.post(f"/api/v1/projects/{pid}/briefs/generate", json={"allow_draft": True, "mapping_ids": [m_a["id"]]})
    assert gen_mixed.status_code == 200
    assert gen_mixed.json()["briefs"] == []
    assert gen_mixed.json()["backlog"][0]["id"] == m_a["id"]

    # F06: Fresh export MUST be labeled DRAFT, not OFFICIAL!
    exp_new = tc.post(f"/api/v1/projects/{pid}/exports/download", json={"format": "xlsx"})
    assert exp_new.status_code == 200
    assert "_DRAFT_" in exp_new.headers["X-FinZ-Export-Filename"]
    wb = openpyxl.load_workbook(io.BytesIO(exp_new.content))
    ws_brief = wb.worksheets[0]
    # V2 block layout: stale historical brief remains visibly DRAFT in its block.
    assert any(ws_brief.cell(r,2).value == "Trạng thái" and ws_brief.cell(r,3).value == "DRAFT" for r in range(1,ws_brief.max_row+1))

    # F06 + F07: Historical OFFICIAL export is preserved, marked OUTDATED_SUPERSEDED, blocks silent download (409), allows explicit historical ack!
    exports_after = {e["id"]: e for e in tc.get(f"/api/v1/projects/{pid}/exports").json()["exports"]}
    assert exports_after[old_export_id]["freshness_status"] == "OUTDATED_SUPERSEDED"
    assert exports_after[old_export_id]["is_superseded"] is True
    silent_dl = tc.get(f"/api/v1/projects/{pid}/exports/file/{old_export_id}")
    assert silent_dl.status_code == 409
    assert silent_dl.json()["detail"]["code"] == "HISTORICAL_EXPORT_SUPERSEDED"
    ack_dl = tc.get(f"/api/v1/projects/{pid}/exports/file/{old_export_id}?acknowledge_historical=true")
    assert ack_dl.status_code == 200
    assert ack_dl.headers.get("X-FinZ-Export-Freshness") == "HISTORICAL_SUPERSEDED"
    assert ack_dl.content == exp_official.content  # Original immutable bytes preserved!

    # F07: Historical BriefVersion, Approval, MappingRevision, and ExportRecord all preserved in SQLite!
    db = db_mod.SessionLocal()
    try:
        assert db.query(BriefVersion).count() >= 2  # V2: backlog does not create an additional brief version
        assert db.query(MappingRevision).filter(MappingRevision.keyword_mapping_id == m_a["id"]).count() >= 2
        assert db.query(Approval).filter(Approval.project_id == pid, Approval.target_ref == m_a["id"], Approval.status == "APPROVED").count() == 1
        assert db.query(Approval).filter(Approval.project_id == pid, Approval.target_ref == m_a["id"], Approval.status == "PENDING").count() == 1
        assert db.query(ExportRecord).filter(ExportRecord.project_id == pid).count() == 2
    finally:
        db.close()


def test_f02_f04_f05_metrics_change_idempotent_reimport_and_degraded_serp_snapshot(client):
    """
    F02: Changed metrics (KD/Volume/Intent) for A immediately invalidates old approval & OFFICIAL brief.
    F04: Re-importing identical metrics or identical SERP CSV does NOT invalidate approval or create duplicate pending approvals.
    F05: Newer incomplete SERP snapshot (1 URL) degrades A to PARTIAL_SERP_EVIDENCE and blocks OFFICIAL (never keeps old green).
    """
    tc, _ = client
    pid = _setup_two_kw_project(tc, "F02")
    m_csv = "Keyword,Volume,KD,Intent\nquyết toán thuế tncn,2000,25,Informational\n"
    s_csv = _serp_csv("quyết toán thuế tncn", list(range(1, 11)), "orig")
    _upload_and_confirm(tc, pid, "m1.csv", m_csv, report_type="KEYWORD_OVERVIEW")
    _upload_and_confirm(tc, pid, "s1.csv", s_csv, report_type="ORGANIC_RESULTS")
    tc.post(f"/api/v1/projects/{pid}/mapping/preview")
    _approve_all(tc, pid)

    m_a = next(m for m in tc.get(f"/api/v1/projects/{pid}/opportunities").json()["mappings"] if m["primary_keyword"] == "quyết toán thuế tncn")
    assert m_a["eligibility"]["eligible_official"] is True
    rev_before = m_a["revision"]
    aprs_count_before = len(tc.get(f"/api/v1/projects/{pid}/approvals").json()["approvals"])

    # F04: Re-import IDENTICAL metrics & IDENTICAL SERP -> NO invalidation, NO revision bump, NO duplicate approval!
    _upload_and_confirm(tc, pid, "m1_copy.csv", m_csv, report_type="KEYWORD_OVERVIEW")
    _upload_and_confirm(tc, pid, "s1_copy.csv", s_csv, report_type="ORGANIC_RESULTS")
    m_a_same = next(m for m in tc.get(f"/api/v1/projects/{pid}/opportunities").json()["mappings"] if m["primary_keyword"] == "quyết toán thuế tncn")
    assert m_a_same["eligibility"]["eligible_official"] is True
    assert m_a_same["revision"] == rev_before
    assert len(tc.get(f"/api/v1/projects/{pid}/approvals").json()["approvals"]) == aprs_count_before

    # F02: Import CHANGED metrics (KD 25 -> 68, Intent -> Commercial) WITHOUT clicking mapping/preview!
    m_changed = "Keyword,Volume,KD,Intent\nquyết toán thuế tncn,2000,68,Commercial\n"
    _upload_and_confirm(tc, pid, "m2_changed.csv", m_changed, report_type="KEYWORD_OVERVIEW")
    m_a_changed = next(m for m in tc.get(f"/api/v1/projects/{pid}/opportunities").json()["mappings"] if m["primary_keyword"] == "quyết toán thuế tncn")
    assert m_a_changed["eligibility"]["eligible_official"] is False
    assert m_a_changed["is_approved"] is False
    assert m_a_changed["kd"] == 68.0

    # Re-approve so A is OFFICIAL again, then test F05 (newer incomplete SERP snapshot with only 1 URL!)
    _approve_all(tc, pid)
    m_a_reok = next(m for m in tc.get(f"/api/v1/projects/{pid}/opportunities").json()["mappings"] if m["primary_keyword"] == "quyết toán thuế tncn")
    assert m_a_reok["eligibility"]["eligible_official"] is True

    _upload_and_confirm(tc, pid, "s_incomplete.csv", _serp_csv("quyết toán thuế tncn", [1], "inc"), report_type="ORGANIC_RESULTS")
    m_a_degraded = next(m for m in tc.get(f"/api/v1/projects/{pid}/opportunities").json()["mappings"] if m["primary_keyword"] == "quyết toán thuế tncn")
    assert m_a_degraded["eligibility"]["serp_tier"] == "PARTIAL_SERP_EVIDENCE"
    assert m_a_degraded["eligibility"]["eligible_official"] is False
    assert tc.post(f"/api/v1/projects/{pid}/briefs/generate", json={"allow_draft": False, "mapping_ids": [m_a["id"]]}).status_code == 400


def test_f08_f09_atomic_import_rollback_and_stale_approval_409(client, monkeypatch: pytest.MonkeyPatch):
    """
    F08: Simulated DB exception during import confirm rolls back atomically (no half-invalidated mapping/approval).
    F09: Submitting approval for old fingerprint after evidence update returns HTTP 409 and never unlocks OFFICIAL.
    """
    tc, _ = client
    from app.domain import mapping_engine

    pid = _setup_two_kw_project(tc, "F08")
    _upload_and_confirm(tc, pid, "m1.csv", "Keyword,Volume,KD,Intent\nquyết toán thuế tncn,1500,20,Informational\n", report_type="KEYWORD_OVERVIEW")
    _upload_and_confirm(tc, pid, "s1.csv", _serp_csv("quyết toán thuế tncn", list(range(1, 11)), "ok"), report_type="ORGANIC_RESULTS")
    tc.post(f"/api/v1/projects/{pid}/mapping/preview")

    # Capture exact PENDING approval ID for mapping A before updating evidence (for F08 & F09)
    m_a_id = next(
        m["id"]
        for m in tc.get(f"/api/v1/projects/{pid}/opportunities").json()["mappings"]
        if m["primary_keyword"] == "quyết toán thuế tncn"
    )
    aprs_before = tc.get(f"/api/v1/projects/{pid}/approvals").json()["approvals"]
    old_pending_a = next(a for a in aprs_before if a["target_ref"] == m_a_id and a["status"] == "PENDING")

    # Approve it first so we can test atomic rollback on F08
    assert tc.post(f"/api/v1/projects/{pid}/approvals/{old_pending_a['id']}", json={"decision": "APPROVED"}).status_code == 200
    m_ok = next(m for m in tc.get(f"/api/v1/projects/{pid}/opportunities").json()["mappings"] if m["primary_keyword"] == "quyết toán thuế tncn")
    assert m_ok["is_approved"] is True
    rev_ok = m_ok["revision"]

    # F08: Inject failure inside freshness reconciliation during confirm -> must rollback entire import transaction!
    prev_boom = tc.post(
        f"/api/v1/projects/{pid}/imports/preview",
        data={"report_type": "ORGANIC_RESULTS", "locale": "en-US"},
        files={"file": ("boom.csv", _serp_csv("quyết toán thuế tncn", list(range(1, 11)), "boom").encode("utf-8"), "text/csv")},
    ).json()

    orig_reconcile = mapping_engine.reconcile_project_freshness

    def _boom_reconcile(*args, **kwargs):
        raise RuntimeError("Simulated SQLite crash during import reconciliation")

    monkeypatch.setattr(mapping_engine, "reconcile_project_freshness", _boom_reconcile)
    with pytest.raises(RuntimeError):
        tc.post(
            f"/api/v1/projects/{pid}/imports/confirm",
            json={
                "upload_id": prev_boom["upload_id"],
                "report_type": "ORGANIC_RESULTS",
                "market": "VN",
                "locale": "en-US",
                "column_mapping": prev_boom["suggested_mapping"],
            },
        )
    monkeypatch.setattr(mapping_engine, "reconcile_project_freshness", orig_reconcile)

    # Because transaction rolled back atomically, mapping A MUST still be approved at rev_ok!
    m_after_rollback = next(m for m in tc.get(f"/api/v1/projects/{pid}/opportunities").json()["mappings"] if m["primary_keyword"] == "quyết toán thuế tncn")
    assert m_after_rollback["is_approved"] is True
    assert m_after_rollback["revision"] == rev_ok

    # F09: Now trigger real evidence update -> creates new pending approval (rev+1); capture it, update evidence AGAIN, try approving superseded ID -> 409!
    _upload_and_confirm(tc, pid, "s2.csv", _serp_csv("quyết toán thuế tncn", list(range(1, 11)), "v2"), report_type="ORGANIC_RESULTS")
    pending_v2 = next(
        a for a in tc.get(f"/api/v1/projects/{pid}/approvals").json()["approvals"]
        if a["target_ref"] == m_ok["id"] and a["status"] == "PENDING"
    )
    _upload_and_confirm(tc, pid, "s3.csv", _serp_csv("quyết toán thuế tncn", list(range(1, 11)), "v3"), report_type="ORGANIC_RESULTS")

    stale_submit = tc.post(f"/api/v1/projects/{pid}/approvals/{pending_v2['id']}", json={"decision": "APPROVED"})
    assert stale_submit.status_code == 409
    m_still_blocked = next(m for m in tc.get(f"/api/v1/projects/{pid}/opportunities").json()["mappings"] if m["primary_keyword"] == "quyết toán thuế tncn")
    assert m_still_blocked["eligibility"]["eligible_official"] is False
