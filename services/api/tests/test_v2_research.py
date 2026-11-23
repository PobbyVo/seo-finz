from app.domain.semrush_parser import infer_page_type_from_url
from app.routers.research import create_research_tickets
from app.models import Project, SourceKeyword


def test_article_is_not_calculator():
    assert (
        infer_page_type_from_url(
            "https://example.org/cach-tinh-lai", "Cách tính lãi suất tiết kiệm"
        )
        == "ARTICLE"
    )
    assert (
        infer_page_type_from_url("https://example.org/khoa-hoc/tai-chinh") != "PRODUCT"
    )
    assert infer_page_type_from_url("https://example.org/cong-cu/gross-net") == "TOOL"


def test_p01_tickets_and_offline_serp(client):
    from pathlib import Path

    tc, _ = client
    tc.put("/api/v1/settings/ai", json={"provider": "mock", "set_active": True})
    pid = tc.post(
        "/api/v1/projects",
        json={"code": "P01", "name": "Lương", "topic_pillar_code": "P01"},
    ).json()["project"]["id"]
    raw = (Path(__file__).parent / "fixtures/bo_key_p01_original.tsv").read_bytes()
    p = tc.post(
        f"/api/v1/projects/{pid}/topic-source/preview",
        files={"file": ("p01.tsv", raw, "text/tab-separated-values")},
    ).json()
    r = tc.post(
        f"/api/v1/projects/{pid}/topic-source/confirm",
        json={
            "upload_id": p["upload_id"],
            "source_scope": "PILLAR",
            "selected_topic_pillar_code": "P01",
            "topic_pillar_name": "Lương",
            "primary_keyword": "lương gross net là gì",
            "business_goal": "Khóa học miễn phí",
            "target_audience": "Bạn trẻ đi làm",
        },
    )
    assert r.status_code == 200, r.text
    analyzed = tc.post(f"/api/v1/projects/{pid}/analyze-topic")
    assert analyzed.status_code == 200, analyzed.text
    seeds = {
        keyword
        for group in analyzed.json()["demand_groups"]
        for keyword in group["seed_keywords"]
    }
    assert {"lương gross net là gì", "cách deal lương"}.issubset(seeds)
    tickets = tc.post(f"/api/v1/projects/{pid}/research-tickets")
    assert tickets.status_code == 200, tickets.text
    rows = tickets.json()["tickets"]
    assert len(rows) == 7
    assert len(rows[0]["keywords"]) == 12
    assert {r["report_type"] for r in rows} == {
        "KEYWORD_OVERVIEW",
        "RELATED",
        "QUESTIONS",
        "ORGANIC_RESULTS",
    }
    assert tc.post(f"/api/v1/projects/{pid}/research-tickets").json()["tickets"] == rows
    analysis = tc.post(f"/api/v1/projects/{pid}/serp-analysis")
    assert analysis.status_code == 200, analysis.text
    assert len(analysis.json()["analyses"]) == 2
    assert all(a["decision"] == "WAITING_DATA" for a in analysis.json()["analyses"])
    mapping = tc.post(f"/api/v1/projects/{pid}/mapping/preview")
    assert mapping.status_code == 200, mapping.text
    handoff = tc.get(f"/api/v1/projects/{pid}/research-handoff").json()["rows"]
    assert sum(r["page_type"] == "ARTICLE" for r in handoff) == 2
    assert any(r["page_type"] == "TOOL" for r in handoff)
    assert all(r["priority"] == "P3" for r in handoff)  # no verified primary metrics
    briefs = tc.post(
        f"/api/v1/projects/{pid}/briefs/generate", json={"allow_draft": True}
    )
    assert briefs.status_code == 200, briefs.text
    articles = briefs.json()["briefs"]
    assert len(articles) == 2
    assert len({str(b["outline"]) for b in articles}) == 2
    assert all(b["brief_mode"] == "DRAFT" for b in articles)
    export = tc.post(
        f"/api/v1/projects/{pid}/exports/download", json={"format": "xlsx"}
    )
    assert export.status_code == 200
    import io, openpyxl

    workbook = openpyxl.load_workbook(io.BytesIO(export.content))
    assert workbook.sheetnames == [
        "Keyword Research - Luong",
        "SERP Check - Luong",
        "Keyword Mapping - Luong",
        "Nhat ky - Luong",
        "SEO Content Brief - Luong",
    ]
    ws = workbook.worksheets[-1]
    links = [cell for row in ws for cell in row if cell.value == "Xem Brief"]
    assert len(links) == 2
    for cell in links:
        target = int(cell.hyperlink.target.rsplit("A", 1)[1])
        assert ws.cell(target, 1).value.startswith("BRIEF")
    before = tc.get(f"/api/v1/projects/{pid}/opportunities").json()["mappings"]
    approvals = tc.get(f"/api/v1/projects/{pid}/approvals").json()["approvals"]
    selected = next(a for a in approvals if a["target_ref"] == before[0]["id"])
    approved = tc.post(
        f"/api/v1/projects/{pid}/approvals/{selected['id']}",
        json={"decision": "APPROVED", "decision_note": "Giữ góc bài gốc."},
    )
    assert approved.status_code == 200, approved.text
    reprocessed = tc.post(
        f"/api/v1/projects/{pid}/mapping/{before[0]['id']}/reprocess",
        json={"note": "Kiểm lại góc bài, giữ keyword nguồn."},
    )
    assert reprocessed.status_code == 200, reprocessed.text
    after = tc.get(f"/api/v1/projects/{pid}/opportunities").json()["mappings"]
    assert {m["id"] for m in before} == {m["id"] for m in after}
    current = next(m for m in after if m["id"] == before[0]["id"])
    assert current["is_approved"]
    assert (
        tc.get(f"/api/v1/projects/{pid}/research-handoff").json()["rows"][0][
            "article_code"
        ]
        == handoff[0]["article_code"]
    )
    # Lượt 2 với chính file Semrush mẫu, không thay giá trị Volume/KD.
    for fixture, report, name in [
        (
            "semrush_metrics_real_sample.csv",
            "KEYWORD_OVERVIEW",
            "Overview-Luong-lo1.csv",
        ),
        (
            "semrush_serp_real_sample.csv",
            "ORGANIC_RESULTS",
            "SERP-luong-gross-net-la-gi.csv",
        ),
    ]:
        contents = (Path(__file__).parent / "fixtures" / fixture).read_bytes()
        preview = tc.post(
            f"/api/v1/projects/{pid}/imports/preview",
            data={"report_type": report, "locale": "en-US"},
            files={"file": (name, contents, "text/csv")},
        )
        assert preview.status_code == 200, preview.text
        preview = preview.json()
        if report == "ORGANIC_RESULTS":
            assert preview["target_keyword"] == "lương gross net là gì"
        confirmed = tc.post(
            f"/api/v1/projects/{pid}/imports/confirm",
            json={
                "upload_id": preview["upload_id"],
                "report_type": report,
                "market": "VN",
                "locale": "en-US",
                "column_mapping": preview["suggested_mapping"],
            },
        )
        assert confirmed.status_code == 200, confirmed.text
    analysis = tc.post(f"/api/v1/projects/{pid}/serp-analysis")
    assert analysis.status_code == 200, analysis.text
    assert tc.post(f"/api/v1/projects/{pid}/mapping/preview").status_code == 200
    mapped = tc.get(f"/api/v1/projects/{pid}/opportunities").json()["mappings"]
    gross = next(m for m in mapped if m["primary_keyword"] == "lương gross net là gì")
    assert gross["volume"] == 140 and gross["kd"] == 20
    assert gross["priority"] == "P2"
    assert gross["id"] in {m["id"] for m in before}
    assert all(m["priority"] != "P1" for m in mapped)
    assert (
        tc.post(
            f"/api/v1/projects/{pid}/briefs/generate", json={"allow_draft": True}
        ).status_code
        == 200
    )


