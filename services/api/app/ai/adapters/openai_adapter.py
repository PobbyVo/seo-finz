from __future__ import annotations

import time
from typing import Any

import httpx

from app.ai.adapters.base import (
    AIProviderAdapter,
    ProviderConfig,
    StructuredGenerationResult,
    TestConnectionResult,
    extract_json_object,
)
from app.ai.errors import build_error, normalize_http_error

DEFAULT_OPENAI_MODEL = "gpt-4.1-mini"


class OpenAIAdapter(AIProviderAdapter):
    """Official OpenAI Platform API adapter (`/v1/chat/completions`)."""

    provider_name = "openai"

    def __init__(self, http_client: httpx.Client | None = None) -> None:
        self._http_client = http_client

    def _client(self, timeout: float) -> httpx.Client:
        return self._http_client if self._http_client is not None else httpx.Client(timeout=timeout)

    def _request(
        self,
        config: ProviderConfig,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 12000,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None, int]:
        started = time.perf_counter()
        if not config.api_key:
            return None, build_error("AI_NOT_CONFIGURED").to_dict(), 0

        model_id = config.model_id.strip() or DEFAULT_OPENAI_MODEL
        url = f"{config.endpoint_url.rstrip('/')}/chat/completions"
        payload: dict[str, Any] = {
            "model": model_id,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "max_completion_tokens": max_tokens,
        }
        # Reasoning models (o1/o3/o4) may reject custom temperature
        if not model_id.startswith(("o1", "o3", "o4")):
            payload["temperature"] = 0.2

        close_after = self._http_client is None
        client = self._client(config.timeout_seconds)
        try:
            resp = client.post(
                url,
                headers={
                    "Authorization": f"Bearer {config.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        except httpx.TimeoutException:
            elapsed = int((time.perf_counter() - started) * 1000)
            return None, build_error("CONNECTION_TIMEOUT", detail=f"OpenAI timeout sau {config.timeout_seconds}s").to_dict(), elapsed
        except httpx.RequestError as exc:
            elapsed = int((time.perf_counter() - started) * 1000)
            return None, build_error("PROVIDER_UNAVAILABLE", detail=exc.__class__.__name__).to_dict(), elapsed
        finally:
            if close_after:
                client.close()

        elapsed = int((time.perf_counter() - started) * 1000)
        if resp.status_code != 200:
            return None, normalize_http_error(resp.status_code, resp.text).to_dict(), elapsed

        try:
            body = resp.json()
            choices = body.get("choices") or []
            content = (choices[0].get("message") or {}).get("content") if choices else None
            if not content:
                return None, build_error("INVALID_PROVIDER_RESPONSE", detail="OpenAI trả về content rỗng.").to_dict(), elapsed
            return extract_json_object(str(content)), None, elapsed
        except Exception as exc:
            return None, build_error("INVALID_PROVIDER_RESPONSE", detail=str(exc)).to_dict(), elapsed

    def test_connection(self, config: ProviderConfig) -> TestConnectionResult:
        model_id = config.model_id.strip() or DEFAULT_OPENAI_MODEL
        data, err, latency_ms = self._request(
            config,
            system_prompt="You are a health check endpoint. Reply only with valid JSON.",
            user_prompt='Return {"ok": true, "pong": "finz"}',
            max_tokens=48,
        )
        if data is not None and err is None:
            return TestConnectionResult(
                ok=True,
                provider=self.provider_name,
                requested_model=model_id,
                actual_model=model_id,
                latency_ms=latency_ms,
                status="CONNECTED",
                message=f"Kết nối OpenAI thành công với model {model_id} ({latency_ms} ms).",
            )
        return TestConnectionResult(
            ok=False,
            provider=self.provider_name,
            requested_model=model_id,
            actual_model=model_id,
            latency_ms=latency_ms,
            status="ERROR",
            message=(err or {}).get("reason", "Không thể kết nối OpenAI."),
            error=err,
        )

    def generate_structured_output(
        self,
        config: ProviderConfig,
        system_prompt: str,
        user_prompt: str,
        context: dict[str, Any] | None = None,
    ) -> StructuredGenerationResult:
        model_id = config.model_id.strip() or DEFAULT_OPENAI_MODEL
        data, err, latency_ms = self._request(config, system_prompt, user_prompt)
        return StructuredGenerationResult(
            ok=data is not None and err is None,
            provider=self.provider_name,
            requested_model=model_id,
            actual_model=model_id,
            latency_ms=latency_ms,
            data=data or {},
            error=err,
        )
