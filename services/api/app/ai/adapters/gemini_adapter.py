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

# Ordered newest/flagship -> fast latest -> stable fallback
DEFAULT_GEMINI_FALLBACK_CHAIN: list[str] = [
    "gemini-4-carbon",
    "gemini-4-argon",
    "gemini-4-neon",
    "gemini-4-hydrogen",
    "gemini-3.8-flash",
    "gemini-3.5-flash",
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

# Filter out non-text / image / audio / specialized models returned by /v1beta/models
_EXCLUDED_MODEL_TOKENS = (
    "embedding",
    "imagen",
    "image",
    "veo",
    "tts",
    "audio",
    "speech",
    "transcribe",
    "live",
    "aqa",
    "bison",
    "gecko",
    "robotics",
    "computer-use",
    "deep-research",
    "customtools",
    "banana",
    "omni",
    "vision",
    "translate",
    "learnlm",
    "gemma",
)

MAX_CHAIN_LENGTH = 12


def _is_usable_text_gemini_model(model_id: str) -> bool:
    low = model_id.lower().strip()
    if not low.startswith("gemini-"):
        return False
    if any(tok in low for tok in _EXCLUDED_MODEL_TOKENS):
        return False
    # Exclude generic rolling aliases when versioned models are present
    if low in {"gemini-pro-latest", "gemini-flash-latest", "gemini-flash-lite-latest"}:
        return False
    return True


def _model_rank_key(model_id: str) -> tuple[float, int, int, str]:
    """Sort Gemini text models newest-first: higher version -> carbon/argon/pro > neon/hydrogen/flash > flash-lite -> stable."""
    low = model_id.lower()
    m = re.search(r"gemini-(\d+(?:\.\d+)?)", low)
    version = float(m.group(1)) if m else 0.0

    tier = 2
    if "carbon" in low or "ultra" in low:
        tier = 6
    elif "argon" in low or "pro" in low:
        tier = 5
    elif "neon" in low:
        tier = 4
    elif "hydrogen" in low:
        tier = 3
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
    """Construct concise, deduplicated newest -> fallback Gemini text-model chain."""
    chain: list[str] = []
    seen: set[str] = set()

    def add(m: str, *, allow_custom: bool = False) -> None:
        cleaned = m.strip()
        if cleaned.startswith("models/"):
            cleaned = cleaned[len("models/") :]
        if not cleaned or cleaned == "auto" or cleaned in seen:
            return
        if not allow_custom and not _is_usable_text_gemini_model(cleaned):
            return
        seen.add(cleaned)
        chain.append(cleaned)

    # If user picked a specific model and auto_latest is False, start with that model first
    if configured_model and configured_model != "auto" and not auto_latest:
        add(configured_model, allow_custom=True)

    # When Google's /v1beta/models returned live models, prioritize those discovered models!
    if discovered:
        for m in sorted(discovered, key=_model_rank_key, reverse=True):
            add(m)
    else:
        if configured_model and configured_model != "auto":
            add(configured_model, allow_custom=True)
        if existing_chain:
            for m in existing_chain:
                add(m)

    for m in DEFAULT_GEMINI_FALLBACK_CHAIN:
        if not discovered or m in discovered:
            add(m)

    # Giữ đường lui tới model ổn định, kể cả cache có nhiều preview.
    stable = [m for m in ("gemini-2.5-flash", "gemini-2.5-flash-lite") if m in chain]
    head = [m for m in chain if m not in stable]
    return head[:MAX_CHAIN_LENGTH-len(stable)] + stable


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

    def discover_latest_models(
        self,
        api_key: str,
        endpoint_url: str,
        timeout: float = 8.0,
        client: httpx.Client | None = None,
    ) -> list[str]:
        """Fetch generateContent-capable text Gemini models from Google API and sort newest-first."""
        url = f"{endpoint_url.rstrip('/')}/models"
        active_client = client or self._http_client
        close_after = active_client is None
        if active_client is None:
            active_client = httpx.Client(timeout=timeout)
        try:
            resp = active_client.get(url, headers={"x-goog-api-key": api_key}, timeout=timeout)
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
                if not _is_usable_text_gemini_model(short):
                    continue
                found.append(short)
            return sorted(set(found), key=_model_rank_key, reverse=True)
        except Exception:
            return []
        finally:
            if close_after:
                active_client.close()

    def _call_single_model(
        self,
        *,
        client: httpx.Client,
        api_key: str,
        endpoint_url: str,
        model_id: str,
        system_prompt: str,
        user_prompt: str,
        timeout: float,
        max_output_tokens: int = 4096,
        require_json_mime: bool = True,
    ) -> tuple[str | None, StandardizedError | None]:
        url = f"{endpoint_url.rstrip('/')}/models/{model_id}:generateContent"
        gen_cfg: dict[str, Any] = {
            "temperature": 0.2,
            "maxOutputTokens": max_output_tokens,
        }
        if require_json_mime:
            gen_cfg["responseMimeType"] = "application/json"

        body: dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": gen_cfg,
        }
        if system_prompt:
            body["systemInstruction"] = {"parts": [{"text": system_prompt}]}

        try:
            resp = client.post(
                url,
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": api_key,
                },
                json=body,
                timeout=timeout,
            )
        except httpx.TimeoutException:
            return None, build_error("CONNECTION_TIMEOUT", detail=f"Model {model_id} quá thời gian chờ ({timeout:.0f}s)")
        except httpx.RequestError as exc:
            return None, build_error("PROVIDER_UNAVAILABLE", detail=f"Lỗi kết nối tới Gemini ({exc.__class__.__name__})")

        if resp.status_code != 200:
            return None, normalize_http_error(resp.status_code, resp.text)

        try:
            payload = resp.json()
            candidates = payload.get("candidates") or []
            if not candidates:
                return None, build_error("INVALID_PROVIDER_RESPONSE", detail="Gemini không trả về candidates nào.")
            parts = (candidates[0].get("content") or {}).get("parts") or []
            # Skip internal thought-only parts if present, collect text output parts
            text_chunks = [
                str(p.get("text", ""))
                for p in parts
                if "text" in p and not p.get("thought", False)
            ]
            if not text_chunks:
                text_chunks = [str(p.get("text", "")) for p in parts if "text" in p]
            combined = "".join(text_chunks).strip()
            if not combined:
                return None, build_error("INVALID_PROVIDER_RESPONSE", detail=f"Model {model_id} trả về nội dung rỗng.")
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
        is_health_ping: bool = False,
    ) -> tuple[bool, str, dict[str, Any], list[str], list[ModelFallbackEvent], dict[str, int], StandardizedError | None, int]:
        """
        Core Gemini execution engine:
        - Picks newest text model first (when auto_latest=True).
        - Tracks consecutive failures per model.
        - After `downgrade_threshold` (default 3) errors on a model, automatically downgrades
          to the next model in `fallback_chain` and continues seamlessly.
        """
        started = time.perf_counter()
        if not config.api_key:
            err = build_error("AI_NOT_CONFIGURED")
            return False, config.model_id or DEFAULT_GEMINI_FALLBACK_CHAIN[0], {}, [], [], dict(config.failure_counts), err, 0

        close_after = self._http_client is None
        per_call_timeout = 8.0 if is_health_ping else max(25.0, float(config.timeout_seconds or 45.0))
        # Guard against indefinite hangs during multi-model ping (disabled for injected mock clients)
        total_budget_s = 45.0 if (is_health_ping and self._http_client is None) else 480.0
        client = self._http_client if self._http_client is not None else httpx.Client(timeout=per_call_timeout)

        try:
            discovered: list[str] = []
            if discover_first and config.auto_latest:
                discovered = self.discover_latest_models(
                    config.api_key,
                    config.endpoint_url,
                    timeout=6.0,
                    client=client,
                )

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

            start_idx = 0
            if not discover_first and config.model_id and config.model_id != "auto" and config.model_id in chain:
                start_idx = chain.index(config.model_id)

            idx = start_idx
            while idx < len(chain):
                current_model = chain[idx]
                while True:
                    if (time.perf_counter() - started) > total_budget_s:
                        elapsed_ms = int((time.perf_counter() - started) * 1000)
                        timeout_err = last_error or build_error(
                            "CONNECTION_TIMEOUT",
                            detail=f"Kiểm tra kết nối vượt quá {int(total_budget_s)}s khi thử tới model {current_model}.",
                        )
                        return False, current_model, {}, discovered, fallback_events, failure_counts, timeout_err, elapsed_ms

                    if failure_counts.get(current_model, 0) >= threshold and idx + 1 < len(chain):
                        next_model = chain[idx + 1]
                        fallback_events.append(ModelFallbackEvent(from_model=current_model,to_model=next_model,failures_on_model=failure_counts[current_model],error_code="PREVIOUS_FAILURES",reason=f"{current_model} đã lỗi đủ {threshold} lần; chuyển sang {next_model}."))
                        idx += 1
                        break

                    raw_text, call_err = self._call_single_model(
                        client=client,
                        api_key=config.api_key,
                        endpoint_url=config.endpoint_url,
                        model_id=current_model,
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        timeout=min(per_call_timeout, max(1.0, total_budget_s - (time.perf_counter() - started))),
                        max_output_tokens=max_output_tokens,
                        require_json_mime=not is_health_ping,
                    )

                    if call_err is None and raw_text is not None:
                        if is_health_ping:
                            try:
                                parsed = extract_json_object(raw_text)
                            except Exception:
                                parsed = {"ok": True, "reply": raw_text[:120]}
                            failure_counts[current_model] = 0
                            elapsed_ms = int((time.perf_counter() - started) * 1000)
                            return True, current_model, parsed, discovered, fallback_events, failure_counts, None, elapsed_ms
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
                                        f"({call_err.code}: {call_err.reason}) → tự động hạ xuống {next_model}."
                                    ),
                                )
                            )
                            idx += 1
                            break
                        else:
                            elapsed_ms = int((time.perf_counter() - started) * 1000)
                            return False, current_model, {}, discovered, fallback_events, failure_counts, call_err, elapsed_ms

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
        finally:
            if close_after:
                client.close()

    def test_connection(self, config: ProviderConfig) -> TestConnectionResult:
        requested = config.model_id or "auto"
        ok, actual_model, _data, discovered, events, counts, err, latency_ms = self._execute_with_auto_downgrade(
            config=config,
            system_prompt="Reply briefly with OK.",
            user_prompt="Reply OK",
            discover_first=True,
            max_output_tokens=512,
            is_health_ping=True,
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
            max_output_tokens=12000,
            is_health_ping=False,
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
