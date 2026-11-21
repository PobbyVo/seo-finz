from __future__ import annotations

import re
import time
from typing import Any

import httpx

from app.ai.adapters.base import (
    AIProviderAdapter,
    ModelFallbackEvent,
    ProviderConfig,
    StructuredGenerationResult,
    TestConnectionResult,
    extract_json_object,
)
from app.ai.errors import StandardizedError, build_error, normalize_http_error

# Ordered newest/flagship -> high-speed latest -> stable fallback
DEFAULT_GEMINI_FALLBACK_CHAIN: list[str] = [
    "gemini-4-argon",
    "gemini-4-carbon",
    "gemini-3.8-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-pro-preview",
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
]

# Error codes that qualify for automatic 3-failure model downgrade (not invalid API key!)
DOWNGRADABLE_ERROR_CODES: set[str] = {
    "MODEL_NOT_FOUND",
    "PERMISSION_DENIED",
    "QUOTA_EXCEEDED",
    "RATE_LIMITED",
    "CONNECTION_TIMEOUT",
    "PROVIDER_UNAVAILABLE",
    "INVALID_PROVIDER_RESPONSE",
}

_EXCLUDED_MODEL_TOKENS = (
    "embedding",
    "imagen",
    "veo",
    "tts",
    "audio",
    "live",
    "aqa",
    "bison",
    "gecko",
    "robotics",
    "computer-use",
    "deep-research",
)


def _model_rank_key(model_id: str) -> tuple[float, int, int, str]:
    """Sort Gemini text models newest-first: higher version -> pro/argon/carbon > flash > flash-lite -> non-exp."""
    low = model_id.lower()
    m = re.search(r"gemini-(\d+(?:\.\d+)?)", low)
    version = float(m.group(1)) if m else 0.0

    tier = 2
    if "carbon" in low or "ultra" in low:
        tier = 5
    elif "argon" in low or "pro" in low:
        tier = 4
    elif "flash-lite" in low or "lite" in low:
        tier = 1
    elif "flash" in low:
        tier = 3

    stability = 1 if ("exp" not in low and "preview" not in low) else 0
    return (version, tier, stability, low)


def build_effective_chain(
    configured_model: str,
    existing_chain: list[str] | None = None,
    discovered: list[str] | None = None,
    auto_latest: bool = True,
) -> list[str]:
    """Construct deduplicated newest -> fallback Gemini model chain."""
    chain: list[str] = []
    seen: set[str] = set()

    def add(m: str) -> None:
        cleaned = m.strip()
        if cleaned.startswith("models/"):
            cleaned = cleaned[len("models/") :]
        if cleaned and cleaned != "auto" and cleaned not in seen:
            seen.add(cleaned)
            chain.append(cleaned)

    # If user picked a specific model and auto_latest is False, start with that model first
    if configured_model and configured_model != "auto" and not auto_latest:
        add(configured_model)

    # Discovered models from Google API sorted newest-first take top precedence when auto_latest is True
    if discovered:
        for m in sorted(discovered, key=_model_rank_key, reverse=True):
            add(m)

    if configured_model and configured_model != "auto":
        add(configured_model)

    if existing_chain:
        for m in existing_chain:
            add(m)

    for m in DEFAULT_GEMINI_FALLBACK_CHAIN:
        add(m)

    return chain


