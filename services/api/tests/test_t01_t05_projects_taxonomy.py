from __future__ import annotations

import io
import openpyxl


def _build_offset_taxonomy_xlsx() -> bytes:
    """T02: Topic Pillar header on row 4, Keywords header on row 1."""
    wb = openpyxl.Workbook()
    ws_tp = wb.active
    ws_tp.title = "Topic Pillar"
    ws_tp.append(["TÀI LIỆU TAXONOMY FINZ"])
    ws_tp.append(["Phiên bản: 2026"])
    ws_tp.append([])
    # Row 4 is the actual header row!
    ws_tp.append(["Pillar", "Mã Topic Pillar", "Tên Topic Pillar", "Loại topic", "Trục chia", "Chủ đề chính"])
    ws_tp.append(["Nhân sự & Thuế", "P08", "Bảo hiểm xã hội doanh nghiệp", "Core Pillar", "Theo nghĩa vụ DN", "Đóng BHXH bắt buộc"])
    ws_tp.append(["Tài chính DN", "Z42", "Quản trị dòng tiền SME", "Cluster", "Theo chu kỳ", "Dự báo dòng tiền"])

    ws_kw = wb.create_sheet(title="Keywords")
    # Row 1 is header row!
    ws_kw.append(["Mã Topic Pillar", "Mã nội dung", "Tiêu đề", "Keyword chính", "Keyword phụ"])
    ws_kw.append(["P08", "P08-01", "Mức đóng BHXH bắt buộc", "mức đóng bhxh bắt buộc", "cách tính bhxh, công cụ tính bhxh, mẫu bảng tính bhxh"])
    ws_kw.append(["Z42", "Z42-01", "Lập kế hoạch dòng tiền", "lập kế hoạch dòng tiền", "mẫu file excel dòng tiền, dự báo dòng tiền doanh nghiệp"])
    ws_kw.append(["X99", "X99-01", "Bài lạc topic", "từ khóa lạc topic", "kw phụ lạc"])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_t01_multi_project_isolation_and_persistence(client):
    tc, _ = client
    r1 = tc.post("/api/v1/projects", json={"code": "P01", "name": "Lương & Thuế TNCN", "primary_keyword": "cách tính lương net"})
    r2 = tc.post("/api/v1/projects", json={"code": "P08", "name": "Bảo hiểm xã hội", "primary_keyword": "mức đóng bhxh bắt buộc"})
    r3 = tc.post("/api/v1/projects", json={"code": "Z42", "name": "Dòng tiền SME", "primary_keyword": "quản trị dòng tiền"})
    assert r1.status_code == 201 and r2.status_code == 201 and r3.status_code == 201

    listing = tc.get("/api/v1/projects").json()["projects"]
    codes = {p["code"] for p in listing}
    assert {"P01", "P08", "Z42"}.issubset(codes)

    p8_id = r2.json()["project"]["id"]
    detail = tc.get(f"/api/v1/projects/{p8_id}").json()["project"]
    assert detail["code"] == "P08"
    assert detail["primary_keyword_original"] == "mức đóng bhxh bắt buộc"


def test_t02_t03_t04_excel_header_row4_preview_no_overwrite_no_guess(client):
    tc, _ = client
    proj = tc.post(
        "/api/v1/projects",
        json={
            "code": "P08",
            "name": "Dự án BHXH",
            "primary_keyword": "keyword cũ chưa xác nhận",
            "business_goal": "Mục tiêu cũ",
        },
    ).json()["project"]
    pid = proj["id"]

    xlsx_bytes = _build_offset_taxonomy_xlsx()
    prev = tc.post(
        f"/api/v1/projects/{pid}/topic-source/preview",
        files={"file": ("taxonomy.xlsx", xlsx_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert prev.status_code == 200
    body = prev.json()
    # T02: Row 4 for Topic Pillar, Row 1 for Keywords
    assert body["topic_pillar_header_row"] == 4
    assert body["keywords_header_row"] == 1
    assert len(body["topic_pillars"]) == 2
    assert any(w["code"] == "ORPHAN_KEYWORD_TOPIC" for w in body["warnings"])
    # T03: Preview MUST NOT overwrite saved project!
    assert body["saved_to_project"] is False
    after_preview = tc.get(f"/api/v1/projects/{pid}").json()["project"]
    assert after_preview["primary_keyword_original"] == "keyword cũ chưa xác nhận"

    # T04: Confirming without business_goal/audience keeps them empty (never guessed)
    conf = tc.post(
        f"/api/v1/projects/{pid}/topic-source/confirm",
        json={
            "upload_id": body["upload_id"],
            "selected_topic_pillar_code": "P08",
            "selected_content_code": "P08-01",
            "pillar_name": "Nhân sự & Thuế",
            "topic_pillar_name": "Bảo hiểm xã hội doanh nghiệp",
            "topic_type": "Core Pillar",
            "split_axis": "Theo nghĩa vụ DN",
            "main_topic": "Đóng BHXH bắt buộc",
            "content_title": "Mức đóng BHXH bắt buộc",
            "primary_keyword": "mức đóng bhxh bắt buộc",
            "secondary_keywords": ["cách tính bhxh", "công cụ tính bhxh"],
            "business_goal": "",
            "target_audience": "",
        },
    )
    assert conf.status_code == 200
    updated = conf.json()["project"]
    assert updated["business_goal"] == ""
    assert updated["target_audience"] == ""
    assert updated["version"] >= 2


def test_t05_preserve_original_primary_keyword_and_queue_approval(client):
    tc, _ = client
    pid = tc.post(
        "/api/v1/projects",
        json={"code": "Z42", "name": "Dòng tiền", "primary_keyword": "quản trị dòng tiền"},
    ).json()["project"]["id"]

    upd = tc.put(
        f"/api/v1/projects/{pid}",
        json={"primary_keyword": "phần mềm quản lý dòng tiền", "change_reason": "Thử đổi keyword chính"},
    )
    assert upd.status_code == 200
    body = upd.json()
    assert body["primary_change_pending_approval"] is True
    assert body["project"]["primary_keyword_original"] == "quản trị dòng tiền"
    # Current keyword does not silently replace original until approved
    assert body["project"]["primary_keyword_current"] == "quản trị dòng tiền"

    approvals = tc.get(f"/api/v1/projects/{pid}/approvals").json()["approvals"]
    assert len(approvals) == 1
    assert approvals[0]["approval_type"] == "PRIMARY_KEYWORD_CHANGE"
    assert approvals[0]["status"] == "PENDING"
