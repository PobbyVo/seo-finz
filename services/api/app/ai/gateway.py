from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.ai.adapters.base import (
    AIProviderAdapter,
    ProviderConfig,
    StructuredGenerationResult,
    TestConnectionResult,
)
from app.ai.adapters.claude_adapter import ClaudeAdapter, DEFAULT_CLAUDE_MODEL
from app.ai.adapters.gemini_adapter import (
    DEFAULT_GEMINI_FALLBACK_CHAIN,
    GeminiAdapter,
    build_effective_chain,
)
from app.ai.adapters.mock_adapter import MockAdapter
from app.ai.adapters.openai_adapter import DEFAULT_OPENAI_MODEL, OpenAIAdapter
from app.knowledge import playbook, prompt_hash, load_thresholds
from app.ai.errors import AIProviderError, build_error
from app.models import AIProviderSetting, AIRun, ProjectEvent, SourceKeyword, TopicPillar
from app.security.secret_store import secret_store
from app.security.ssrf import DEFAULT_PROVIDER_ENDPOINTS, validate_provider_endpoint

SUPPORTED_PROVIDERS = ("openai", "gemini", "claude", "mock")

DEFAULT_PROVIDER_MODELS: dict[str, str] = {
    "openai": DEFAULT_OPENAI_MODEL,
    "gemini": "auto",  # Auto-selects newest Gemini model + downgrades after 3 failures
    "claude": DEFAULT_CLAUDE_MODEL,
    "mock": "finz-mock-deterministic-v1",
}


