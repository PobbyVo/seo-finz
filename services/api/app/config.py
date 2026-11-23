from __future__ import annotations

import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

API_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = API_ROOT.parent.parent
DEFAULT_DATA_DIR = REPO_ROOT / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FINZ_", extra="ignore")

    app_name: str = "FinZ SEO Workbench API"
    app_version: str = "2.0.0"
    host: str = "127.0.0.1"
    port: int = 8000
    data_dir: Path = DEFAULT_DATA_DIR
    db_path: Path | None = None
    web_origin: str = "http://127.0.0.1:3000,http://localhost:3000"
    max_upload_rows: int = 25000
    max_upload_bytes: int = 15 * 1024 * 1024  # 15 MB
    max_critique_rounds_per_cycle: int = 2
    default_gemini_downgrade_threshold: int = 3
    secret_backend: str = "auto"  # auto | keyring | env | memory (tests)

    @property
    def resolved_db_path(self) -> Path:
        if self.db_path is not None:
            return Path(self.db_path)
        return self.data_dir / "finz_workbench.sqlite3"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def backups_dir(self) -> Path:
        return self.data_dir / "backups"

    @property
    def exports_dir(self) -> Path:
        return self.data_dir / "exports"

    @property
    def database_url(self) -> str:
        env_url = os.environ.get("FINZ_DATABASE_URL")
        if env_url:
            return env_url
        return f"sqlite:///{self.resolved_db_path}"

    @property
    def allowed_origins(self) -> list[str]:
        return [o.strip() for o in self.web_origin.split(",") if o.strip()]


settings = Settings()


def ensure_data_dirs() -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    settings.backups_dir.mkdir(parents=True, exist_ok=True)
    settings.exports_dir.mkdir(parents=True, exist_ok=True)
