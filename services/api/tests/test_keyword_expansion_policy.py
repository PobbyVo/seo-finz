from app.domain.keyword_expansion import enabled
from types import SimpleNamespace


def test_policy_is_explicit_and_preserves_legacy():
    assert not enabled(SimpleNamespace(provenance_json="{}"))
    assert enabled(
        SimpleNamespace(provenance_json='{"exclude_keywords_without_volume":true}')
    )


def test_research_candidates_are_not_articles_or_fake_metrics(client):
    tc, _ = client
    pid = tc.post(
        "/api/v1/projects",
        json={
            "code": "P01",
            "name": "Lương",
            "topic_pillar_code": "P01",
            "primary_keyword": "cách deal lương",
        },
    ).json()["project"]["id"]
    response = tc.post(f"/api/v1/projects/{pid}/keyword-expansion")
    assert response.status_code == 200, response.text
    rows = response.json()
    assert len(rows["candidates"]) == 8
    assert all(r["volume"] is None and r["kd"] is None for r in rows["candidates"])
    assert all(r["status"] == "WAITING_SEMRUSH" for r in rows["candidates"])
    assert rows["source_keywords"][0]["included"] is False
    assert tc.get(f"/api/v1/projects/{pid}/opportunities").json()["mappings"] == []
    assert (
        len(tc.post(f"/api/v1/projects/{pid}/keyword-expansion").json()["candidates"])
        == 8
    )


def test_new_keyword_enters_plan_only_after_semrush_and_human_decision(client):
    tc, _ = client
    pid = tc.post(
        "/api/v1/projects",
        json={
            "code": "P01",
            "name": "Lương",
            "topic_pillar_code": "P01",
            "primary_keyword": "gross net",
        },
    ).json()["project"]["id"]
    plan = tc.post(f"/api/v1/projects/{pid}/keyword-expansion").json()
    candidate = next(r for r in plan["candidates"] if r["keyword"] == "lương thử việc")
    assert candidate["status"] == "WAITING_SEMRUSH"
    # Số liệu tổng hợp chỉ là fixture kiểm thử, không dùng trong output người dùng.
    raw = "Keyword,Volume,Keyword Difficulty\nlương thử việc,100,20\n".encode()
    preview = tc.post(
        f"/api/v1/projects/{pid}/imports/preview",
        data={"report_type": "KEYWORD_OVERVIEW", "locale": "en-US"},
        files={"file": ("test-only.csv", raw, "text/csv")},
    ).json()
    imported = tc.post(
        f"/api/v1/projects/{pid}/imports/confirm",
        json={
            "upload_id": preview["upload_id"],
            "report_type": "KEYWORD_OVERVIEW",
            "market": "VN",
            "locale": "en-US",
            "column_mapping": preview["suggested_mapping"],
        },
    )
    assert imported.status_code == 200, imported.text
    approval = next(
        a
        for a in tc.get(f"/api/v1/projects/{pid}/approvals").json()["approvals"]
        if a["target_ref"] == candidate["id"]
    )
    assert approval["status"] == "PENDING"
    refreshed = tc.get(f"/api/v1/projects/{pid}/keyword-expansion").json()["candidates"]
    verified = next(c for c in refreshed if c["id"] == candidate["id"])
    assert verified["volume"] == 100 and verified["kd"] == 20
    assert tc.get(f"/api/v1/projects/{pid}/opportunities").json()["mappings"] == []
    assert (
        tc.post(
            f"/api/v1/projects/{pid}/approvals/{approval['id']}",
            json={"decision": "APPROVED"},
        ).status_code
        == 200
    )
    promoted = tc.post(
        f"/api/v1/projects/{pid}/demand-map/candidates/{candidate['id']}/promote",
        json={"action": "PROMOTE"},
    )
    assert promoted.status_code == 200, promoted.text
    assert tc.post(f"/api/v1/projects/{pid}/mapping/preview").status_code == 200
    mappings = tc.get(f"/api/v1/projects/{pid}/opportunities").json()["mappings"]
    assert len(mappings) == 1
    assert mappings[0]["primary_keyword"] == "lương thử việc"
    assert mappings[0]["is_approved"] is False

    tc.put("/api/v1/settings/ai", json={"provider": "mock", "set_active": True})
    analysis = tc.post(f"/api/v1/projects/{pid}/serp-analysis")
    assert analysis.status_code == 200, analysis.text
    assert any(
        a["keyword"] == "lương thử việc" and a["decision"] == "WAITING_DATA"
        for a in analysis.json()["analyses"]
    )
