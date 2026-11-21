from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

API_DIR = Path(__file__).resolve().parent.parent
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_file = tmp_path / "test_finz.sqlite3"
    monkeypatch.setenv("FINZ_DATABASE_URL", f"sqlite:///{db_file}")

    from app import config as cfg_mod
    from app import db as db_mod
    from app.security import secret_store as ss_mod
    from app.ai.gateway import gateway

    monkeypatch.setattr(cfg_mod.settings, "data_dir", tmp_path)
    monkeypatch.setattr(cfg_mod.settings, "db_path", db_file)
    monkeypatch.setattr(cfg_mod.settings, "secret_backend", "memory")
    ss_mod.secret_store._memory_store.clear()

    # Rebind engine and session to isolated temp SQLite file
    test_engine = db_mod._create_engine(f"sqlite:///{db_file}")
    TestSession = db_mod.sessionmaker(bind=test_engine, autoflush=False, autocommit=False, expire_on_commit=False)
    monkeypatch.setattr(db_mod, "engine", test_engine)
    monkeypatch.setattr(db_mod, "SessionLocal", TestSession)
    db_mod.Base.metadata.create_all(bind=test_engine)

    from app.main import app

    def override_get_db():
        s = TestSession()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[db_mod.get_db] = override_get_db

    # Reset gateway adapters cleanly
    from app.ai.adapters.claude_adapter import ClaudeAdapter
    from app.ai.adapters.gemini_adapter import GeminiAdapter
    from app.ai.adapters.mock_adapter import MockAdapter
    from app.ai.adapters.openai_adapter import OpenAIAdapter

    gateway.adapters = {
        "openai": OpenAIAdapter(),
        "gemini": GeminiAdapter(),
        "claude": ClaudeAdapter(),
        "mock": MockAdapter(),
    }

    with TestClient(app) as tc:
        yield tc, db_file

    app.dependency_overrides.clear()
    test_engine.dispose()
