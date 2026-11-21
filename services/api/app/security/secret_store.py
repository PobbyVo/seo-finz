from __future__ import annotations

import os
from typing import Tuple

import keyring
from keyring.errors import KeyringError, NoKeyringError

from app.config import settings

SERVICE_NAME = "finz-seo-workbench"

PROVIDER_ENV_VARS: dict[str, list[str]] = {
    "openai": ["FINZ_OPENAI_API_KEY", "OPENAI_API_KEY"],
    "gemini": ["FINZ_GEMINI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"],
    "claude": ["FINZ_CLAUDE_API_KEY", "ANTHROPIC_API_KEY"],
}


class SecretStoreError(RuntimeError):
    pass


class SecretStore:
    """
    Secure secret manager:
    - Prefers OS credential store (macOS Keychain / Windows Credential Locker / Linux SecretService).
    - Supports explicit server environment variables when OS keyring is unavailable.
    - NEVER persists plaintext keys to SQLite, JSON exports, or logs.
    """

    def __init__(self) -> None:
        self._memory_store: dict[str, str] = {}

    @staticmethod
    def mask_key(raw_key: str | None) -> str | None:
        if not raw_key:
            return None
        cleaned = raw_key.strip()
        if len(cleaned) <= 4:
            return "****"
        return f"****{cleaned[-4:]}"

    def _keyring_available(self) -> bool:
        if settings.secret_backend == "memory":
            return False
        if settings.secret_backend == "env":
            return False
        try:
            kr = keyring.get_keyring()
            # Reject null/fail keyrings so we never silently fail
            name = kr.__class__.__name__.lower()
            if "fail" in name or "null" in name:
                return False
            return True
        except Exception:
            return False

    def save_secret(self, provider: str, api_key: str) -> Tuple[str, str]:
        """Store API key securely and return (secret_ref, storage_mode)."""
        cleaned = api_key.strip()
        if not cleaned:
            raise SecretStoreError("API key trống.")

        if settings.secret_backend == "memory":
            ref = f"memory:{SERVICE_NAME}:{provider}"
            self._memory_store[ref] = cleaned
            return ref, "memory"

        if self._keyring_available():
            try:
                keyring.set_password(SERVICE_NAME, provider, cleaned)
                return f"keyring:{SERVICE_NAME}:{provider}", "keyring"
            except (KeyringError, NoKeyringError, Exception) as exc:
                raise SecretStoreError(
                    f"Không thể lưu API key vào OS Keychain ({exc}). "
                    f"Bạn có thể cấu hình biến môi trường {', '.join(PROVIDER_ENV_VARS.get(provider, []))}."
                ) from exc

        raise SecretStoreError(
            "Máy hiện tại không có OS Keychain khả dụng. Hệ thống từ chối lưu plaintext API key vào SQLite. "
            f"Vui lòng thiết lập biến môi trường {', '.join(PROVIDER_ENV_VARS.get(provider, []))} trên server local."
        )

    def get_secret(self, provider: str, secret_ref: str | None = None) -> tuple[str | None, str]:
        """Return (api_key, source_mode) without ever logging the key."""
        if secret_ref and secret_ref.startswith("memory:"):
            val = self._memory_store.get(secret_ref)
            if val:
                return val, "memory"

        if secret_ref and secret_ref.startswith("keyring:") and self._keyring_available():
            try:
                val = keyring.get_password(SERVICE_NAME, provider)
                if val:
                    return val, "keyring"
            except Exception:
                pass

        # Fallback: check explicit environment variables
        for env_name in PROVIDER_ENV_VARS.get(provider, []):
            env_val = os.environ.get(env_name, "").strip()
            if env_val:
                return env_val, f"env:{env_name}"

        return None, "none"

    def delete_secret(self, provider: str, secret_ref: str | None = None) -> None:
        if secret_ref and secret_ref.startswith("memory:"):
            self._memory_store.pop(secret_ref, None)
            return
        if self._keyring_available():
            try:
                keyring.delete_password(SERVICE_NAME, provider)
            except Exception:
                pass

    def has_env_key(self, provider: str) -> str | None:
        for env_name in PROVIDER_ENV_VARS.get(provider, []):
            if os.environ.get(env_name, "").strip():
                return env_name
        return None


secret_store = SecretStore()
