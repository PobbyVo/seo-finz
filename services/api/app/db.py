from __future__ import annotations

import logging
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import ensure_data_dirs, settings

logger = logging.getLogger("finz.db")

_WIN_DRIVE_RE = re.compile(r"^/?([A-Za-z]:[\\/].*)$")


class BackupError(RuntimeError):
    """Raised when a SQLite online backup fails integrity verification, path resolution, or disk write."""


class Base(DeclarativeBase):
    pass


def resolve_sqlite_db_path(
    database_url: str | None = None,
    *,
    base_dir: Path | None = None,
    platform_name: str | None = None,
) -> Path:
    """
    Resolve the exact filesystem path targeted by a SQLAlchemy SQLite URL using `make_url`.
    Fails closed for non-SQLite backends and `:memory:` databases so pre-migration backups
    never silently target a wrong file or report fake safety.
    """
    raw_url = database_url or settings.database_url
    try:
        parsed = make_url(raw_url)
    except Exception as exc:
        raise BackupError(f"INVALID_DATABASE_URL: Không thể phân tích URL cơ sở dữ liệu ({exc}).") from exc

    if not parsed.drivername.lower().startswith("sqlite"):
        raise BackupError(
            f"UNSUPPORTED_DB_BACKEND: Sao lưu cục bộ SQLite không hỗ trợ backend '{parsed.drivername}'."
        )

    db_target = parsed.database
    if not db_target or db_target == ":memory:" or str(parsed.query.get("mode", "")).lower() == "memory":
        raise BackupError(
            "UNSUPPORTED_SQLITE_MEMORY_DB: Không thể sao lưu file cho SQLite in-memory (:memory:)."
        )

    eff_platform = (platform_name or os.name).lower()
    # Handle Windows drive letter URLs (e.g. sqlite:///C:/Users/Test User/finz.sqlite3)
    win_match = _WIN_DRIVE_RE.match(db_target)
    if eff_platform == "nt" or win_match:
        win_str = win_match.group(1) if win_match else db_target
        if eff_platform == "nt" and os.name != "nt":
            # Cross-platform unit-testable path normalization without failing on POSIX
            return Path(PureWindowsPath(win_str).as_posix())
        return Path(win_str)

    p = Path(db_target)
    if not p.is_absolute():
        anchor = Path(base_dir) if base_dir is not None else Path.cwd()
        return (anchor / p).resolve()
    return p


def _create_engine(url: str):
    connect_args = {"check_same_thread": False, "timeout": 15.0} if url.startswith("sqlite") else {}
    eng = create_engine(url, connect_args=connect_args, future=True)

    if url.startswith("sqlite"):
        @event.listens_for(eng, "connect")
        def _set_sqlite_pragma(dbapi_conn, _connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=15000")
            cursor.close()

    return eng


ensure_data_dirs()
engine = _create_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def verify_sqlite_integrity(db_file: Path) -> tuple[bool, list[str]]:
    """Run PRAGMA quick_check and PRAGMA foreign_key_check on a SQLite file."""
    errors: list[str] = []
    conn = sqlite3.connect(str(db_file), timeout=15.0)
    try:
        qc_rows = conn.execute("PRAGMA quick_check").fetchall()
        if not qc_rows or [r[0] for r in qc_rows] != ["ok"]:
            errors.append(f"quick_check failed: {qc_rows}")
        fk_rows = conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk_rows:
            errors.append(f"foreign_key_check violations: {len(fk_rows)} row(s)")
    finally:
        conn.close()
    return len(errors) == 0, errors


def backup_database(
    reason: str = "manual",
    *,
    source_path: Path | None = None,
    database_url: str | None = None,
    backups_dir: Path | None = None,
    verify: bool = True,
) -> Path | None:
    """
    Create a WAL-consistent online SQLite backup via sqlite3.Connection.backup().
    - Resolves the effective SQLite file from `source_path` or `database_url` / `settings.database_url`
      (NEVER ignoring custom `FINZ_DATABASE_URL`).
    - Returns None cleanly ONLY when the source SQLite file does not exist yet (fresh bootstrap).
    - Writes to a unique temporary file, verifies integrity (quick_check + foreign_key_check),
      and atomically renames to the final destination.
    - Cleans up incomplete temp files and FAILS CLOSED on disk-full, wrong path, or verification errors.
    """
    ensure_data_dirs()
    src = Path(source_path) if source_path is not None else resolve_sqlite_db_path(database_url or settings.database_url)
    if not src.exists():
        logger.info("SQLite source %s does not exist yet (fresh bootstrap); skipping backup.", src)
        return None
    if src.is_dir():
        raise BackupError(f"Đường dẫn SQLite nguồn là thư mục, không phải tệp hợp lệ: {src}")

    target_dir = Path(backups_dir) if backups_dir is not None else settings.backups_dir
    target_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    uniq = uuid.uuid4().hex[:6]
    safe_reason = "".join(c if c.isalnum() or c in "-_" else "_" for c in reason)[:32] or "backup"
    dst = target_dir / f"finz_backup_{ts}_{uniq}_{safe_reason}.sqlite3"
    tmp = target_dir / f".{dst.name}.tmp"

    src_conn: sqlite3.Connection | None = None
    dst_conn: sqlite3.Connection | None = None
    try:
        src_conn = sqlite3.connect(str(src), timeout=15.0)
        src_conn.execute("PRAGMA busy_timeout=15000")
        dst_conn = sqlite3.connect(str(tmp), timeout=15.0)
        src_conn.backup(dst_conn, pages=256, sleep=0.01)
        dst_conn.commit()
        dst_conn.close()
        dst_conn = None
        src_conn.close()
        src_conn = None

        if verify:
            ok, errs = verify_sqlite_integrity(tmp)
            if not ok:
                raise BackupError(f"Kiểm tra toàn vẹn bản sao lưu thất bại: {'; '.join(errs)}")

        os.replace(tmp, dst)

        size_bytes = dst.stat().st_size
        total_backup_bytes = sum(
            p.stat().st_size for p in target_dir.glob("*.sqlite3") if p.is_file()
        )
        logger.info(
            "SQLite online backup created: %s from %s (%d bytes; total backups dir: %d bytes)",
            dst.name,
            src,
            size_bytes,
            total_backup_bytes,
        )
        if total_backup_bytes > 500 * 1024 * 1024:
            logger.warning(
                "Thư mục backups đang dùng %.1f MB; hãy cân nhắc dọn bản cũ thủ công.",
                total_backup_bytes / (1024 * 1024),
            )
        return dst
    except Exception as exc:
        if dst_conn is not None:
            try:
                dst_conn.close()
            except Exception:
                pass
        if src_conn is not None:
            try:
                src_conn.close()
            except Exception:
                pass
        if tmp.exists():
            try:
                tmp.unlink()
            except Exception:
                pass
        if isinstance(exc, BackupError):
            raise
        raise BackupError(f"Sao lưu SQLite thất bại ({exc.__class__.__name__}: {exc})") from exc
