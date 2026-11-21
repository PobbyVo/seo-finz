from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from app.db import BackupError, backup_database, verify_sqlite_integrity
from app.models import EvidenceRow, FileUpload, Project, ResearchBatch

API_DIR = Path(__file__).resolve().parent.parent


def _build_legacy_0001_db(db_file: Path, *, project_code: str = "B01") -> None:
    conn = sqlite3.connect(str(db_file))
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(
        f"""
        CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY);
        INSERT INTO alembic_version VALUES ('0001_initial_schema');
        CREATE TABLE projects (
            id VARCHAR(40) PRIMARY KEY, code VARCHAR(32) NOT NULL, name VARCHAR(200) NOT NULL,
            pillar_name VARCHAR(200) DEFAULT '', topic_pillar_code VARCHAR(64) DEFAULT '',
            topic_pillar_name VARCHAR(255) DEFAULT '', topic_type VARCHAR(120) DEFAULT '',
            split_axis VARCHAR(200) DEFAULT '', main_topic VARCHAR(255) DEFAULT '',
            content_code VARCHAR(64) DEFAULT '', content_title VARCHAR(300) DEFAULT '',
            primary_keyword_original VARCHAR(300) DEFAULT '', primary_keyword_current VARCHAR(300) DEFAULT '',
            secondary_keywords_json TEXT DEFAULT '[]', business_goal TEXT DEFAULT '',
            target_audience TEXT DEFAULT '', market VARCHAR(32) DEFAULT 'VN', language VARCHAR(32) DEFAULT 'vi',
            soft_article_min INTEGER DEFAULT 5, soft_article_max INTEGER DEFAULT 7,
            provenance_json TEXT DEFAULT '{{}}', version INTEGER DEFAULT 1, research_cycle INTEGER DEFAULT 1,
            status VARCHAR(40) DEFAULT 'READY',
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE file_uploads (
            id VARCHAR(40) PRIMARY KEY, project_id VARCHAR(40) NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            research_request_id VARCHAR(40), purpose VARCHAR(40) DEFAULT 'SEMRUSH_IMPORT',
            filename VARCHAR(255) NOT NULL, stored_path VARCHAR(500) NOT NULL, sha256 VARCHAR(64) NOT NULL,
            size_bytes INTEGER DEFAULT 0, file_format VARCHAR(16) DEFAULT 'csv', sheet_name VARCHAR(120) DEFAULT '',
            encoding VARCHAR(32) DEFAULT 'utf-8', delimiter VARCHAR(8) DEFAULT ',', locale VARCHAR(16) DEFAULT 'en-US',
            row_count_total INTEGER DEFAULT 0, status VARCHAR(40) DEFAULT 'CONFIRMED', preview_meta_json TEXT DEFAULT '{{}}',
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE research_batches (
            id VARCHAR(40) PRIMARY KEY, project_id VARCHAR(40) NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            research_request_id VARCHAR(40), file_upload_id VARCHAR(40) REFERENCES file_uploads(id) ON DELETE SET NULL,
            report_type VARCHAR(40) DEFAULT 'KEYWORD_OVERVIEW', market VARCHAR(32) DEFAULT 'VN', locale VARCHAR(16) DEFAULT 'en-US',
            column_mapping_json TEXT DEFAULT '{{}}', total_raw_rows INTEGER DEFAULT 1, total_normalized_rows INTEGER DEFAULT 1,
            duplicate_rows_detected INTEGER DEFAULT 0, warnings_json TEXT DEFAULT '[]',
            source_timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, status VARCHAR(40) DEFAULT 'PROCESS_COMPLETED',
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE evidence_rows (
            id VARCHAR(40) PRIMARY KEY, project_id VARCHAR(40) NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            batch_id VARCHAR(40) NOT NULL REFERENCES research_batches(id) ON DELETE CASCADE,
            row_type VARCHAR(32) DEFAULT 'METRICS', source_row_number INTEGER DEFAULT 1,
            keyword VARCHAR(300) DEFAULT '', keyword_normalized VARCHAR(300) DEFAULT '',
            volume INTEGER, kd FLOAT, intent VARCHAR(120), cpc FLOAT, serp_features TEXT,
            organic_url TEXT, organic_position INTEGER, organic_title TEXT, organic_page_type VARCHAR(64),
            market VARCHAR(32) DEFAULT 'VN', is_duplicate BOOLEAN DEFAULT 0,
            raw_row_json TEXT DEFAULT '{{}}', warnings_json TEXT DEFAULT '[]',
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE approvals (
            id VARCHAR(40) PRIMARY KEY, project_id VARCHAR(40) NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            approval_type VARCHAR(48) NOT NULL, target_ref VARCHAR(120) DEFAULT '',
            title VARCHAR(255) NOT NULL, original_value TEXT DEFAULT '', proposed_value TEXT DEFAULT '',
            rationale TEXT DEFAULT '', evidence_json TEXT DEFAULT '[]', impact TEXT DEFAULT '',
            scope VARCHAR(32) DEFAULT 'BRIEF_ELIGIBILITY', status VARCHAR(32) DEFAULT 'PENDING',
            decision_note TEXT DEFAULT '', decided_by VARCHAR(120) DEFAULT '', version INTEGER DEFAULT 1,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, decided_at DATETIME
        );
        CREATE TABLE keyword_mappings (
            id VARCHAR(40) PRIMARY KEY, project_id VARCHAR(40) NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            demand_group_id VARCHAR(40), revision INTEGER DEFAULT 1, primary_keyword VARCHAR(300) NOT NULL,
            secondary_keywords_json TEXT DEFAULT '[]', page_type VARCHAR(32) DEFAULT 'ARTICLE',
            proposed_url VARCHAR(300) DEFAULT '', volume INTEGER, kd FLOAT, intent VARCHAR(120),
            metrics_source VARCHAR(255) DEFAULT '', priority VARCHAR(24) DEFAULT 'P2',
            business_value VARCHAR(32) DEFAULT 'MEDIUM', effort VARCHAR(32) DEFAULT 'MEDIUM',
            merge_split_proposal TEXT DEFAULT '', serp_status VARCHAR(40) DEFAULT 'SERP_NOT_VERIFIED',
            content_status VARCHAR(40) DEFAULT 'SERP_NOT_VERIFIED', evidence_json TEXT DEFAULT '[]',
            is_approved BOOLEAN DEFAULT 0, approved_at DATETIME,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE content_briefs (
            id VARCHAR(40) PRIMARY KEY, project_id VARCHAR(40) NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            keyword_mapping_id VARCHAR(40) REFERENCES keyword_mappings(id) ON DELETE SET NULL,
            br_code VARCHAR(40) NOT NULL, content_type VARCHAR(32) DEFAULT 'ARTICLE', priority VARCHAR(24) DEFAULT 'P1',
            brief_mode VARCHAR(24) DEFAULT 'DRAFT', status VARCHAR(40) DEFAULT 'SERP_NOT_VERIFIED',
            primary_keyword VARCHAR(300) NOT NULL, secondary_keywords_json TEXT DEFAULT '[]',
            metrics_json TEXT DEFAULT '{{}}', proposed_url VARCHAR(300) DEFAULT '', target_audience TEXT DEFAULT '',
            search_intent_status VARCHAR(40) DEFAULT 'ASSUMED', search_intent_summary TEXT DEFAULT '',
            article_goal TEXT DEFAULT '', seo_title VARCHAR(300) DEFAULT '', h1 VARCHAR(300) DEFAULT '',
            meta_description TEXT DEFAULT '', cta TEXT DEFAULT '', internal_links_json TEXT DEFAULT '[]',
            outline_json TEXT DEFAULT '[]', seo_checklist_json TEXT DEFAULT '[]', writing_strategy_json TEXT DEFAULT '{{}}',
            version INTEGER DEFAULT 1, created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE exports (
            id VARCHAR(40) PRIMARY KEY, project_id VARCHAR(40) NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            export_format VARCHAR(24) NOT NULL, filename VARCHAR(255) NOT NULL, stored_path VARCHAR(500) NOT NULL,
            brief_mode VARCHAR(24) DEFAULT 'DRAFT', created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO projects (id, code, name, primary_keyword_original, primary_keyword_current, business_goal, target_audience)
        VALUES ('prj_target', '{project_code}', 'Target DB Project', 'kế toán nội bộ', 'kế toán nội bộ', 'Lead', 'HR');
        """
    )
    conn.commit()
    conn.close()


