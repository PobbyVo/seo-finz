from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.ai.adapters.gemini_adapter import DEFAULT_GEMINI_FALLBACK_CHAIN, GeminiAdapter, build_effective_chain
from app.ai.errors import AIProviderError, build_error
from app.ai.gateway import DEFAULT_PROVIDER_MODELS, SUPPORTED_PROVIDERS, gateway
from app.db import get_db
from app.models import AIProviderSetting, ProjectEvent
from app.schemas import AISettingUpdateRequest, AITestConnectionRequest
from app.security.secret_store import SecretStoreError, secret_store
from app.security.ssrf import DEFAULT_PROVIDER_ENDPOINTS, validate_provider_endpoint

router = APIRouter(prefix="/settings/ai", tags=["settings-ai"])


def _serialize_provider(row: AIProviderSetting) -> dict[str, Any]:
    """Serialize provider metadata ONLY — NEVER exposes raw API keys!"""
    env_var = secret_store.has_env_key(row.provider) if row.provider != "mock" else None
    has_key = row.provider == "mock" or bool(row.secret_ref) or bool(env_var)
    storage_mode = row.secret_storage_mode
    if row.provider != "mock" and not row.secret_ref and env_var:
        storage_mode = f"env:{env_var}"

    chain = json.loads(row.fallback_chain_json or "[]")
    if row.provider == "gemini" and not chain:
        chain = list(DEFAULT_GEMINI_FALLBACK_CHAIN)
    failure_counts = json.loads(row.failure_counts_json or "{}")

    return {
        "provider": row.provider,
        "is_active": row.is_active,
        "has_key": has_key,
        "key_hint": row.key_hint if row.secret_ref else (f"ENV ({env_var})" if env_var else None),
        "secret_storage_mode": storage_mode,
        "model_id": row.model_id or DEFAULT_PROVIDER_MODELS[row.provider],
        "active_model_id": row.active_model_id or (chain[0] if row.provider == "gemini" and chain else row.model_id),
        "use_shared_model": row.use_shared_model,
        "analyst_model_id": row.analyst_model_id,
        "critic_model_id": row.critic_model_id,
        "endpoint_url": row.endpoint_url or DEFAULT_PROVIDER_ENDPOINTS[row.provider],
        "auto_latest": row.auto_latest,
        "downgrade_threshold": row.downgrade_threshold,
        "fallback_chain": chain,
        "failure_counts": failure_counts,
        "last_downgrade_reason": row.last_downgrade_reason,
        "last_downgrade_at": row.last_downgrade_at.isoformat() if row.last_downgrade_at else None,
        "connection_status": row.connection_status,
        "last_tested_at": row.last_tested_at.isoformat() if row.last_tested_at else None,
        "last_latency_ms": row.last_latency_ms,
        "last_error_code": row.last_error_code,
        "last_error": json.loads(row.last_error_json) if row.last_error_json else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.get("")
def get_ai_settings(db: Session = Depends(get_db)):
    rows = gateway.ensure_default_rows(db)
    active = next((r.provider for r in rows if r.is_active), None)
    return {
        "active_provider": active,
        "providers": [_serialize_provider(r) for r in rows],
        "security_notice": (
            "API key chỉ lưu trong OS Keychain hoặc biến môi trường server local; "
            "KHÔNG bao giờ lưu plaintext vào SQLite, localStorage, log hay file export."
        ),
        "cost_notice": (
            "Test Connection gửi một yêu cầu nhỏ đến nhà cung cấp (có thể phát sinh chi phí nhỏ trừ Mock Provider) "
            "và KHÔNG gửi dữ liệu dự án/keyword của bạn."
        ),
    }


@router.put("")
def update_ai_settings(payload: AISettingUpdateRequest, db: Session = Depends(get_db)):
    provider = payload.provider.lower().strip()
    if provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(status_code=400, detail=build_error("AI_NOT_CONFIGURED", detail=f"Provider không hợp lệ: {provider}").to_dict())

    rows = gateway.ensure_default_rows(db)
    row = next(r for r in rows if r.provider == provider)

    try:
        validated_endpoint = validate_provider_endpoint(provider, payload.endpoint_url or row.endpoint_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=build_error("INVALID_PROVIDER_RESPONSE", detail=str(exc)).to_dict())

    row.endpoint_url = validated_endpoint
    row.use_shared_model = payload.use_shared_model
    row.analyst_model_id = (payload.analyst_model_id or "").strip() or None
    row.critic_model_id = (payload.critic_model_id or "").strip() or None

    if payload.model_id is not None:
        cleaned_model = payload.model_id.strip() or DEFAULT_PROVIDER_MODELS[provider]
        row.model_id = cleaned_model
        if provider != "gemini" or cleaned_model != "auto":
            row.active_model_id = cleaned_model

    if provider == "gemini":
        if payload.auto_latest is not None:
            row.auto_latest = payload.auto_latest
        if payload.downgrade_threshold is not None:
            row.downgrade_threshold = max(1, min(10, payload.downgrade_threshold))
        existing_chain = payload.fallback_chain if payload.fallback_chain else json.loads(row.fallback_chain_json or "[]")
        merged = build_effective_chain(
            configured_model=row.model_id,
            existing_chain=existing_chain,
            auto_latest=row.auto_latest,
        )
        row.fallback_chain_json = json.dumps(merged)
        if row.auto_latest or row.model_id == "auto" or not row.active_model_id:
            row.active_model_id = merged[0]

    # Store API key securely (NEVER plaintext in SQLite!)
    if payload.api_key and payload.api_key.strip() and provider != "mock":
        try:
            secret_ref, mode = secret_store.save_secret(provider, payload.api_key)
        except SecretStoreError as exc:
            raise HTTPException(status_code=400, detail=build_error("AI_NOT_CONFIGURED", detail=str(exc)).to_dict())
        row.secret_ref = secret_ref
        row.secret_storage_mode = mode
        row.key_hint = secret_store.mask_key(payload.api_key)
        row.connection_status = "READY_TO_TEST"
        row.last_error_code = None
        row.last_error_json = None
    elif provider == "mock":
        row.secret_ref = None
        row.secret_storage_mode = "none"
        row.key_hint = "LOCAL MOCK"
        row.connection_status = "READY_TO_TEST"

    if payload.set_active:
        for r in rows:
            r.is_active = r.provider == provider

    db.add(
        ProjectEvent(
            project_id=None,
            level="INFO",
            event_type="AI_SETTINGS_UPDATED",
            message=f"Đã cập nhật cấu hình AI Provider '{provider}' (model: {row.active_model_id or row.model_id}).",
            details_json=json.dumps({"provider": provider, "active": row.is_active, "model": row.active_model_id or row.model_id}),
        )
    )
    db.commit()
    db.refresh(row)
    return {
        "saved": True,
        "provider": _serialize_provider(row),
        "active_provider": next((r.provider for r in rows if r.is_active), None),
    }


@router.post("/test")
def test_ai_connection(payload: AITestConnectionRequest, db: Session = Depends(get_db)):
    provider = payload.provider.lower().strip()
    if provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(status_code=400, detail=build_error("AI_NOT_CONFIGURED", detail=f"Provider không hợp lệ: {provider}").to_dict())

    try:
        res = gateway.test_connection(
            db,
            provider,
            api_key=payload.api_key,
            model_id=payload.model_id,
            endpoint_url=payload.endpoint_url,
            auto_latest=payload.auto_latest,
            downgrade_threshold=payload.downgrade_threshold,
        )
    except AIProviderError as exc:
        raise HTTPException(status_code=400, detail=exc.error.to_dict())

    row = db.get(AIProviderSetting, provider)
    return {
        "ok": res.ok,
        "provider": res.provider,
        "requested_model": res.requested_model,
        "actual_model": res.actual_model,
        "latency_ms": res.latency_ms,
        "status": res.status,
        "message": res.message,
        "discovered_models": res.discovered_models,
        "fallback_events": [e.__dict__ for e in res.fallback_events],
        "error": res.error,
        "provider_state": _serialize_provider(row) if row else None,
    }


@router.post("/gemini/reset-latest")
def reset_gemini_to_latest(db: Session = Depends(get_db)):
    gateway.ensure_default_rows(db)
    row = db.get(AIProviderSetting, "gemini")
    assert row is not None
    chain = json.loads(row.fallback_chain_json or "[]") or list(DEFAULT_GEMINI_FALLBACK_CHAIN)
    row.auto_latest = True
    row.model_id = "auto"
    row.active_model_id = chain[0]
    row.failure_counts_json = "{}"
    row.last_downgrade_reason = None
    row.last_downgrade_at = None
    db.commit()
    db.refresh(row)
    return {"ok": True, "message": f"Đã khôi phục Gemini về model mới nhất ({chain[0]}) và đặt lại bộ đếm lỗi.", "provider": _serialize_provider(row)}


@router.post("/gemini/sync-models")
def sync_gemini_models(db: Session = Depends(get_db)):
    gateway.ensure_default_rows(db)
    row = db.get(AIProviderSetting, "gemini")
    assert row is not None
    api_key, _ = secret_store.get_secret("gemini", row.secret_ref)
    if not api_key:
        raise HTTPException(status_code=400, detail=build_error("AI_NOT_CONFIGURED", detail="Cần lưu Gemini API key trước khi đồng bộ danh sách model.").to_dict())

    adapter = gateway.adapters["gemini"]
    assert isinstance(adapter, GeminiAdapter)
    endpoint = validate_provider_endpoint("gemini", row.endpoint_url)
    discovered = adapter.discover_latest_models(api_key, endpoint)
    merged = build_effective_chain(configured_model="auto", existing_chain=json.loads(row.fallback_chain_json or "[]"), discovered=discovered, auto_latest=True)
    row.fallback_chain_json = json.dumps(merged)
    if row.auto_latest:
        row.active_model_id = merged[0]
    db.commit()
    db.refresh(row)
    return {
        "ok": True,
        "discovered_count": len(discovered),
        "discovered_models": discovered,
        "fallback_chain": merged,
        "active_model_id": row.active_model_id,
        "provider": _serialize_provider(row),
    }


@router.delete("/{provider}")
def delete_provider_key(provider: str, db: Session = Depends(get_db)):
    prov = provider.lower().strip()
    if prov not in SUPPORTED_PROVIDERS:
        raise HTTPException(status_code=404, detail="Provider không tồn tại.")
    gateway.ensure_default_rows(db)
    row = db.get(AIProviderSetting, prov)
    assert row is not None

    secret_store.delete_secret(prov, row.secret_ref)
    row.secret_ref = None
    row.secret_storage_mode = "none"
    row.key_hint = None
    row.connection_status = "NOT_CONFIGURED" if prov != "mock" else "READY_TO_TEST"
    row.last_error_code = None
    row.last_error_json = None
    if row.is_active and prov != "mock":
        row.is_active = False
    db.add(
        ProjectEvent(
            project_id=None,
            level="INFO",
            event_type="AI_KEY_DELETED",
            message=f"Đã xóa API key đã lưu của nhà cung cấp '{prov}'.",
        )
    )
    db.commit()
    db.refresh(row)
    return {"deleted": True, "provider": _serialize_provider(row)}
