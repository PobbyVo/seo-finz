from app.domain.brief_writer import mock_brief, business_quality, WriterOutput


def test_briefs_have_topic_outline_and_no_fabricated_rates():
    first = mock_brief(
        {
            "primary_keyword": "lương gross net là gì",
            "secondary_keywords": ["cách đọc phiếu lương"],
            "other_mappings": [],
        }
    )
    second = mock_brief(
        {
            "primary_keyword": "cách deal lương",
            "secondary_keywords": ["sai lầm khi deal lương"],
            "other_mappings": [],
        }
    )
    assert first["outline"] != second["outline"]
    for kw, secondary, payload in [
        ("lương gross net là gì", ["cách đọc phiếu lương"], first),
        ("cách deal lương", ["sai lầm khi deal lương"], second),
    ]:
        WriterOutput.model_validate(payload)
        assert not business_quality(
            payload,
            primary_keyword=kw,
            secondary_keywords=secondary,
            allowed_urls=set(),
        )
        assert payload["legal_sources"]
        assert len(payload["meta_description"]) <= 160


def test_f7_rejects_broken_handoff():
    p = mock_brief({"primary_keyword": "thuế lương", "secondary_keywords": []})
    p.update(
        title_variants=["x" * 61, "Sai"],
        meta_description="x" * 161,
        internal_links=[{"target_url": "/invented", "anchor": "x", "reason": "x"}],
        legal_sources=[],
    )
    errors = business_quality(
        p,
        primary_keyword="thuế lương",
        secondary_keywords=["chưa có"],
        allowed_urls=set(),
    )
    assert all(
        any(code in e for e in errors)
        for code in ["F7-TITLE", "F7-META", "F7-KEY-PHU", "F7-LINK", "F7-NGUON"]
    )


def test_invalid_writer_json_retries_once_then_labels_fallback(client, monkeypatch):
    from types import SimpleNamespace
    from app.ai.gateway import gateway

    tc, _ = client
    pid = tc.post(
        "/api/v1/projects",
        json={
            "code": "Z99",
            "name": "Kiểm retry",
            "primary_keyword": "cách quản lý tiền",
        },
    ).json()["project"]["id"]
    assert tc.post(f"/api/v1/projects/{pid}/mapping/preview").status_code == 200
    calls = []

    def malformed(*args, **kwargs):
        calls.append(kwargs["role"])
        return SimpleNamespace(data={"bad": "JSON thiếu schema"}), None

    monkeypatch.setattr(gateway, "generate_structured", malformed)
    generated = tc.post(
        f"/api/v1/projects/{pid}/briefs/generate", json={"allow_draft": True}
    )
    assert generated.status_code == 200, generated.text
    assert calls == ["BRIEF_WRITER", "BRIEF_WRITER"]
    brief = generated.json()["briefs"][0]
    assert brief["brief_mode"] == "DRAFT"
    assert brief["status"] == "NEEDS_HUMAN_EDIT"
    assert brief["writing_strategy"]["generation_source"] == "FALLBACK"
    assert brief["writing_strategy"]["quality_errors"]