def test_b01_b03_b04_b05_b06_effective_database_url_backup_and_downgrade_rejection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """
    B01: FINZ_DATABASE_URL points to custom path X != settings.resolved_db_path Y -> Alembic MUST back up X, NEVER Y!
    B03: Backup failure aborts migration BEFORE schema mutation.
    B04: No pending migration -> no redundant backup.
    B05: Relative path, path with spaces, and Windows URL parsing unit checks; :memory:/non-sqlite fail closed.
    B06: Fresh new nonexistent SQLite DB bootstraps cleanly without creating a fake empty backup.
    P1-E: Unsupported downgrade (0002 / 0003 -> 0001) raises explicit error and leaves schema/version/rows intact!
    """
    from app import config as cfg_mod
    from app import db as db_mod

    # B05 URL resolution checks (POSIX spaces, relative, Windows drive path, :memory:, postgres)
    spaced_dir = tmp_path / "dir with spaces"
    spaced_dir.mkdir()
    spaced_db = spaced_dir / "custom target.sqlite3"
    assert db_mod.resolve_sqlite_db_path(f"sqlite:///{spaced_db}") == spaced_db
    rel_resolved = db_mod.resolve_sqlite_db_path("sqlite:///relative_dir/finz.sqlite3")
    assert rel_resolved.name == "finz.sqlite3"
    win_resolved = db_mod.resolve_sqlite_db_path("sqlite:///C:/Users/SEO User/finz.sqlite3", platform_name="nt")
    assert str(win_resolved).replace("\\", "/").endswith("C:/Users/SEO User/finz.sqlite3")
    with pytest.raises(BackupError):
        db_mod.resolve_sqlite_db_path("sqlite:///:memory:")
    with pytest.raises(BackupError):
        db_mod.resolve_sqlite_db_path("postgresql://user:pass@localhost/finz")

    # B01: Custom FINZ_DATABASE_URL (X) != settings.resolved_db_path (Y)
    db_x = spaced_db
    db_y = tmp_path / "wrong_default_y.sqlite3"
    backups_dir = tmp_path / "backups"
    _build_legacy_0001_db(db_x, project_code="CUSTOM_X")
    _build_legacy_0001_db(db_y, project_code="WRONG_Y")

    monkeypatch.setattr(cfg_mod.settings, "data_dir", tmp_path)
    monkeypatch.setattr(cfg_mod.settings, "db_path", db_y)  # Points to Y!
    monkeypatch.setenv("FINZ_DATABASE_URL", f"sqlite:///{db_x}")  # Effective target is X!

    alembic_cfg = Config(str(API_DIR / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(API_DIR / "alembic"))

    # B03: Inject backup failure -> migration MUST abort BEFORE altering db_x schema!
    import os as _os

    def _boom_replace(_s, _d):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(_os, "replace", _boom_replace)
    with pytest.raises(BackupError):
        command.upgrade(alembic_cfg, "head")
    monkeypatch.undo()

    # Re-apply settings/env after undo
    monkeypatch.setattr(cfg_mod.settings, "data_dir", tmp_path)
    monkeypatch.setattr(cfg_mod.settings, "db_path", db_y)
    monkeypatch.setenv("FINZ_DATABASE_URL", f"sqlite:///{db_x}")

    # Confirm db_x is STILL at 0001_initial_schema after failed backup!
    conn_chk = sqlite3.connect(str(db_x))
    assert conn_chk.execute("SELECT version_num FROM alembic_version").fetchone() == ("0001_initial_schema",)
    conn_chk.close()

    # Now run real upgrade head -> MUST back up X (containing CUSTOM_X, NOT WRONG_Y)!
    command.upgrade(alembic_cfg, "head")
    backup_files = sorted(backups_dir.glob("*.sqlite3"))
    assert len(backup_files) == 1
    bconn = sqlite3.connect(str(backup_files[0]))
    backed_code = bconn.execute("SELECT code FROM projects WHERE id='prj_target'").fetchone()[0]
    bconn.close()
    assert backed_code == "CUSTOM_X"  # Proves X was backed up, NEVER Y!

    ok, errs = verify_sqlite_integrity(db_x)
    assert ok is True and errs == []

    # B04: Re-running upgrade head produces ZERO redundant backups
    command.upgrade(alembic_cfg, "head")
    assert len(list(backups_dir.glob("*.sqlite3"))) == 1

    # P1-E: Attempting downgrade to 0001 MUST fail nonzero/raise and keep version & data intact!
    conn_before_dg = sqlite3.connect(str(db_x))
    ver_before_dg = conn_before_dg.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    conn_before_dg.close()
    with pytest.raises(RuntimeError, match="FINZ_UNSUPPORTED_DOWNGRADE"):
        command.downgrade(alembic_cfg, "0001_initial_schema")

    conn_after_dg = sqlite3.connect(str(db_x))
    assert conn_after_dg.execute("SELECT version_num FROM alembic_version").fetchone()[0] == ver_before_dg
    assert conn_after_dg.execute("SELECT code FROM projects WHERE id='prj_target'").fetchone()[0] == "CUSTOM_X"
    conn_after_dg.close()
    ok_dg, errs_dg = verify_sqlite_integrity(db_x)
    assert ok_dg is True and errs_dg == []

    # B06: Fresh nonexistent DB bootstraps cleanly WITHOUT creating a bogus backup of empty file
    fresh_dir = tmp_path / "fresh_case"
    fresh_dir.mkdir()
    fresh_db = fresh_dir / "brand_new.sqlite3"
    monkeypatch.setattr(cfg_mod.settings, "data_dir", fresh_dir)
    monkeypatch.setattr(cfg_mod.settings, "db_path", fresh_db)
    monkeypatch.setenv("FINZ_DATABASE_URL", f"sqlite:///{fresh_db}")
    command.upgrade(alembic_cfg, "head")
    assert fresh_db.exists()
    assert list((fresh_dir / "backups").glob("*.sqlite3")) == []


def test_i01_to_i08_real_f2_integrity_manifest_tamper_detection_and_legacy_unverified(client):
    """
    I01: Valid upload & all rows intact -> F2 PASSED with verified manifest.
    I02: Tamper stored CSV bytes between preview & confirm -> rejected, DB unchanged.
    I03: Mutate 6th or last EvidenceRow raw/normalized field -> F2 FAILED (closes first-5-only gap!).
    I04/I05: Tamper stored file bytes on disk or delete file -> F2 FAILED.
    I08: Legacy batch without manifest_sha256 -> classified UNVERIFIED (NOT falsely PASSED!).
    """
    tc, _ = client
    from app import db as db_mod

    pid = tc.post(
        "/api/v1/projects",
        json={
            "code": "I01",
            "name": "F2 Integrity Project",
            "topic_pillar_code": "I01",
            "topic_pillar_name": "Integrity",
            "primary_keyword": "keyword 1",
            "business_goal": "Lead",
            "target_audience": "HR",
            "market": "VN",
        },
    ).json()["project"]["id"]

    # Build 12-row CSV (well beyond first 5 rows!)
    rows_csv = ["Keyword,Volume,KD,Intent"]
    for i in range(1, 13):
        rows_csv.append(f"keyword {i},{100 * i},{10 + i},Informational")
    csv_text = "\n".join(rows_csv) + "\n"

    # I02: Preview, then tamper file on disk BEFORE confirm -> MUST reject & write 0 batches!
    prev_tamper = tc.post(
        f"/api/v1/projects/{pid}/imports/preview",
        data={"report_type": "KEYWORD_OVERVIEW", "locale": "en-US"},
        files={"file": ("tamper_before_confirm.csv", csv_text.encode("utf-8"), "text/csv")},
    ).json()

    db = db_mod.SessionLocal()
    try:
        upl = db.get(FileUpload, prev_tamper["upload_id"])
        Path(upl.stored_path).write_bytes((csv_text + "injected,9999,1,Commercial\n").encode("utf-8"))
    finally:
        db.close()

    r_tamper = tc.post(
        f"/api/v1/projects/{pid}/imports/confirm",
        json={
            "upload_id": prev_tamper["upload_id"],
            "report_type": "KEYWORD_OVERVIEW",
            "market": "VN",
            "locale": "en-US",
            "column_mapping": prev_tamper["suggested_mapping"],
        },
    )
    assert r_tamper.status_code == 409
    assert r_tamper.json()["detail"]["code"] == "UPLOAD_TAMPERED_BETWEEN_PREVIEW_AND_CONFIRM"
    assert tc.get(f"/api/v1/projects/{pid}/evidence").json()["batches"] == []

    # I01: Normal upload & confirm -> F2 PASSED with manifest_sha256
    prev_ok = tc.post(
        f"/api/v1/projects/{pid}/imports/preview",
        data={"report_type": "KEYWORD_OVERVIEW", "locale": "en-US"},
        files={"file": ("good_12.csv", csv_text.encode("utf-8"), "text/csv")},
    ).json()
    conf_ok = tc.post(
        f"/api/v1/projects/{pid}/imports/confirm",
        json={
            "upload_id": prev_ok["upload_id"],
            "report_type": "KEYWORD_OVERVIEW",
            "market": "VN",
            "locale": "en-US",
            "column_mapping": prev_ok["suggested_mapping"],
        },
    )
    assert conf_ok.status_code == 200
    batch_id = conf_ok.json()["batch_id"]
    gates_ok = {g["gate_code"]: g for g in tc.post(f"/api/v1/projects/{pid}/evidence/validate").json()["quality_gates"]}
    assert gates_ok["F2"]["status"] == "PASSED"

    # I03: Mutate the 10th (last/beyond-first-5) EvidenceRow normalized volume -> F2 MUST FAIL!
    db = db_mod.SessionLocal()
    try:
        row10 = (
            db.query(EvidenceRow)
            .filter(EvidenceRow.batch_id == batch_id, EvidenceRow.keyword_normalized == "keyword 10")
            .one()
        )
        orig_vol = row10.volume
        row10.volume = 999999
        db.commit()
    finally:
        db.close()

    gates_mut_row = {g["gate_code"]: g for g in tc.post(f"/api/v1/projects/{pid}/evidence/validate").json()["quality_gates"]}
    assert gates_mut_row["F2"]["status"] == "FAILED"

    # Restore row10 volume -> F2 PASSED again
    db = db_mod.SessionLocal()
    try:
        row10 = (
            db.query(EvidenceRow)
            .filter(EvidenceRow.batch_id == batch_id, EvidenceRow.keyword_normalized == "keyword 10")
            .one()
        )
        row10.volume = orig_vol
        db.commit()
        upl_ok = db.get(FileUpload, prev_ok["upload_id"])
        stored_ok_path = Path(upl_ok.stored_path)
        orig_disk_bytes = stored_ok_path.read_bytes()
    finally:
        db.close()

    assert {g["gate_code"]: g for g in tc.post(f"/api/v1/projects/{pid}/evidence/validate").json()["quality_gates"]}["F2"]["status"] == "PASSED"

    # I04: Tamper stored source file on disk -> F2 MUST FAIL!
    stored_ok_path.write_bytes(orig_disk_bytes + b"\n")
    gates_tampered_disk = {g["gate_code"]: g for g in tc.post(f"/api/v1/projects/{pid}/evidence/validate").json()["quality_gates"]}
    assert gates_tampered_disk["F2"]["status"] == "FAILED"

    # I05: Delete source file on disk -> F2 MUST FAIL!
    stored_ok_path.unlink()
    gates_missing_disk = {g["gate_code"]: g for g in tc.post(f"/api/v1/projects/{pid}/evidence/validate").json()["quality_gates"]}
    assert gates_missing_disk["F2"]["status"] == "FAILED"

    # Restore disk bytes, then simulate I08: legacy pre-0003 batch with manifest_sha256=None -> UNVERIFIED (NOT PASSED!)
    stored_ok_path.write_bytes(orig_disk_bytes)
    db = db_mod.SessionLocal()
    try:
        bat = db.get(ResearchBatch, batch_id)
        bat.manifest_sha256 = None
        bat.integrity_status = "UNVERIFIED"
        db.commit()
    finally:
        db.close()

    gates_legacy = {g["gate_code"]: g for g in tc.post(f"/api/v1/projects/{pid}/evidence/validate").json()["quality_gates"]}
    assert gates_legacy["F2"]["status"] != "PASSED"
    assert gates_legacy["F2"]["details"]["batch_statuses"][batch_id] == "UNVERIFIED"


def test_b02_i06_i07_wal_custom_url_263_rows_dedup_null_vs_zero_and_cross_project_export(client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """
    B02: Active WAL writer with custom FINZ_DATABASE_URL yields readable snapshot with exact row parity.
    I06: Duplicate rows never summed, null != 0 preserved, strict project isolation (incl. cross-project export denial).
    I07: 263+ rows processed completely with full F2 manifest verification.
    """
    tc, _ = client
    from app import config as cfg_mod

    # B02: Active WAL on custom FINZ_DATABASE_URL (no explicit source_path passed!)
    wal_db = tmp_path / "custom wal live.sqlite3"
    bdir = tmp_path / "custom_backups"
    conn = sqlite3.connect(str(wal_db))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, label TEXT)")
    conn.execute("INSERT INTO items VALUES (1, 'alpha'), (2, 'beta')")
    conn.commit()
    writer = sqlite3.connect(str(wal_db))
    writer.execute("INSERT INTO items VALUES (3, 'gamma_wal')")
    writer.commit()

    monkeypatch.setenv("FINZ_DATABASE_URL", f"sqlite:///{wal_db}")
    monkeypatch.setattr(cfg_mod.settings, "backups_dir" if False else "data_dir", tmp_path)
    bp = backup_database(reason="b02_wal", backups_dir=bdir, verify=True)
    assert bp is not None and bp.exists()
    rconn = sqlite3.connect(str(bp))
    assert rconn.execute("SELECT id, label FROM items ORDER BY id").fetchall() == [
        (1, "alpha"), (2, "beta"), (3, "gamma_wal")
    ]
    rconn.close()
    writer.close()
    conn.close()

    # I06 + I07: 265-row Semrush CSV with explicit 0 volume, NULL volume, and duplicate keyword (never summed!)
    pid_a = tc.post(
        "/api/v1/projects",
        json={"code": "I06A", "name": "Proj A", "primary_keyword": "kw 001", "business_goal": "G", "target_audience": "A"},
    ).json()["project"]["id"]
    pid_b = tc.post(
        "/api/v1/projects",
        json={"code": "I06B", "name": "Proj B", "primary_keyword": "kw b", "business_goal": "G", "target_audience": "A"},
    ).json()["project"]["id"]

    lines = [
        "Keyword,Volume,KD,Intent",
        "kw zero,0,12,Informational",
        "kw null,,15,Informational",
        "kw dup,500,20,Informational",
        "kw dup,500,20,Informational",
    ]
    for i in range(1, 263):
        lines.append(f"kw {i:03d},{100 + i},{10 + (i % 50)},Informational")
    csv_266 = ("\n".join(lines) + "\n").encode("utf-8")

    prev = tc.post(
        f"/api/v1/projects/{pid_a}/imports/preview",
        data={"report_type": "KEYWORD_OVERVIEW", "locale": "en-US"},
        files={"file": ("rows_266.csv", csv_266, "text/csv")},
    ).json()
    assert prev["total_rows"] == 266
    conf = tc.post(
        f"/api/v1/projects/{pid_a}/imports/confirm",
        json={
            "upload_id": prev["upload_id"],
            "report_type": "KEYWORD_OVERVIEW",
            "market": "VN",
            "locale": "en-US",
            "column_mapping": prev["suggested_mapping"],
        },
    )
    assert conf.status_code == 200
    cbody = conf.json()
    assert cbody["total_raw_rows"] == 266
    assert cbody["total_normalized_rows"] == 265
    assert cbody["duplicate_rows_detected"] == 1
    assert cbody["integrity_status"] == "VERIFIED"

    ev_a = tc.get(f"/api/v1/projects/{pid_a}/evidence?limit=300").json()
    ev_b = tc.get(f"/api/v1/projects/{pid_b}/evidence?limit=300").json()
    assert ev_b["total_evidence_rows"] == 0  # Project isolation!
    by_kw = {r["keyword"]: r for r in ev_a["rows"] if not r["is_duplicate"]}
    assert by_kw["kw zero"]["volume"] == 0  # Explicit 0 preserved
    assert by_kw["kw null"]["volume"] is None  # NULL distinct from 0
    assert by_kw["kw dup"]["volume"] == 500  # Duplicate NOT summed to 1000!
    f2_gate = next(g for g in ev_a["quality_gates"] if g["gate_code"] == "F2")
    assert f2_gate["status"] == "PASSED"

    # Cross-project export isolation
    tc.post(f"/api/v1/projects/{pid_a}/mapping/preview")
    tc.post(f"/api/v1/projects/{pid_a}/briefs/generate", json={"allow_draft": True})
    exp_a = tc.post(f"/api/v1/projects/{pid_a}/exports/download", json={"format": "json"})
    assert exp_a.status_code == 200
    exp_id = exp_a.headers["X-FinZ-Export-Id"]
    assert tc.get(f"/api/v1/projects/{pid_b}/exports/file/{exp_id}").status_code == 404

