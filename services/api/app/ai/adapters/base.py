from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProviderConfig:
    provider: str
    api_key: str | None
    model_id: str
    endpoint_url: str
    timeout_seconds: float = 30.0
    auto_latest: bool = False
    downgrade_threshold: int = 3
    fallback_chain: list[str] = field(default_factory=list)
    failure_counts: dict[str, int] = field(default_factory=dict)


@dataclass
class ModelFallbackEvent:
    from_model: str
    to_model: str
    failures_on_model: int
    error_code: str
    reason: str


@dataclass
class TestConnectionResult:
    __test__ = False
    ok: bool
    provider: str
    requested_model: str
    actual_model: str
    latency_ms: int
    status: str  # CONNECTED | ERROR
    message: str
    discovered_models: list[str] = field(default_factory=list)
    fallback_events: list[ModelFallbackEvent] = field(default_factory=list)
    updated_failure_counts: dict[str, int] = field(default_factory=dict)
    error: dict[str, Any] | None = None


@dataclass
class StructuredGenerationResult:
    ok: bool
    provider: str
    requested_model: str
    actual_model: str
    latency_ms: int
    data: dict[str, Any]
    fallback_events: list[ModelFallbackEvent] = field(default_factory=list)
    updated_failure_counts: dict[str, int] = field(default_factory=dict)
    error: dict[str, Any] | None = None


def extract_json_object(raw_text: str) -> dict[str, Any]:
    """Safely extract a JSON object from LLM text (handling markdown code fences)."""
    text = raw_text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    # Try locating first '{' ... last '}'
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        parsed = json.loads(text[start : end + 1])
        if isinstance(parsed, dict):
            return parsed

    raise ValueError("Phản hồi của model không chứa JSON object hợp lệ.")


class AIProviderAdapter(ABC):
    provider_name: str = ""

    @abstractmethod
    def test_connection(self, config: ProviderConfig) -> TestConnectionResult:
        raise NotImplementedError

    @abstractmethod
    def generate_structured_output(
        self,
        config: ProviderConfig,
        system_prompt: str,
        user_prompt: str,
        context: dict[str, Any] | None = None,
    ) -> StructuredGenerationResult:
        raise NotImplementedError