class AIProviderGateway:
    """Unified Provider Gateway mediating Settings, Test Connection, and AI runs."""

    def __init__(self, adapters: dict[str, AIProviderAdapter] | None = None) -> None:
        self.adapters: dict[str, AIProviderAdapter] = adapters or {
            "openai": OpenAIAdapter(),
            "gemini": GeminiAdapter(),
            "claude": ClaudeAdapter(),
            "mock": MockAdapter(),
        }

    def ensure_default_rows(self, db: Session) -> list[AIProviderSetting]:
        rows = {r.provider: r for r in db.query(AIProviderSetting).all()}
        changed = False
        for prov in SUPPORTED_PROVIDERS:
            if prov not in rows:
                is_gemini = prov == "gemini"
                chain = list(DEFAULT_GEMINI_FALLBACK_CHAIN) if is_gemini else []
                row = AIProviderSetting(
                    provider=prov,
                    is_active=False,
                    secret_ref=None,
                    secret_storage_mode="none",
                    key_hint=None,
                    model_id=DEFAULT_PROVIDER_MODELS[prov],
                    active_model_id=(chain[0] if is_gemini else DEFAULT_PROVIDER_MODELS[prov]),
                    use_shared_model=True,
                    endpoint_url=DEFAULT_PROVIDER_ENDPOINTS[prov],
                    auto_latest=is_gemini,
                    downgrade_threshold=3,
                    fallback_chain_json=json.dumps(chain),
                    failure_counts_json="{}",
                    connection_status=("READY_TO_TEST" if prov == "mock" else "NOT_CONFIGURED"),
                )
                db.add(row)
                rows[prov] = row
                changed = True
        if changed:
            db.commit()
        return [rows[p] for p in SUPPORTED_PROVIDERS]

    def get_active_setting(self, db: Session) -> AIProviderSetting | None:
        self.ensure_default_rows(db)
        return db.query(AIProviderSetting).filter(AIProviderSetting.is_active == True).first()  # noqa: E712

    def _build_config(
        self,
        setting: AIProviderSetting,
        *,
        role: str = "ANALYST",
        override_api_key: str | None = None,
        override_model: str | None = None,
        override_endpoint: str | None = None,
    ) -> ProviderConfig:
        endpoint = validate_provider_endpoint(setting.provider, override_endpoint or setting.endpoint_url)
        api_key = override_api_key
        if not api_key and setting.provider != "mock":
            api_key, _ = secret_store.get_secret(setting.provider, setting.secret_ref)

        chain = json.loads(setting.fallback_chain_json or "[]")
        failure_counts = json.loads(setting.failure_counts_json or "{}")

        chosen_model = override_model
        if not chosen_model:
            if not setting.use_shared_model:
                if role == "ANALYST" and setting.analyst_model_id:
                    chosen_model = setting.analyst_model_id
                elif role.startswith("CRITIC") and setting.critic_model_id:
                    chosen_model = setting.critic_model_id
            if not chosen_model:
                if setting.provider == "gemini":
                    chosen_model = setting.active_model_id or setting.model_id or "auto"
                else:
                    chosen_model = setting.model_id or DEFAULT_PROVIDER_MODELS[setting.provider]

        if setting.provider == "gemini":
            chain = build_effective_chain(
                configured_model=chosen_model,
                existing_chain=chain,
                auto_latest=setting.auto_latest,
            )

        return ProviderConfig(
            provider=setting.provider,
            api_key=api_key,
            model_id=chosen_model,
            endpoint_url=endpoint,
            auto_latest=setting.auto_latest,
            downgrade_threshold=max(1, int(setting.downgrade_threshold or 3)),
            fallback_chain=chain,
            failure_counts=failure_counts,
        )

    def _persist_gemini_state(
        self,
        db: Session,
        setting: AIProviderSetting,
        *,
        actual_model: str,
        discovered_models: list[str] | None,
        fallback_events: list[Any],
        updated_failure_counts: dict[str, int],
        project_id: str | None = None,
    ) -> None:
        if setting.provider != "gemini":
            return

        existing_chain = json.loads(setting.fallback_chain_json or "[]")
        merged_chain = build_effective_chain(
            configured_model=setting.model_id,
            existing_chain=existing_chain,
            discovered=discovered_models,
            auto_latest=setting.auto_latest,
        )
        setting.fallback_chain_json = json.dumps(merged_chain)
        setting.failure_counts_json = json.dumps(updated_failure_counts)
        if actual_model:
            setting.active_model_id = actual_model

        if fallback_events:
            last_ev = fallback_events[-1]
            setting.last_downgrade_reason = last_ev.reason
            setting.last_downgrade_at = datetime.now(timezone.utc)
            for ev in fallback_events:
                db.add(
                    ProjectEvent(
                        project_id=project_id,
                        level="WARNING",
                        event_type="GEMINI_MODEL_DOWNGRADED",
                        message=ev.reason,
                        details_json=json.dumps(
                            {
                                "from_model": ev.from_model,
                                "to_model": ev.to_model,
                                "failures": ev.failures_on_model,
                                "error_code": ev.error_code,
                            },
                            ensure_ascii=False,
                        ),
                    )
                )

    def test_connection(
        self,
        db: Session,
        provider: str,
        *,
        api_key: str | None = None,
        model_id: str | None = None,
        endpoint_url: str | None = None,
        auto_latest: bool | None = None,
        downgrade_threshold: int | None = None,
    ) -> TestConnectionResult:
        self.ensure_default_rows(db)
        setting = db.get(AIProviderSetting, provider)
        if not setting:
            raise AIProviderError(build_error("AI_NOT_CONFIGURED", detail=f"Provider không hợp lệ: {provider}"))

        if auto_latest is not None and provider == "gemini":
            setting.auto_latest = auto_latest
        if downgrade_threshold is not None and provider == "gemini":
            setting.downgrade_threshold = max(1, min(10, downgrade_threshold))

        try:
            config = self._build_config(
                setting,
                override_api_key=api_key,
                override_model=model_id,
                override_endpoint=endpoint_url,
            )
        except ValueError as exc:
            err = build_error("INVALID_PROVIDER_RESPONSE", detail=str(exc))
            return TestConnectionResult(
                ok=False,
                provider=provider,
                requested_model=model_id or setting.model_id,
                actual_model=model_id or setting.model_id,
                latency_ms=0,
                status="ERROR",
                message=err.reason,
                error=err.to_dict(),
            )

        setting.connection_status = "TESTING"
        db.commit()

        adapter = self.adapters[provider]
        try:
            result = adapter.test_connection(config)
        except Exception as exc:
            err = build_error("PROVIDER_UNAVAILABLE", detail=str(exc))
            result = TestConnectionResult(
                ok=False,
                provider=provider,
                requested_model=config.model_id,
                actual_model=config.model_id,
                latency_ms=0,
                status="ERROR",
                message=err.reason,
                error=err.to_dict(),
            )

        now = datetime.now(timezone.utc)
        setting.last_tested_at = now
        setting.last_latency_ms = result.latency_ms
        setting.connection_status = "CONNECTED" if result.ok else "ERROR"
        setting.last_error_code = None if result.ok else (result.error or {}).get("code")
        setting.last_error_json = None if result.ok else json.dumps(result.error or {}, ensure_ascii=False)
        if result.ok and result.actual_model:
            setting.active_model_id = result.actual_model

        self._persist_gemini_state(
            db,
            setting,
            actual_model=result.actual_model,
            discovered_models=result.discovered_models,
            fallback_events=result.fallback_events,
            updated_failure_counts=result.updated_failure_counts,
        )

        db.add(
            AIRun(
                project_id=None,
                role="TEST_CONNECTION",
                provider=provider,
                requested_model=result.requested_model,
                actual_model=result.actual_model,
                latency_ms=result.latency_ms,
                fallback_events_json=json.dumps([e.__dict__ for e in result.fallback_events], ensure_ascii=False),
                status="COMPLETED" if result.ok else "ERROR",
                error_code=setting.last_error_code,
                output_json=json.dumps({"ok": result.ok, "message": result.message}, ensure_ascii=False),
            )
        )
        db.commit()
        return result

    def generate_structured(
        self,
        db: Session,
        *,
        project_id: str,
        role: str,
        system_prompt: str,
        user_prompt: str,
        context: dict[str, Any],
        research_cycle: int = 1,
        source_refs: list[str] | None = None,
    ) -> tuple[StructuredGenerationResult, AIRun]:
        setting = self.get_active_setting(db)
        if not setting:
            raise AIProviderError(build_error("AI_NOT_CONFIGURED"))

        config = self._build_config(setting, role=role)
        if role == "BRIEF_WRITER":config.timeout_seconds = 90.0
        if setting.provider != "mock" and not config.api_key:
            raise AIProviderError(build_error("AI_NOT_CONFIGURED"))

        context = dict(context)
        context["source_keywords"] = [{key: getattr(row, key) for key in ("keyword", "role", "content_code", "funnel_stage", "title_match_check", "content_title", "subtopic", "planner_volume", "source_ref")} for row in db.query(SourceKeyword).filter_by(project_id=project_id).all()]
        context["pillar_boundaries"] = [{"code": row.code, "notes": row.notes, "main_topic": row.main_topic} for row in db.query(TopicPillar).filter_by(project_id=project_id).all()]
        user_prompt += "\nMetadata nguồn (planner_volume chỉ tham khảo, không phải Semrush):\n" + json.dumps(context, ensure_ascii=False)
        system_prompt += "\n" + playbook() + "\nNgưỡng đề xuất hiện tại:\n" + json.dumps(load_thresholds(), ensure_ascii=False)
        adapter = self.adapters[setting.provider]
        result = adapter.generate_structured_output(config, system_prompt, user_prompt, context=context)

        self._persist_gemini_state(
            db,
            setting,
            actual_model=result.actual_model,
            discovered_models=None,
            fallback_events=result.fallback_events,
            updated_failure_counts=result.updated_failure_counts,
            project_id=project_id,
        )

        if not result.ok and result.error:
            setting.last_error_code = result.error.get("code")
            setting.last_error_json = json.dumps(result.error, ensure_ascii=False)

        ai_run = AIRun(
            project_id=project_id,
            role=role,
            provider=setting.provider,
            requested_model=result.requested_model,
            actual_model=result.actual_model,
            prompt_version=prompt_hash(system_prompt),
            schema_version="2.0.0",
            research_cycle=research_cycle,
            latency_ms=result.latency_ms,
            fallback_events_json=json.dumps([e.__dict__ for e in result.fallback_events], ensure_ascii=False),
            source_refs_json=json.dumps(source_refs or [], ensure_ascii=False),
            status="COMPLETED" if result.ok else "ERROR",
            error_code=(result.error or {}).get("code") if not result.ok else None,
            output_json=json.dumps(result.data if result.ok else (result.error or {}), ensure_ascii=False),
        )
        db.add(ai_run)
        db.commit()
        db.refresh(ai_run)

        if not result.ok:
            err_dict = result.error or build_error("PROVIDER_UNAVAILABLE").to_dict()
            raise AIProviderError(
                build_error(
                    err_dict.get("code", "PROVIDER_UNAVAILABLE"),
                    detail=err_dict.get("reason"),
                    http_status=err_dict.get("http_status"),
                )
            )
        return result, ai_run


gateway = AIProviderGateway()
