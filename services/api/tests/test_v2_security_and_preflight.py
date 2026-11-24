from types import SimpleNamespace
import pytest
from app.security.ssrf import resolve_public_web_url
from app.domain.research_business import preflight
from app.domain.brief_writer import business_quality, mock_brief


@pytest.mark.parametrize(
    "url",
    [
        "http://example.org",
        "https://u:p@example.org",
        "https://example.org:8080",
        "https://127.0.0.1",
        "https://localhost",
    ],
)
def test_reader_blocks_private_or_unsafe_url(url):
    with pytest.raises(ValueError):
        resolve_public_web_url(url)


def test_reader_rejects_mixed_dns(monkeypatch):
    import socket

    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: [
            (2, 1, 6, "", ("8.8.8.8", 443)),
            (2, 1, 6, "", ("127.0.0.1", 443)),
        ],
    )
    with pytest.raises(ValueError, match="SSRF"):
        resolve_public_web_url("https://example.org")


def test_preflight_preserves_ambiguous_accents_and_flags_two_codes():
    def row(kw, code):
        return SimpleNamespace(keyword=kw, content_code=code, title_match_check="")

    retained, decisions = preflight(
        [row("thuê nhà", "P06.1"), row("thue nha", "P06.2"), row("thuê nhà", "P06.3")],
        "P06",
    )
    assert len(retained) == 2
    assert decisions[0]["code"] == "F2-HAI-MA"
    assert decisions[0]["needs_review"]


def test_f7_outline_similarity_and_unsourced_rate():
    payload = mock_brief({"primary_keyword": "thuế lương", "secondary_keywords": []})
    errors = business_quality(
        payload,
        primary_keyword="thuế lương",
        secondary_keywords=[],
        allowed_urls=set(),
        other_outlines=[payload["outline"]],
    )
    assert any("F7-TRUNG-OUTLINE" in e for e in errors)
    payload["outline"][0]["notes"] = "Khẳng định mức 10%"
    assert any(
        "F7-NGUON" in e
        for e in business_quality(
            payload,
            primary_keyword="thuế lương",
            secondary_keywords=[],
            allowed_urls=set(),
        )
    )


def test_settings_reject_invalid_payload(client):
    tc, _ = client
    r = tc.get("/api/v1/settings/knowledge")
    assert r.status_code == 200
    values = r.json()["thresholds"]
    values["p1_max_kd"] = 101
    assert tc.put("/api/v1/settings/knowledge", json=values).status_code == 422


def test_query_assets_distinguish_answer_examples_and_data():
    from app.domain.research_business import infer_query_asset

    assert infer_query_asset("câu trả lời mẫu mức lương mong muốn") == "ARTICLE"
    assert infer_query_asset("giá vàng hôm nay") == "UNKNOWN"
    assert infer_query_asset("công cụ tính lương gross sang net") == "TOOL"


def test_reader_rechecks_redirect_before_connecting(monkeypatch):
    from app.domain import serp_reader

    original = serp_reader.resolve_public_web_url
    monkeypatch.setattr(
        serp_reader,
        "resolve_public_web_url",
        lambda url: (
            ("example.org", "8.8.8.8", "/")
            if url == "https://example.org"
            else original(url)
        ),
    )
    connections = []

    class Redirect:
        def __init__(self, host, ip):
            connections.append((host, ip))

        def request(self, *args, **kwargs):
            pass

        def getresponse(self):
            return SimpleNamespace(
                status=302, getheader=lambda key: "https://127.0.0.1/"
            )

        def close(self):
            pass

    monkeypatch.setattr(serp_reader, "PinnedHTTPS", Redirect)
    result = serp_reader.read_article("https://example.org")
    assert result["read_status"] == "UNREADABLE"
    assert len(connections) == 1
