from __future__ import annotations

import json
import sqlite3

import httpx

from app.ai.adapters.claude_adapter import ClaudeAdapter
from app.ai.adapters.gemini_adapter import GeminiAdapter
from app.ai.adapters.openai_adapter import OpenAIAdapter
from app.ai.gateway import gateway


def test_t06_t08_t09_ai_settings_security_no_plaintext_key(client):
    tc, db_file = client
    # T09: GET settings makes zero live API calls and returns all providers
    initial = tc.get("/api/v1/settings/ai")
    assert initial.status_code == 200
    provs = {p["provider"]: p for p in initial.json()["providers"]}
    assert {"openai", "gemini", "claude", "mock"}.issubset(provs.keys())
    assert provs["gemini"]["auto_latest"] is True
    assert provs["gemini"]["downgrade_threshold"] == 3

    secret_value = "AIzaSySUPER_SECRET_KEY_NEVER_LEAK_98765"
    put_res = tc.put(
        "/api/v1/settings/ai",
        json={
            "provider": "gemini",
            "set_active": True,
            "api_key": secret_value,
            "model_id": "auto",
            "auto_latest": True,
            "downgrade_threshold": 3,
        },
    )
    assert put_res.status_code == 200
    # T08: API response NEVER returns raw key!
    assert secret_value not in put_res.text
    assert put_res.json()["provider"]["key_hint"] == "****8765"

    get_res = tc.get("/api/v1/settings/ai")
    assert secret_value not in get_res.text

    # T08: Inspect raw SQLite file bytes & rows -> ZERO plaintext key!
    conn = sqlite3.connect(db_file)
    all_rows = conn.execute("SELECT * FROM ai_provider_settings").fetchall()
    conn.close()
    assert secret_value not in str(all_rows)
    assert secret_value.encode("utf-8") not in db_file.read_bytes()


def test_t10_ai_not_configured_returns_cta(client):
    tc, _ = client
    pid = tc.post("/api/v1/projects", json={"code": "P09", "name": "Test", "primary_keyword": "seo local"}).json()["project"]["id"]
    res = tc.post(f"/api/v1/projects/{pid}/analyze-topic")
    assert res.status_code == 400
    detail = res.json()["detail"]
    assert detail["code"] == "AI_NOT_CONFIGURED"
    assert detail["cta_href"] == "/settings/ai"


def test_t07_openai_and_claude_mocked_errors_401_403_404_429_timeout(client):
    tc, _ = client

    def make_transport(status_code: int | None, body: dict | None = None, raise_timeout: bool = False):
        def handler(request: httpx.Request) -> httpx.Response:
            if raise_timeout:
                raise httpx.ReadTimeout("timeout", request=request)
            return httpx.Response(status_code or 200, json=body or {})
        return httpx.MockTransport(handler)

    cases = [
        (401, "API_KEY_INVALID"),
        (403, "PERMISSION_DENIED"),
        (404, "MODEL_NOT_FOUND"),
        (429, "RATE_LIMITED"),
        (None, "CONNECTION_TIMEOUT"),
    ]
    for code, expected_err in cases:
        gateway.adapters["openai"] = OpenAIAdapter(
            http_client=httpx.Client(transport=make_transport(code, {"error": {"message": "fail"}}, raise_timeout=(code is None)))
        )
        res = tc.post(
            "/api/v1/settings/ai/test",
            json={"provider": "openai", "api_key": "sk-test-1234567890", "model_id": "gpt-4.1-mini"},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["ok"] is False
        assert body["error"]["code"] == expected_err

    # Claude native schema success test (`content[0].text`, NOT OpenAI `choices`)
    gateway.adapters["claude"] = ClaudeAdapter(
        http_client=httpx.Client(
            transport=make_transport(200, {"content": [{"type": "text", "text": '{"ok": true, "pong": "finz"}'}]})
        )
    )
    ok_claude = tc.post(
        "/api/v1/settings/ai/test",
        json={"provider": "claude", "api_key": "sk-ant-test-123456", "model_id": "claude-sonnet-4-5"},
    )
    assert ok_claude.status_code == 200
    assert ok_claude.json()["ok"] is True
    assert ok_claude.json()["status"] == "CONNECTED"


def test_gemini_auto_latest_and_downgrade_after_3_errors(client):
    """
    CORE USER REQUIREMENT:
    - Gemini automatically selects the newest available model (auto-latest).
    - After 3 consecutive failures on that model, it automatically downgrades to the next model in chain!
    """
    tc, _ = client
    call_log: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        # Live discovery endpoint returns newest models including a bleeding-edge model
        if path.endswith("/models") and request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "models": [
                        {"name": "models/gemini-4-argon", "supportedGenerationMethods": ["generateContent"]},
                        {"name": "models/gemini-3.8-flash", "supportedGenerationMethods": ["generateContent"]},
                        {"name": "models/gemini-2.5-flash", "supportedGenerationMethods": ["generateContent"]},
                        {"name": "models/gemini-embedding-2", "supportedGenerationMethods": ["embedContent"]},
                    ]
                },
            )
        # Extract model ID from /v1beta/models/{model}:generateContent
        model_part = path.split("/models/")[1].split(":")[0]
        call_log.append(model_part)

        # Simulate gemini-4-argon failing 3 times (503/429), then gemini-3.8-flash succeeding!
        if model_part == "gemini-4-argon":
            return httpx.Response(503, json={"error": {"message": "overloaded"}})
        if model_part == "gemini-3.8-flash":
            return httpx.Response(
                200,
                json={
                    "candidates": [
                        {"content": {"parts": [{"text": '{"ok": true, "pong": "finz"}'}]}}
                    ]
                },
            )
        return httpx.Response(404, json={"error": {"message": "not found"}})

    gateway.adapters["gemini"] = GeminiAdapter(http_client=httpx.Client(transport=httpx.MockTransport(handler)))

    tc.put(
        "/api/v1/settings/ai",
        json={
            "provider": "gemini",
            "set_active": True,
            "api_key": "AIzaSyTestFallback1234567890",
            "model_id": "auto",
            "auto_latest": True,
            "downgrade_threshold": 3,
        },
    )

    res = tc.post("/api/v1/settings/ai/test", json={"provider": "gemini"})
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    # Tried gemini-4-argon exactly 3 times, then automatically downgraded to gemini-3.8-flash!
    assert call_log == ["gemini-4-argon", "gemini-4-argon", "gemini-4-argon", "gemini-3.8-flash"]
    assert body["actual_model"] == "gemini-3.8-flash"
    assert len(body["fallback_events"]) == 1
    assert body["fallback_events"][0]["from_model"] == "gemini-4-argon"
    assert body["fallback_events"][0]["to_model"] == "gemini-3.8-flash"
    assert body["fallback_events"][0]["failures_on_model"] == 3

    # Persisted active_model_id is now gemini-3.8-flash
    settings_after = tc.get("/api/v1/settings/ai").json()
    gem = next(p for p in settings_after["providers"] if p["provider"] == "gemini")
    assert gem["active_model_id"] == "gemini-3.8-flash"
    assert "gemini-4-argon" in (gem["last_downgrade_reason"] or "")

    # Reset back to newest works cleanly
    reset = tc.post("/api/v1/settings/ai/gemini/reset-latest")
    assert reset.status_code == 200
    assert reset.json()["provider"]["active_model_id"] == "gemini-4-argon"