class GeminiAdapter(AIProviderAdapter):
    """
    Google Gemini REST adapter using native `/v1beta/models/{model}:generateContent`.
    Features:
    - Auto-latest model selection & live discovery via `/v1beta/models`.
    - Automatic downgrade after N consecutive failures (default 3) on the active model.
    - Passes API key via `x-goog-api-key` header (never in URL query string).
    """

    provider_name = "gemini"

    def __init__(self, http_client: httpx.Client | None = None) -> None:
        self._http_client = http_client

    def _client(self, timeout: float) -> httpx.Client:
        if self._http_client is not None:
            return self._http_client
        return httpx.Client(timeout=timeout)

    def discover_latest_models(self, api_key: str, endpoint_url: str, timeout: float = 12.0) -> list[str]:
        """Fetch generateContent-capable Gemini models from Google API and sort newest-first."""
        url = f"{endpoint_url.rstrip('/')}/models"
        close_after = self._http_client is None
        client = self._client(timeout)
        try:
            resp = client.get(url, headers={"x-goog-api-key": api_key})
            if resp.status_code != 200:
                return []
            payload = resp.json()
            raw_models = payload.get("models", [])
            found: list[str] = []
            for item in raw_models:
                name = str(item.get("name", ""))
                methods = item.get("supportedGenerationMethods") or []
                if "generateContent" not in methods:
                    continue
                short = name[len("models/") :] if name.startswith("models/") else name
                low = short.lower()
                if not low.startswith("gemini-"):
                    continue
                if any(tok in low for tok in _EXCLUDED_MODEL_TOKENS):
                    continue
                found.append(short)
            return sorted(set(found), key=_model_rank_key, reverse=True)
        except Exception:
            return []
        finally:
            if close_after:
                client.close()

    def _call_single_model(
        self,
        *,
        api_key: str,
        endpoint_url: str,
        model_id: str,
        system_prompt: str,
        user_prompt: str,
        timeout: float,
        max_output_tokens: int = 4096,
    ) -> tuple[str | None, StandardizedError | None]:
        url = f"{endpoint_url.rstrip('/')}/models/{model_id}:generateContent"
        body: dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": max_output_tokens,
                "responseMimeType": "application/json",
            },
        }
        if system_prompt:
            body["systemInstruction"] = {"parts": [{"text": system_prompt}]}

        close_after = self._http_client is None
        client = self._client(timeout)
        try:
            resp = client.post(
                url,
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": api_key,
                },
                json=body,
            )
        except httpx.TimeoutException:
            return None, build_error("CONNECTION_TIMEOUT", detail=f"Model {model_id} quá thời gian chờ ({timeout}s)")
        except httpx.RequestError as exc:
            return None, build_error("PROVIDER_UNAVAILABLE", detail=f"Lỗi kết nối tới Gemini ({exc.__class__.__name__})")
        finally:
            if close_after:
                client.close()

        if resp.status_code != 200:
            return None, normalize_http_error(resp.status_code, resp.text)

        try:
            payload = resp.json()
            candidates = payload.get("candidates") or []
            if not candidates:
                return None, build_error("INVALID_PROVIDER_RESPONSE", detail="Gemini không trả về candidates nào.")
            parts = (candidates[0].get("content") or {}).get("parts") or []
            text_chunks = [str(p.get("text", "")) for p in parts if "text" in p]
            combined = "".join(text_chunks).strip()
            if not combined:
                return None, build_error("INVALID_PROVIDER_RESPONSE", detail="Gemini trả về nội dung rỗng.")
            return combined, None
        except Exception as exc:
            return None, build_error("INVALID_PROVIDER_RESPONSE", detail=str(exc))

    def _execute_with_auto_downgrade(
        self,
        config: ProviderConfig,
        system_prompt: str,
        user_prompt: str,
        *,
        discover_first: bool = False,
        max_output_tokens: int = 4096,
    ) -> tuple[bool, str, dict[str, Any], list[str], list[ModelFallbackEvent], dict[str, int], StandardizedError | None, int]:
        """
        Core Gemini execution engine:
        - Picks newest model first (when auto_latest=True).
        - Tracks consecutive failures per model.
        - After `downgrade_threshold` (default 3) errors on a model, automatically downgrades
          to the next model in `fallback_chain` and continues seamlessly!
        """
        started = time.perf_counter()
        if not config.api_key:
            err = build_error("AI_NOT_CONFIGURED")
            return False, config.model_id or DEFAULT_GEMINI_FALLBACK_CHAIN[0], {}, [], [], dict(config.failure_counts), err, 0

        discovered: list[str] = []
        if discover_first and config.auto_latest:
            discovered = self.discover_latest_models(config.api_key, config.endpoint_url, timeout=min(config.timeout_seconds, 10.0))

        chain = build_effective_chain(
            configured_model=config.model_id,
            existing_chain=config.fallback_chain,
            discovered=discovered,
            auto_latest=config.auto_latest,
        )
        threshold = max(1, int(config.downgrade_threshold or 3))
        failure_counts = dict(config.failure_counts or {})
        fallback_events: list[ModelFallbackEvent] = []
        last_error: StandardizedError | None = None

        # Start from the configured model if it's in the chain (so already-downgraded models stay active
        # unless user resets to latest or auto_latest discovered a newer working set during test)
        start_idx = 0
        if not discover_first and config.model_id and config.model_id != "auto" and config.model_id in chain:
            start_idx = chain.index(config.model_id)

        idx = start_idx
        while idx < len(chain):
            current_model = chain[idx]
            while True:
                raw_text, call_err = self._call_single_model(
                    api_key=config.api_key,
                    endpoint_url=config.endpoint_url,
                    model_id=current_model,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    timeout=config.timeout_seconds,
                    max_output_tokens=max_output_tokens,
                )

                if call_err is None and raw_text is not None:
                    try:
                        parsed = extract_json_object(raw_text)
                        failure_counts[current_model] = 0
                        elapsed_ms = int((time.perf_counter() - started) * 1000)
                        return True, current_model, parsed, discovered, fallback_events, failure_counts, None, elapsed_ms
                    except Exception as exc:
                        call_err = build_error("INVALID_PROVIDER_RESPONSE", detail=str(exc))

                assert call_err is not None
                last_error = call_err

                # Invalid API key fails globally — do not waste retries or downgrade
                if call_err.code not in DOWNGRADABLE_ERROR_CODES:
                    elapsed_ms = int((time.perf_counter() - started) * 1000)
                    return False, current_model, {}, discovered, fallback_events, failure_counts, call_err, elapsed_ms

                failure_counts[current_model] = failure_counts.get(current_model, 0) + 1

                if failure_counts[current_model] >= threshold:
                    # Reached 3 errors -> automatically downgrade to next model in chain!
                    if idx + 1 < len(chain):
                        next_model = chain[idx + 1]
                        fallback_events.append(
                            ModelFallbackEvent(
                                from_model=current_model,
                                to_model=next_model,
                                failures_on_model=failure_counts[current_model],
                                error_code=call_err.code,
                                reason=(
                                    f"Model {current_model} lỗi {failure_counts[current_model]}/{threshold} lần "
                                    f"({call_err.code}) → tự động hạ xuống {next_model}."
                                ),
                            )
                        )
                        idx += 1
                        break
                    else:
                        elapsed_ms = int((time.perf_counter() - started) * 1000)
                        return False, current_model, {}, discovered, fallback_events, failure_counts, call_err, elapsed_ms

                # Below threshold (e.g., 1/3 or 2/3): retry same model cleanly in this request loop
                # until it succeeds or reaches 3 failures to trigger downgrade.

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return (
            False,
            chain[min(idx, len(chain) - 1)],
            {},
            discovered,
            fallback_events,
            failure_counts,
            last_error or build_error("PROVIDER_UNAVAILABLE"),
            elapsed_ms,
        )

    def test_connection(self, config: ProviderConfig) -> TestConnectionResult:
        requested = config.model_id or "auto"
        ok, actual_model, _data, discovered, events, counts, err, latency_ms = self._execute_with_auto_downgrade(
            config=config,
            system_prompt="You are a health-check responder. Reply ONLY with compact JSON.",
            user_prompt='Return JSON: {"ok": true, "pong": "finz"}',
            discover_first=True,
            max_output_tokens=64,
        )
        if ok:
            msg = f"Kết nối Gemini thành công với model {actual_model} ({latency_ms} ms)."
            if events:
                msg += f" Đã tự động hạ model {len(events)} bậc sau các lần lỗi."
            return TestConnectionResult(
                ok=True,
                provider=self.provider_name,
                requested_model=requested,
                actual_model=actual_model,
                latency_ms=latency_ms,
                status="CONNECTED",
                message=msg,
                discovered_models=discovered,
                fallback_events=events,
                updated_failure_counts=counts,
                error=None,
            )
        return TestConnectionResult(
            ok=False,
            provider=self.provider_name,
            requested_model=requested,
            actual_model=actual_model,
            latency_ms=latency_ms,
            status="ERROR",
            message=err.reason if err else "Không thể kết nối tới Gemini.",
            discovered_models=discovered,
            fallback_events=events,
            updated_failure_counts=counts,
            error=err.to_dict() if err else build_error("PROVIDER_UNAVAILABLE").to_dict(),
        )

    def generate_structured_output(
        self,
        config: ProviderConfig,
        system_prompt: str,
        user_prompt: str,
        context: dict[str, Any] | None = None,
    ) -> StructuredGenerationResult:
        requested = config.model_id or "auto"
        ok, actual_model, data, _discovered, events, counts, err, latency_ms = self._execute_with_auto_downgrade(
            config=config,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            discover_first=False,
            max_output_tokens=4096,
        )
        return StructuredGenerationResult(
            ok=ok,
            provider=self.provider_name,
            requested_model=requested,
            actual_model=actual_model,
            latency_ms=latency_ms,
            data=data if ok else {},
            fallback_events=events,
            updated_failure_counts=counts,
            error=err.to_dict() if err else None,
        )
