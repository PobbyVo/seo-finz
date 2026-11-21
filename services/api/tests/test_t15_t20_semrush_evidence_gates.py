from __future__ import annotations


def test_t15_t16_t17_t18_t19_t20_semrush_upload_locale_dedup_organic_and_gates(client):
    tc, _ = client
    tc.put("/api/v1/settings/ai", json={"provider": "mock", "set_active": True})
    pid = tc.post(
        "/api/v1/projects",
        json={
            "code": "P18",
            "name": "Quyết toán thuế",
            "primary_keyword": "quyết toán thuế doanh nghiệp",
            "secondary_keywords": ["dịch vụ quyết toán thuế b2b"],
            "business_goal": "Tăng khách hàng B2B",
            "target_audience": "Kế toán trưởng SME",
        },
    ).json()["project"]["id"]

    # T15: Manual Semrush request with UI steps, zero Semrush API/MCP
    req_res = tc.post(
        f"/api/v1/projects/{pid}/research-requests",
        json={
            "items": [
                {"seed_keyword": "quyết toán thuế doanh nghiệp", "report_type": "KEYWORD_OVERVIEW", "market": "VN", "purpose": "Lấy metrics"},
                {"seed_keyword": "quyết toán thuế doanh nghiệp", "report_type": "ORGANIC_RESULTS", "market": "VN", "purpose": "Kiểm chứng SERP"},
            ]
        },
    )
    assert req_res.status_code == 201
    reqs = req_res.json()["research_requests"]
    assert reqs[0]["status"] == "WAITING_USER"
    assert len(reqs[0]["semrush_steps"]) >= 3

    # Build CSV with >250 rows (T17), vi-VN locale numbers `9.900` & `45,5` (T18), missing KD (null != 0),
    # duplicate keyword (MUST NOT sum volume!), and a low-volume B2B keyword (T13: volume=20 preserved!)
    lines = ["Keyword;Volume;KD;Intent;CPC"]
    lines.append("quyết toán thuế doanh nghiệp;9.900;45,5;Informational;1,2")
    lines.append("quyết toán thuế doanh nghiệp;9.900;45,5;Informational;1,2")  # Duplicate!
    lines.append("dịch vụ quyết toán thuế b2b;20;;Commercial;2,5")  # Low volume + missing KD (null != 0)
    lines.append("từ khóa volume bằng 0;0;12;Informational;0")  # Explicit 0 != null
    for i in range(1, 260):
        lines.append(f"từ khóa mở rộng {i};1.{i:03d};30;Informational;0,5")
    csv_bytes = "\n".join(lines).encode("utf-8")

    # T16: Preview MUST NOT write evidence to SQLite
    prev = tc.post(
        f"/api/v1/projects/{pid}/imports/preview",
        data={"research_request_id": reqs[0]["id"], "report_type": "KEYWORD_OVERVIEW", "locale": "vi-VN"},
        files={"file": ("semrush_vi.csv", csv_bytes, "text/csv")},
    )
    assert prev.status_code == 200
    pbody = prev.json()
    assert pbody["saved_to_research"] is False
    assert pbody["total_rows"] == 263  # > 200 rows detected!
    ev_before = tc.get(f"/api/v1/projects/{pid}/evidence").json()
    assert ev_before["total_evidence_rows"] == 0

    # Confirm import processes ALL 263 rows (T17)
    conf = tc.post(
        f"/api/v1/projects/{pid}/imports/confirm",
        json={
            "upload_id": pbody["upload_id"],
            "research_request_id": reqs[0]["id"],
            "report_type": "KEYWORD_OVERVIEW",
            "market": "VN",
            "locale": "vi-VN",
            "column_mapping": pbody["suggested_mapping"],
        },
    )
    assert conf.status_code == 200
    cbody = conf.json()
    assert cbody["status"] == "PROCESS_COMPLETED"
    assert cbody["quality_approved"] is False
    assert cbody["total_raw_rows"] == 263
    assert cbody["duplicate_rows_detected"] == 1
    assert cbody["total_normalized_rows"] == 262

    # Check parsed values (T18 + T13 + T19 + T20)
    ev = tc.get(f"/api/v1/projects/{pid}/evidence?limit=300").json()
    non_dup = {r["keyword"]: r for r in ev["rows"] if not r["is_duplicate"]}
    # vi-VN: 9.900 == 9900 (NOT 9.9 and NOT summed to 19800!), 45,5 == 45.5
    assert non_dup["quyết toán thuế doanh nghiệp"]["volume"] == 9900
    assert non_dup["quyết toán thuế doanh nghiệp"]["kd"] == 45.5
    # Missing KD is None, NOT 0; explicit 0 volume is 0, NOT None
    assert non_dup["dịch vụ quyết toán thuế b2b"]["volume"] == 20
    assert non_dup["dịch vụ quyết toán thuế b2b"]["kd"] is None
    assert non_dup["từ khóa volume bằng 0"]["volume"] == 0
    # T13: Low-volume B2B keyword preserved in F3
    assert "dịch vụ quyết toán thuế b2b" in ev["summary"]["low_volume_keywords"]
    # T19 & T20: Full metrics alone NEVER auto-promote READY_FOR_BRIEF; without ORGANIC_RESULTS -> SERP_NOT_VERIFIED
    assert ev["summary"]["ready_for_brief"] is False
    assert ev["summary"]["serp_status"] == "SERP_NOT_VERIFIED"

    # Dedicated ORGANIC_RESULTS parser test
    organic_csv = (
        "Keyword,Position,URL,Title\n"
        "quyết toán thuế doanh nghiệp,1,https://example.vn/blog/quyet-toan-thue,Hướng dẫn quyết toán thuế\n"
        "quyết toán thuế doanh nghiệp,2,https://example.vn/cong-cu/tinh-thue,Công cụ tính thuế\n"
    ).encode("utf-8")
    oprev = tc.post(
        f"/api/v1/projects/{pid}/imports/preview",
        data={"research_request_id": reqs[1]["id"], "report_type": "ORGANIC_RESULTS", "locale": "en-US"},
        files={"file": ("organic.csv", organic_csv, "text/csv")},
    ).json()
    oconf = tc.post(
        f"/api/v1/projects/{pid}/imports/confirm",
        json={
            "upload_id": oprev["upload_id"],
            "research_request_id": reqs[1]["id"],
            "report_type": "ORGANIC_RESULTS",
            "market": "VN",
            "locale": "en-US",
            "column_mapping": oprev["suggested_mapping"],
        },
    )
    assert oconf.status_code == 200
    ev_after = tc.get(f"/api/v1/projects/{pid}/evidence?row_type=ORGANIC_RESULTS").json()
    assert len(ev_after["rows"]) == 2
    assert ev_after["rows"][0]["organic_url"].startswith("https://")
    assert ev_after["rows"][1]["organic_page_type"] == "TOOL"
    assert ev_after["summary"]["serp_verified"] is True
    # Still NOT ready_for_brief because human has not approved mapping yet (F6)!
    assert ev_after["summary"]["ready_for_brief"] is False
