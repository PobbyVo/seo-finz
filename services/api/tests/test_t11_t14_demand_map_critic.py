from __future__ import annotations

from app.ai.adapters.base import AIProviderAdapter, ProviderConfig, StructuredGenerationResult, TestConnectionResult
from app.ai.gateway import gateway


class _FakeInvalidRefAdapter(AIProviderAdapter):
    provider_name = "mock"

    def test_connection(self, config: ProviderConfig) -> TestConnectionResult:
        return TestConnectionResult(True, "mock", "m", "m", 1, "CONNECTED", "ok")

    def generate_structured_output(self, config, system_prompt, user_prompt, context=None):
        if (context or {}).get("task") == "ANALYST":
            return StructuredGenerationResult(
                ok=True,
                provider="mock",
                requested_model="m",
                actual_model="m",
                latency_ms=5,
                data={
                    "summary": "test",
                    "demand_groups": [
                        {
                            "name": "Nhóm có nguồn thật",
                            "user_need": "Cần biết quy trình",
                            "coverage_type": "COVERED",
                            "assumed_page_type": "ARTICLE",
                            "assumed_intent": "Informational",
                            "seed_keywords": ["thuế tndn"],
                            "related_keywords": [],
                            "supporting_evidence": ["Từ nguồn SQLite"],
                            "source_refs": ["TOPIC:P12"],
                            "strongest_counterargument": "Chưa có Semrush",
                            "missing_data": ["Volume/KD"],
                            "next_action": "Lấy KEYWORD_OVERVIEW",
                            "recommended_semrush_report": "KEYWORD_OVERVIEW",
                            "status": "RESEARCH_CANDIDATE",
                        },
                        {
                            "name": "Nhóm bịa nguồn",
                            "user_need": "Không rõ nguồn",
                            "coverage_type": "GAP",
                            "assumed_page_type": "ARTICLE",
                            "assumed_intent": "Informational",
                            "seed_keywords": ["bịa nguồn"],
                            "related_keywords": [],
                            "supporting_evidence": ["Nguồn giả"],
                            "source_refs": ["FAKE:999"],
                            "strongest_counterargument": "Nguồn không tồn tại",
                            "missing_data": ["Kiểm tra taxonomy"],
                            "next_action": "Xác minh nguồn",
                            "recommended_semrush_report": "KEYWORD_OVERVIEW",
                            "status": "RESEARCH_CANDIDATE",
                        },
                    ],
                    "proposed_candidates": [
                        {
                            "keyword": "ứng viên nguồn giả",
                            "candidate_type": "EXPANSION",
                            "assumed_page_type": "ARTICLE",
                            "source_refs": ["FAKE:888"],
                            "rationale": "Test",
                        }
                    ],
                },
            )
        return StructuredGenerationResult(
            ok=True,
            provider="mock",
            requested_model="m",
            actual_model="m",
            latency_ms=5,
            data={
                "supporting_evidence": ["OK"],
                "counterarguments": ["Thiếu bằng chứng Semrush"],
                "missing_data": ["Volume/KD"],
                "followup_requests": [{"seed_keyword": "thuế tndn", "report_type": "RELATED", "purpose": "Lấy related"}],
                "next_action": "Lấy Semrush",
                "decision_status": "WAITING_USER",
            },
        )


def test_t11_t12_demand_map_source_ref_validation_and_card_fields(client):
    tc, _ = client
    tc.put("/api/v1/settings/ai", json={"provider": "mock", "set_active": True})
    pid = tc.post(
        "/api/v1/projects",
        json={
            "code": "P12",
            "name": "Thuế TNDN",
            "topic_pillar_code": "P12",
            "topic_pillar_name": "Thuế thu nhập doanh nghiệp",
            "primary_keyword": "thuế tndn",
            "business_goal": "Tư vấn kế toán B2B",
        },
    ).json()["project"]["id"]

    # Inject fake adapter to test T11 (invalid source_ref -> UNCERTAIN)
    gateway.adapters["mock"] = _FakeInvalidRefAdapter()
    res = tc.post(f"/api/v1/projects/{pid}/analyze-topic")
    assert res.status_code == 200
    groups = {g["name"]: g for g in res.json()["demand_groups"]}

    assert groups["Nhóm có nguồn thật"]["status"] == "RESEARCH_CANDIDATE"
    assert groups["Nhóm bịa nguồn"]["status"] == "UNCERTAIN"  # T11!

    # T12: Every card has supporting_evidence, strongest_counterargument, missing_data, next_action
    for g in groups.values():
        assert g["supporting_evidence"]
        assert g["strongest_counterargument"]
        assert g["missing_data"]
        assert g["next_action"]


def test_t14_critic_followups_and_cycle_limit(client):
    tc, _ = client
    tc.put("/api/v1/settings/ai", json={"provider": "mock", "set_active": True})
    pid = tc.post(
        "/api/v1/projects",
        json={"code": "P25", "name": "Hóa đơn điện tử", "primary_keyword": "hóa đơn điện tử b2b", "business_goal": "Chuyển đổi B2B"},
    ).json()["project"]["id"]

    # Round 1 & Round 2 succeed
    c1 = tc.post(f"/api/v1/projects/{pid}/ai/critic", json={"stage": "POST_SEMRUSH"})
    assert c1.status_code == 200
    critique_id = c1.json()["critique"]["id"]
    followups = c1.json()["critique"]["followup_requests"]
    assert len(followups) >= 1

    # Convert Critic followup_requests into Research Requests (T14)
    fu_res = tc.post(
        f"/api/v1/projects/{pid}/research/followups",
        json={"critique_id": critique_id, "selected_indices": [0]},
    )
    assert fu_res.status_code == 201
    assert fu_res.json()["created_requests"][0]["origin"] == "CRITIC_FOLLOWUP"

    c2 = tc.post(f"/api/v1/projects/{pid}/ai/critic", json={"stage": "POST_SEMRUSH"})
    assert c2.status_code == 200

    # Round 3 in same cycle is blocked (max 2 rounds/cycle prevents infinite loop)
    c3 = tc.post(f"/api/v1/projects/{pid}/ai/critic", json={"stage": "POST_SEMRUSH"})
    assert c3.status_code == 409
    assert c3.json()["detail"]["code"] == "CRITIQUE_ROUND_LIMIT_REACHED"

    # Reopen cycle allows a new Critic round cleanly
    reopen = tc.post(f"/api/v1/projects/{pid}/research/reopen-cycle")
    assert reopen.status_code == 200
    assert reopen.json()["research_cycle"] == 2
    c4 = tc.post(f"/api/v1/projects/{pid}/ai/critic", json={"stage": "POST_SEMRUSH"})
    assert c4.status_code == 200
