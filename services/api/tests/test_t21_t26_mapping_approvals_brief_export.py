from __future__ import annotations

import io
import openpyxl


def test_t22_t23_t24_t25_t26_mapping_approvals_brief_and_xlsx_export(client):
    tc, _ = client
    tc.put("/api/v1/settings/ai", json={"provider": "mock", "set_active": True})

    # Create non-demo project Z42 (verify zero hardcoded 'Luong')
    pid = tc.post(
        "/api/v1/projects",
        json={
            "code": "Z42",
            "name": "Quản trị dòng tiền SME",
            "topic_pillar_code": "Z42",
            "topic_pillar_name": "Quản trị dòng tiền",
            "primary_keyword": "quản trị dòng tiền",
            "secondary_keywords": ["công cụ tính dòng tiền", "mẫu file excel dòng tiền"],
            "business_goal": "Thu hút CFO SME đăng ký khóa học",
            "target_audience": "Chủ doanh nghiệp & CFO SME",
        },
    ).json()["project"]["id"]

    # Step 02: Analyze topic -> creates ARTICLE groups + TOOL/DOWNLOAD group
    an = tc.post(f"/api/v1/projects/{pid}/analyze-topic")
    assert an.status_code == 200

    # Step 04: Upload Semrush metrics (en-US `9,900`) WITHOUT organic first -> test DRAFT & SERP_NOT_VERIFIED
    metrics_csv = (
        "Keyword,Volume,KD,Intent\n"
        "quản trị dòng tiền,\"9,900\",42,Informational\n"
        "công cụ tính dòng tiền,540,28,Transactional\n"
        "cách xử lý quản trị dòng tiền,110,20,Informational\n"
    ).encode("utf-8")
    p1 = tc.post(
        f"/api/v1/projects/{pid}/imports/preview",
        data={"report_type": "KEYWORD_OVERVIEW", "locale": "en-US"},
        files={"file": ("z42_metrics.csv", metrics_csv, "text/csv")},
    ).json()
    tc.post(
        f"/api/v1/projects/{pid}/imports/confirm",
        json={
            "upload_id": p1["upload_id"],
            "report_type": "KEYWORD_OVERVIEW",
            "market": "VN",
            "locale": "en-US",
            "column_mapping": p1["suggested_mapping"],
        },
    )

    # Step 06: Generate mapping preview without SERP -> DRAFT_SERP_NOT_VERIFIED
    mp = tc.post(f"/api/v1/projects/{pid}/mapping/preview")
    assert mp.status_code == 200
    mp_body = mp.json()
    assert mp_body["serp_status"] == "SERP_NOT_VERIFIED"
    assert mp_body["plan_mode"] == "DRAFT_SERP_NOT_VERIFIED"

    opps = tc.get(f"/api/v1/projects/{pid}/opportunities").json()
    # T23: TOOL/DOWNLOAD asset is separated and NEVER counts toward ARTICLE quota!
    assert len(opps["non_article_assets"]) >= 1
    for asset in opps["non_article_assets"]:
        assert asset["counts_toward_article_quota"] is False
    # T22: Merge/split framed as proposal
    assert any("ĐỀ XUẤT" in m["merge_split_proposal"] for m in opps["mappings"])

    # T24: Trying to generate OFFICIAL brief before approval & SERP MUST fail!
    fail_official = tc.post(f"/api/v1/projects/{pid}/briefs/generate", json={"allow_draft": False})
    assert fail_official.status_code == 400

    # Draft brief IS allowed and explicitly stamped SERP_NOT_VERIFIED
    draft_br = tc.post(f"/api/v1/projects/{pid}/briefs/generate", json={"allow_draft": True})
    assert draft_br.status_code == 200
    assert draft_br.json()["official_count"] == 0
    assert draft_br.json()["draft_count"] >= 1
    first_draft = draft_br.json()["briefs"][0]
    assert first_draft["brief_mode"] == "DRAFT"
    assert first_draft["status"] == "SERP_NOT_VERIFIED"
    assert first_draft["search_intent_status"] == "ASSUMED"

    # Now upload sufficient ORGANIC_RESULTS (>=3 ranked organic URLs per keyword) AND approve mappings -> OFFICIAL brief succeeds!
    org_csv = (
        "Keyword,Position,URL,Title\n"
        "quản trị dòng tiền,1,https://finz.vn/blog/quan-tri-dong-tien-1,Quản trị dòng tiền SME\n"
        "quản trị dòng tiền,2,https://finz.vn/blog/quan-tri-dong-tien-2,Hướng dẫn dòng tiền\n"
        "quản trị dòng tiền,3,https://finz.vn/blog/quan-tri-dong-tien-3,Kiểm soát dòng tiền\n"
        "cách xử lý quản trị dòng tiền,1,https://finz.vn/blog/xu-ly-dong-tien-1,Cách xử lý dòng tiền\n"
        "cách xử lý quản trị dòng tiền,2,https://finz.vn/blog/xu-ly-dong-tien-2,Xử lý thiếu hụt dòng tiền\n"
        "cách xử lý quản trị dòng tiền,3,https://finz.vn/blog/xu-ly-dong-tien-3,Giải pháp dòng tiền SME\n"
        "công cụ tính dòng tiền,1,https://finz.vn/cong-cu/tinh-dong-tien-1,Công cụ tính dòng tiền\n"
        "công cụ tính dòng tiền,2,https://finz.vn/cong-cu/tinh-dong-tien-2,Calculator dòng tiền\n"
        "công cụ tính dòng tiền,3,https://finz.vn/cong-cu/tinh-dong-tien-3,Công cụ lập dòng tiền\n"
    ).encode("utf-8")
    p2 = tc.post(
        f"/api/v1/projects/{pid}/imports/preview",
        data={"report_type": "ORGANIC_RESULTS", "locale": "en-US"},
        files={"file": ("z42_org.csv", org_csv, "text/csv")},
    ).json()
    tc.post(
        f"/api/v1/projects/{pid}/imports/confirm",
        json={
            "upload_id": p2["upload_id"],
            "report_type": "ORGANIC_RESULTS",
            "market": "VN",
            "locale": "en-US",
            "column_mapping": p2["suggested_mapping"],
        },
    )
    tc.post(f"/api/v1/projects/{pid}/mapping/preview")

    # Approve all pending mappings
    aprs = tc.get(f"/api/v1/projects/{pid}/approvals").json()["approvals"]
    for a in aprs:
        if a["status"] == "PENDING":
            dec = tc.post(
                f"/api/v1/projects/{pid}/approvals/{a['id']}",
                json={"decision": "APPROVED", "decision_note": "Đủ bằng chứng", "decided_by": "SEO Lead"},
            )
            assert dec.status_code == 200

    official_br = tc.post(f"/api/v1/projects/{pid}/briefs/generate", json={"allow_draft": False})
    assert official_br.status_code == 200
    assert official_br.json()["official_count"] >= 1
    b0 = official_br.json()["briefs"][0]
    assert b0["brief_mode"] == "OFFICIAL"
    # T25: Whole-article Writing Strategy, 1 primary formula, <=2 supporting, 3-6 tactics, NOT forced per H2
    ws = b0["writing_strategy"]
    assert ws["scope"] == "WHOLE_ARTICLE"
    assert ws["per_heading_enforcement"] is False
    assert ws["primary_formula"]
    assert 1 <= len(ws["supporting_formulas"]) <= 2
    assert 3 <= len(ws["engagement_tactics"]) <= 6

    # T26: XLSX export has exact 3 logical sheets and dynamic filename (NO hardcoded 'Luong')
    exp = tc.post(f"/api/v1/projects/{pid}/exports/download", json={"format": "xlsx"})
    assert exp.status_code == 200
    fname = exp.headers.get("x-finz-export-filename", "")
    assert "Z42" in fname
    assert "Luong" not in fname and "luong" not in fname

    wb = openpyxl.load_workbook(io.BytesIO(exp.content))
    assert len(wb.sheetnames) == 5
    assert [name.split(" - ")[0] for name in wb.sheetnames] == ["Keyword Research", "SERP Check", "Keyword Mapping", "Nhat ky", "SEO Content Brief"]
    assert wb.worksheets[4].max_row >= 2

    # CSV, JSON, HTML printable exports also work cleanly
    for fmt in ("csv", "json", "html"):
        r = tc.post(f"/api/v1/projects/{pid}/exports/download", json={"format": fmt})
        assert r.status_code == 200
        assert len(r.content) > 50