def test_new_related_keyword_requires_human_approval(client):
    from pathlib import Path
    from app import db as db_mod
    from app.models import SourceKeyword

    tc, _ = client
    pid = tc.post(
        "/api/v1/projects",
        json={
            "code": "P01",
            "name": "Lương",
            "content_code": "P01.1",
            "primary_keyword": "lương gross net là gì",
        },
    ).json()["project"]["id"]
    raw = (
        Path(__file__).parent / "fixtures/semrush_metrics_real_sample.csv"
    ).read_bytes()
    preview = tc.post(
        f"/api/v1/projects/{pid}/imports/preview",
        data={
            "report_type": "RELATED",
            "locale": "en-US",
            "target_keyword": "lương gross net là gì",
        },
        files={"file": ("Related-gross.csv", raw, "text/csv")},
    ).json()
    assert (
        tc.post(
            f"/api/v1/projects/{pid}/imports/confirm",
            json={
                "upload_id": preview["upload_id"],
                "report_type": "RELATED",
                "market": "VN",
                "locale": "en-US",
                "column_mapping": preview["suggested_mapping"],
            },
        ).status_code
        == 200
    )
    assert tc.post(f"/api/v1/projects/{pid}/mapping/preview").status_code == 200
    approvals = tc.get(f"/api/v1/projects/{pid}/approvals").json()["approvals"]
    proposal = next(
        a
        for a in approvals
        if a["scope"] == "RESEARCH_ONLY" and a["title"].startswith("Phụ (mới)")
    )
    with db_mod.SessionLocal() as session:
        count = session.query(SourceKeyword).filter_by(project_id=pid).count()
    accepted = tc.post(
        f"/api/v1/projects/{pid}/approvals/{proposal['id']}",
        json={
            "decision": "APPROVED",
            "decision_note": "Đã kiểm cùng intent và mã nguồn.",
        },
    )
    assert accepted.status_code == 200, accepted.text
    with db_mod.SessionLocal() as session:
        assert (
            session.query(SourceKeyword).filter_by(project_id=pid).count() == count + 1
        )
        assert (
            session.query(SourceKeyword)
            .filter_by(
                project_id=pid, keyword=proposal["proposed_value"], role="SECONDARY"
            )
            .count()
            == 1
        )
    assert (
        tc.post(
            f"/api/v1/projects/{pid}/approvals/{proposal['id']}",
            json={"decision": "APPROVED"},
        ).status_code
        == 409
    )
