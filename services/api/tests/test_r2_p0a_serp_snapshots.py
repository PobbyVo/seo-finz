from __future__ import annotations

import time
from pathlib import Path

from app.domain.eligibility_policy import evaluate_serp_for_keyword, load_project_policy_context
from app.models import Project

FIXTURES = Path(__file__).parent / "fixtures"


def _setup_project(tc, *, code: str, primary_keyword: str, market: str = "VN", secondary_keywords: list[str] | None = None) -> str:
    tc.put("/api/v1/settings/ai", json={"provider": "mock", "set_active": True})
    resp = tc.post(
        "/api/v1/projects",
        json={
            "code": code,
            "name": f"Project {code}",
            "topic_pillar_code": code,
            "topic_pillar_name": f"Pillar {code}",
            "primary_keyword": primary_keyword,
            "secondary_keywords": secondary_keywords or [],
            "business_goal": "Tư vấn kế toán thuế B2B cho SME",
            "target_audience": "Kế toán trưởng & HR SME",
            "market": market,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["project"]["id"]


def _upload_and_confirm(
    tc,
    pid: str,
    filename: str,
    csv_text: str,
    *,
    report_type: str,
    market: str = "VN",
    locale: str = "en-US",
    research_request_id: str | None = None,
    target_keyword: str | None = None,
):
    data = {"report_type": report_type, "locale": locale}
    if research_request_id:
        data["research_request_id"] = research_request_id
    if target_keyword:
        data["target_keyword"] = target_keyword
    prev = tc.post(
        f"/api/v1/projects/{pid}/imports/preview",
        data=data,
        files={"file": (filename, csv_text.encode("utf-8"), "text/csv")},
    )
    assert prev.status_code == 200, prev.text
    pbody = prev.json()
    payload = {
        "upload_id": pbody["upload_id"],
        "research_request_id": research_request_id,
        "report_type": report_type,
        "market": market,
        "locale": locale,
        "column_mapping": pbody["suggested_mapping"],
    }
    if target_keyword:
        payload["target_keyword"] = target_keyword
    conf = tc.post(f"/api/v1/projects/{pid}/imports/confirm", json=payload)
    assert conf.status_code == 200, conf.text
    return conf.json()


def _approve_all_pending(tc, pid: str):
    aprs = tc.get(f"/api/v1/projects/{pid}/approvals").json()["approvals"]
    for a in aprs:
        if a["status"] == "PENDING":
            r = tc.post(f"/api/v1/projects/{pid}/approvals/{a['id']}", json={"decision": "APPROVED"})
            assert r.status_code == 200, r.text


def _serp_csv_for_positions(keyword: str, positions: list[int], domain_prefix: str = "site") -> str:
    lines = ["Keyword,Position,URL,Title"]
    for pos in positions:
        lines.append(f"{keyword},{pos},https://{domain_prefix}{pos}.vn/bai-viet-{pos},Tiêu đề {pos}")
    return "\n".join(lines) + "\n"


def test_s01_single_coherent_top10_snapshot_certified_with_provenance(client):
    """S01: Single valid 10-rank organic snapshot for keyword A/VN -> TOP_10_VERIFIED with batch & timestamp provenance."""
    tc, _ = client
    pid = _setup_project(tc, code="S01", primary_keyword="thuế thu nhập cá nhân")
    _upload_and_confirm(
        tc, pid, "m.csv",
        "Keyword,Volume,KD,Intent\nthuế thu nhập cá nhân,2400,30,Informational\n",
        report_type="KEYWORD_OVERVIEW",
    )
    serp_res = _upload_and_confirm(
        tc, pid, "serp10.csv",
        _serp_csv_for_positions("thuế thu nhập cá nhân", list(range(1, 11)), "top10"),
        report_type="ORGANIC_RESULTS",
    )
    tc.post(f"/api/v1/projects/{pid}/mapping/preview")
    _approve_all_pending(tc, pid)

    opps = tc.get(f"/api/v1/projects/{pid}/opportunities").json()
    m = opps["mappings"][0]
    serp_ev = m["eligibility"]["serp_evidence"]
    assert m["eligibility"]["serp_tier"] == "TOP_10_VERIFIED"
    assert m["eligibility"]["top10_verified"] is True
    assert m["eligibility"]["eligible_official"] is True
    assert serp_ev["selected_batch_id"] == serp_res["batch_id"]
    assert serp_ev["snapshot_identity"]["batch_id"] == serp_res["batch_id"]
    assert serp_ev["snapshot_identity"]["observed_at"] is not None
    assert serp_ev["snapshot_identity"]["timestamp_kind"] in ("SOURCE_OBSERVED", "INGESTED_AT")


def test_s02_s03_no_cross_batch_top10_or_official_merging(client):
    """
    S02: Batch 1 ranks 1..5 + Batch 2 ranks 6..10 -> NEVER TOP_10_VERIFIED!
    S03: Batch 1 (1 URL) + Batch 2 (1 URL) + Batch 3 (1 URL) -> NEVER SERP_VERIFIED or OFFICIAL!
    """
    tc, _ = client
    # S02: 1..5 in batch 1 + 6..10 in batch 2
    pid2 = _setup_project(tc, code="S02", primary_keyword="kê khai thuế quý")
    _upload_and_confirm(
        tc, pid2, "m.csv",
        "Keyword,Volume,KD,Intent\nkê khai thuế quý,1500,25,Informational\n",
        report_type="KEYWORD_OVERVIEW",
    )
    _upload_and_confirm(
        tc, pid2, "serp_1_5.csv",
        _serp_csv_for_positions("kê khai thuế quý", [1, 2, 3, 4, 5], "b1site"),
        report_type="ORGANIC_RESULTS",
    )
    b2 = _upload_and_confirm(
        tc, pid2, "serp_6_10.csv",
        _serp_csv_for_positions("kê khai thuế quý", [6, 7, 8, 9, 10], "b2site"),
        report_type="ORGANIC_RESULTS",
    )
    tc.post(f"/api/v1/projects/{pid2}/mapping/preview")
    _approve_all_pending(tc, pid2)

    m2 = tc.get(f"/api/v1/projects/{pid2}/opportunities").json()["mappings"][0]
    assert m2["eligibility"]["top10_verified"] is False
    assert m2["eligibility"]["serp_tier"] != "TOP_10_VERIFIED"
    assert m2["eligibility"]["serp_evidence"]["batch_ids"] == [b2["batch_id"]]

    # S03: 3 separate batches, 1 URL each -> NEVER merged into 3 URLs!
    pid3 = _setup_project(tc, code="S03", primary_keyword="quyết toán thuế cuối năm")
    _upload_and_confirm(
        tc, pid3, "m.csv",
        "Keyword,Volume,KD,Intent\nquyết toán thuế cuối năm,900,20,Informational\n",
        report_type="KEYWORD_OVERVIEW",
    )
    for idx in (1, 2, 3):
        _upload_and_confirm(
            tc, pid3, f"serp_single_{idx}.csv",
            _serp_csv_for_positions("quyết toán thuế cuối năm", [idx], f"single{idx}"),
            report_type="ORGANIC_RESULTS",
        )
    tc.post(f"/api/v1/projects/{pid3}/mapping/preview")
    _approve_all_pending(tc, pid3)

    m3 = tc.get(f"/api/v1/projects/{pid3}/opportunities").json()["mappings"][0]
    assert m3["eligibility"]["serp_tier"] == "PARTIAL_SERP_EVIDENCE"
    assert m3["eligibility"]["eligible_official"] is False
    assert m3["eligibility"]["serp_evidence"]["valid_organic_count"] == 1
    assert tc.post(f"/api/v1/projects/{pid3}/briefs/generate", json={"allow_draft": False}).status_code == 400


def test_s04_s05_s06_conflicting_snapshots_order_independence_market_isolation_and_ai_overview(client):
    """
    S04: Conflicting rank-1 URLs across two snapshots -> deterministic single snapshot selected regardless of retrieval order, NEVER combined.
    S05: Mixed markets VN/US and keywords A/B -> strict isolation.
    S06: AI Overview at rank 1 + Organic rank 1 -> no false duplicate organic rank and no artificial TOP10.
    """
    tc, _ = client
    from app import db as db_mod

    pid = _setup_project(tc, code="S04", primary_keyword="mức đóng bhxh bắt buộc", market="VN")
    _upload_and_confirm(
        tc, pid, "m.csv",
        "Keyword,Volume,KD,Intent\nmức đóng bhxh bắt buộc,1800,28,Informational\n",
        report_type="KEYWORD_OVERVIEW",
    )

    # Snapshot 1: rank 1..4 with alpha domain + AI Overview at rank 1 (S06)
    snap1_csv = (
        "Keyword,Position,Type,URL,Title\n"
        "mức đóng bhxh bắt buộc,1,AI Overview,https://ai-overview.vn/summary,AI Summary\n"
        "mức đóng bhxh bắt buộc,1,Organic,https://alpha1.vn/bhxh,Alpha 1\n"
        "mức đóng bhxh bắt buộc,2,Organic,https://alpha2.vn/bhxh,Alpha 2\n"
        "mức đóng bhxh bắt buộc,3,Organic,https://alpha3.vn/bhxh,Alpha 3\n"
        "mức đóng bhxh bắt buộc,4,Organic,https://alpha4.vn/bhxh,Alpha 4\n"
    )
    b1 = _upload_and_confirm(tc, pid, "snap1.csv", snap1_csv, report_type="ORGANIC_RESULTS", market="VN")

    # Verify S06 on snap1: AI Overview at pos 1 + Organic at pos 1 => 0 duplicate organic ranks, NOT TOP10
    tc.post(f"/api/v1/projects/{pid}/mapping/preview")
    m_s1 = tc.get(f"/api/v1/projects/{pid}/opportunities").json()["mappings"][0]
    assert m_s1["eligibility"]["serp_evidence"]["duplicate_ranks"] == []
    assert m_s1["eligibility"]["serp_evidence"]["ai_overview_count"] == 1
    assert m_s1["eligibility"]["serp_tier"] == "SERP_VERIFIED"
    assert m_s1["eligibility"]["top10_verified"] is False

    # Snapshot 2: conflicting rank-1 URL (beta1.vn instead of alpha1.vn), 3 URLs
    snap2_csv = (
        "Keyword,Position,Type,URL,Title\n"
        "mức đóng bhxh bắt buộc,1,Organic,https://beta1.vn/bhxh,Beta 1\n"
        "mức đóng bhxh bắt buộc,2,Organic,https://beta2.vn/bhxh,Beta 2\n"
        "mức đóng bhxh bắt buộc,3,Organic,https://beta3.vn/bhxh,Beta 3\n"
    )
    b2 = _upload_and_confirm(tc, pid, "snap2.csv", snap2_csv, report_type="ORGANIC_RESULTS", market="VN")

    # Upload US market Top 10 and another keyword Top 10 (S05) -> MUST NOT bleed into VN/keyword A!
    _upload_and_confirm(
        tc, pid, "snap_us.csv",
        _serp_csv_for_positions("mức đóng bhxh bắt buộc", list(range(1, 11)), "usonly"),
        report_type="ORGANIC_RESULTS",
        market="US",
    )
    _upload_and_confirm(
        tc, pid, "snap_other_kw.csv",
        _serp_csv_for_positions("từ khóa hoàn toàn khác", list(range(1, 11)), "otherkw"),
        report_type="ORGANIC_RESULTS",
        market="VN",
    )

    # Direct order-independence verification (S04): forward vs reversed organic_rows must yield identical result!
    db = db_mod.SessionLocal()
    try:
        proj = db.get(Project, pid)
        ctx = load_project_policy_context(db, proj)
        org_rows = [r for r in ctx["evidence_rows"] if r.row_type == "ORGANIC_RESULTS"]
        eval_fwd = evaluate_serp_for_keyword(proj, "mức đóng bhxh bắt buộc", org_rows, ctx["batches_by_id"], ctx["uploads_by_id"], batch_integrity_by_id=ctx.get("batch_integrity_by_id"))
        eval_rev = evaluate_serp_for_keyword(proj, "mức đóng bhxh bắt buộc", list(reversed(org_rows)), ctx["batches_by_id"], ctx["uploads_by_id"], batch_integrity_by_id=ctx.get("batch_integrity_by_id"))
    finally:
        db.close()

    assert eval_fwd["selected_batch_id"] == b2["batch_id"]
    assert eval_fwd["selected_batch_id"] == eval_rev["selected_batch_id"]
    assert eval_fwd["serp_evidence_hash"] == eval_rev["serp_evidence_hash"]
    assert eval_fwd["sample_urls"][0] == "https://beta1.vn/bhxh"
    assert eval_fwd["valid_organic_count"] == 3  # NEVER combined with b1 (would be 7)!
    assert eval_fwd["top10_verified"] is False
    assert b1["batch_id"] not in eval_fwd["batch_ids"]


def test_s07_s08_full_digest_beyond_20_rows_and_real_semrush_fixture(client):
    """
    S07: Changing the 21st/99th supporting URL MUST change serp_evidence_hash & mapping fingerprint;
         adding an irrelevant keyword MUST NOT change keyword A's digest.
    S08: Real Semrush SERP fixture (104 rows incl. 5 AI Overview, no Keyword column) parses into 1 coherent TOP_10_VERIFIED batch.
    """
    tc, _ = client
    pid = _setup_project(tc, code="S07", primary_keyword="lương net và gross là gì")
    reqs = tc.post(
        f"/api/v1/projects/{pid}/research-requests",
        json={
            "items": [
                {"seed_keyword": "lương net và gross là gì", "report_type": "KEYWORD_OVERVIEW", "market": "VN"},
                {"seed_keyword": "lương net và gross là gì", "report_type": "ORGANIC_RESULTS", "market": "VN"},
            ]
        },
    ).json()["research_requests"]

    metrics_text = (FIXTURES / "semrush_metrics_real_sample.csv").read_text(encoding="utf-8")
    serp_text = (FIXTURES / "semrush_serp_real_sample.csv").read_text(encoding="utf-8")
    _upload_and_confirm(tc, pid, "m.csv", metrics_text, report_type="KEYWORD_OVERVIEW", research_request_id=reqs[0]["id"])
    b_real = _upload_and_confirm(tc, pid, "real_serp.csv", serp_text, report_type="ORGANIC_RESULTS", research_request_id=reqs[1]["id"])
    tc.post(f"/api/v1/projects/{pid}/mapping/preview")

    m_before = tc.get(f"/api/v1/projects/{pid}/opportunities").json()["mappings"][0]
    hash_before = m_before["eligibility"]["serp_evidence"]["serp_evidence_hash"]
    fp_before = m_before["content_fingerprint"]
    assert m_before["eligibility"]["serp_tier"] == "TOP_10_VERIFIED"
    assert m_before["eligibility"]["serp_evidence"]["selected_batch_id"] == b_real["batch_id"]
    assert len(hash_before) >= 32  # Full cryptographic SHA-256 digest, not truncated weak 20-row hash

    # Import SERP for an unrelated keyword -> MUST NOT change keyword A's hash or fingerprint!
    _upload_and_confirm(
        tc, pid, "irrelevant_kw.csv",
        _serp_csv_for_positions("chủ đề hoàn toàn không liên quan", list(range(1, 11)), "irrel"),
        report_type="ORGANIC_RESULTS",
    )
    m_after_irrel = tc.get(f"/api/v1/projects/{pid}/opportunities").json()["mappings"][0]
    assert m_after_irrel["eligibility"]["serp_evidence"]["serp_evidence_hash"] == hash_before
    assert m_after_irrel["content_fingerprint"] == fp_before

    # Now modify ONLY the 25th organic URL (row > 20!) in the real Semrush SERP fixture -> hash MUST change!
    lines = serp_text.splitlines()
    mutated_lines = list(lines)
    # Line index 30 is around position 25 (base.vn)
    assert "base.vn" in mutated_lines[30]
    mutated_lines[30] = mutated_lines[30].replace("base.vn/blog/luong-gross-va-luong-net/", "base.vn/blog/luong-gross-va-luong-net-changed-v2/")
    mutated_serp = "\n".join(mutated_lines) + "\n"

    _upload_and_confirm(tc, pid, "real_serp_v2.csv", mutated_serp, report_type="ORGANIC_RESULTS", research_request_id=reqs[1]["id"])
    m_after_mut = tc.get(f"/api/v1/projects/{pid}/opportunities").json()["mappings"][0]
    hash_after = m_after_mut["eligibility"]["serp_evidence"]["serp_evidence_hash"]
    assert hash_after != hash_before


def test_s09_s10_malformed_binding_duplicate_rank_and_multi_snapshot_performance(client):
    """
    S09: Duplicate organic rank in Top 10, empty keyword binding, invalid URLs/positions -> CANNOT certify snapshot.
    S10: Many snapshots/keywords remain bounded in runtime and deterministic.
    """
    tc, _ = client
    pid = _setup_project(tc, code="S09", primary_keyword="hợp đồng lao động thử việc")
    _upload_and_confirm(
        tc, pid, "m.csv",
        "Keyword,Volume,KD,Intent\nhợp đồng lao động thử việc,1100,22,Informational\n",
        report_type="KEYWORD_OVERVIEW",
    )

    # S09a: No keyword column AND no target_keyword/request -> cannot certify!
    no_kw_csv = "Position,Type,URL\n1,Organic,https://a.vn/1\n2,Organic,https://a.vn/2\n3,Organic,https://a.vn/3\n"
    _upload_and_confirm(tc, pid, "no_kw.csv", no_kw_csv, report_type="ORGANIC_RESULTS")
    tc.post(f"/api/v1/projects/{pid}/mapping/preview")
    m_no_kw = tc.get(f"/api/v1/projects/{pid}/opportunities").json()["mappings"][0]
    assert m_no_kw["eligibility"]["serp_tier"] == "SERP_NOT_VERIFIED"
    assert m_no_kw["eligibility"]["eligible_official"] is False

    # S09b: Duplicate organic rank (two distinct Organic URLs both claiming rank #1) -> cannot certify!
    dup_rank_csv = (
        "Keyword,Position,Type,URL\n"
        "hợp đồng lao động thử việc,1,Organic,https://dupA.vn/1\n"
        "hợp đồng lao động thử việc,1,Organic,https://dupB.vn/1\n"
        "hợp đồng lao động thử việc,2,Organic,https://dupC.vn/2\n"
        "hợp đồng lao động thử việc,3,Organic,https://dupD.vn/3\n"
    )
    _upload_and_confirm(tc, pid, "dup_rank.csv", dup_rank_csv, report_type="ORGANIC_RESULTS")
    _approve_all_pending(tc, pid)
    m_dup = tc.get(f"/api/v1/projects/{pid}/opportunities").json()["mappings"][0]
    assert m_dup["eligibility"]["serp_evidence"]["duplicate_ranks"] == [1]
    assert m_dup["eligibility"]["serp_evidence"]["serp_sufficient"] is False
    assert m_dup["eligibility"]["top10_verified"] is False
    assert m_dup["eligibility"]["eligible_official"] is False

    # S10: Bounded performance with 12 snapshots across multiple keywords
    t0 = time.perf_counter()
    for i in range(12):
        kw = "hợp đồng lao động thử việc" if i == 11 else f"từ khóa phụ {i}"
        _upload_and_confirm(
            tc, pid, f"perf_{i}.csv",
            _serp_csv_for_positions(kw, list(range(1, 11)), f"perf{i}s"),
            report_type="ORGANIC_RESULTS",
        )
    opps_perf = tc.get(f"/api/v1/projects/{pid}/opportunities").json()
    elapsed = time.perf_counter() - t0
    assert elapsed < 10.0
    assert opps_perf["mappings"][0]["eligibility"]["serp_tier"] == "TOP_10_VERIFIED"
