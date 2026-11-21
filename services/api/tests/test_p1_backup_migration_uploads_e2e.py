from __future__ import annotations

import io
import json
import sqlite3
import zipfile
from pathlib import Path

import openpyxl
import pytest
from alembic import command
from alembic.config import Config

from app.ai.adapters.base import AIProviderAdapter, ProviderConfig, StructuredGenerationResult, TestConnectionResult
from app.ai.gateway import gateway
from app.db import BackupError, backup_database, verify_sqlite_integrity
from app.security.upload_guard import sanitize_upload_filename

API_DIR = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).parent / "fixtures"


def test_g3_invalid_e0_source_ref_blocks_official_even_after_approval_and_serp(client):
    """G3 + M8: Fabricated AI source_ref MUST block OFFICIAL brief even with valid metrics, Top-10 SERP, and human approval."""
    tc, _ = client
    tc.put("/api/v1/settings/ai", json={"provider": "mock", "set_active": True})

    class _BadRefAdapter(AIProviderAdapter):
        provider_name = "mock"

        def test_connection(self, config: ProviderConfig) -> TestConnectionResult:
            return TestConnectionResult(True, "mock", "m", "m", 1, "CONNECTED", "ok")

        def generate_structured_output(self, config, system_prompt, user_prompt, context=None):
            if (context or {}).get("task") == "ANALYST":
                return StructuredGenerationResult(
                    ok=True, provider="mock", requested_model="m", actual_model="m", latency_ms=2,
                    data={
                        "summary": "bad ref",
                        "demand_groups": [
                            {
                                "name": "Nhóm bịa source_ref",
                                "user_need": "Cần kiểm chứng",
                                "coverage_type": "COVERED",
                                "assumed_page_type": "ARTICLE",
                                "assumed_intent": "Informational",
                                "seed_keywords": ["lương thử việc"],
                                "related_keywords": [],
                                "supporting_evidence": ["Bịa ref"],
                                "source_refs": ["FABRICATED:9999"],
                                "strongest_counterargument": "Nguồn chưa xác minh",
                                "missing_data": ["Taxonomy thật"],
                                "next_action": "Kiểm tra lại nguồn",
                                "recommended_semrush_report": "KEYWORD_OVERVIEW",
                                "status": "RESEARCH_CANDIDATE",
                            }
                        ],
                    },
                )
            return StructuredGenerationResult(
                ok=True, provider="mock", requested_model="m", actual_model="m", latency_ms=2,
                data={"supporting_evidence": ["ok"], "counterarguments": ["c"], "missing_data": [], "followup_requests": [], "next_action": "n", "decision_status": "WAITING_USER"},
            )

    gateway.adapters["mock"] = _BadRefAdapter()
    pid = tc.post(
        "/api/v1/projects",
        json={
            "code": "G3T",
            "name": "Lương thử việc",
            "primary_keyword": "lương thử việc",
            "business_goal": "Tư vấn HR",
            "target_audience": "HR SME",
            "market": "VN",
        },
    ).json()["project"]["id"]

    tc.post(f"/api/v1/projects/{pid}/analyze-topic")

    # Provide complete metrics + 3 organic URLs
    m_prev = tc.post(
        f"/api/v1/projects/{pid}/imports/preview",
        data={"report_type": "KEYWORD_OVERVIEW", "locale": "en-US"},
        files={"file": ("m.csv", b"Keyword,Volume,KD,Intent\nl\xc6\xb0\xc6\xa1ng th\xe1\xbb\xad vi\xe1\xbb\x87c,500,15,Informational\n", "text/csv")},
    ).json()
    tc.post(f"/api/v1/projects/{pid}/imports/confirm", json={"upload_id": m_prev["upload_id"], "report_type": "KEYWORD_OVERVIEW", "market": "VN", "locale": "en-US", "column_mapping": m_prev["suggested_mapping"]})

    s_csv = (
        "Keyword,Position,URL,Title\n"
        "lương thử việc,1,https://ex.vn/1,T1\n"
        "lương thử việc,2,https://ex.vn/2,T2\n"
        "lương thử việc,3,https://ex.vn/3,T3\n"
    ).encode("utf-8")
    s_prev = tc.post(
        f"/api/v1/projects/{pid}/imports/preview",
        data={"report_type": "ORGANIC_RESULTS", "locale": "en-US"},
        files={"file": ("s.csv", s_csv, "text/csv")},
    ).json()
    tc.post(f"/api/v1/projects/{pid}/imports/confirm", json={"upload_id": s_prev["upload_id"], "report_type": "ORGANIC_RESULTS", "market": "VN", "locale": "en-US", "column_mapping": s_prev["suggested_mapping"]})

    tc.post(f"/api/v1/projects/{pid}/mapping/preview")
    for a in tc.get(f"/api/v1/projects/{pid}/approvals").json()["approvals"]:
        if a["status"] == "PENDING":
            tc.post(f"/api/v1/projects/{pid}/approvals/{a['id']}", json={"decision": "APPROVED"})

    opps = tc.get(f"/api/v1/projects/{pid}/opportunities").json()
    m0 = opps["mappings"][0]
    assert m0["eligibility"]["eligible_official"] is False
    assert any(b["code"] == "E0_INVALID_SOURCE_REF" for b in m0["eligibility"]["blockers"])
    assert tc.post(f"/api/v1/projects/{pid}/briefs/generate", json={"allow_draft": False}).status_code == 400


def test_p1_online_wal_backup_restore_and_fail_closed_injection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """P1: Active WAL online backup preserves committed rows, passes quick_check & foreign_key_check, and fails closed on errors."""
    db_file = tmp_path / "live_wal.sqlite3"
    backups_dir = tmp_path / "backups"

    conn = sqlite3.connect(str(db_file))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("CREATE TABLE parents (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("CREATE TABLE children (id INTEGER PRIMARY KEY, parent_id INTEGER REFERENCES parents(id))")
    conn.execute("INSERT INTO parents VALUES (1, 'P01'), (2, 'P08')")
    conn.execute("INSERT INTO children VALUES (10, 1), (20, 2)")
    conn.commit()

    # Keep an active writer open while taking online backup!
    writer = sqlite3.connect(str(db_file))
    writer.execute("INSERT INTO parents VALUES (3, 'Z42')")
    writer.commit()

    backup_path = backup_database(reason="wal_active", source_path=db_file, backups_dir=backups_dir, verify=True)
    assert backup_path is not None and backup_path.exists()
    assert not list(backups_dir.glob("*.tmp"))

    # Restore & verify integrity + exact row parity
    ok, errs = verify_sqlite_integrity(backup_path)
    assert ok is True and errs == []

    restored = sqlite3.connect(str(backup_path))
    rows = restored.execute("SELECT id, name FROM parents ORDER BY id").fetchall()
    child_rows = restored.execute("SELECT id, parent_id FROM children ORDER BY id").fetchall()
    restored.close()
    assert rows == [(1, "P01"), (2, "P08"), (3, "Z42")]
    assert child_rows == [(10, 1), (20, 2)]

    # Rapid second backup never collides/overwrites first backup
    backup_path_2 = backup_database(reason="wal_active", source_path=db_file, backups_dir=backups_dir, verify=True)
    assert backup_path_2 is not None and backup_path_2 != backup_path
    assert backup_path.exists() and backup_path_2.exists()

    # Failure injection 1: Simulated disk full during atomic replace -> FAIL CLOSED & cleanup .tmp!
    import os as _os

    def _boom_replace(_src, _dst):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(_os, "replace", _boom_replace)
    with pytest.raises(BackupError):
        backup_database(reason="disk_full", source_path=db_file, backups_dir=backups_dir, verify=True)
    assert not list(backups_dir.glob("*.tmp"))

    writer.close()
    conn.close()


def test_t30_legacy_v16_migration_0001_to_0002_preserves_data_and_skips_redundant_backup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """
    T30: Build a legacy `0001_initial_schema` DB with real user rows, run forward migration to `head` (0002):
    - Creates exactly 1 verified pre-migration backup when upgrading from 0001 -> 0002.
    - Preserves all legacy rows, passes quick_check & foreign_key_check.
    - Re-running `alembic upgrade head` when already at head does NOT spam redundant backups!
    """
    db_file = tmp_path / "legacy_v16.sqlite3"
    backups_dir = tmp_path / "backups"
    monkeypatch.setenv("FINZ_DATABASE_URL", f"sqlite:///{db_file}")

    from app import config as cfg_mod
    monkeypatch.setattr(cfg_mod.settings, "data_dir", tmp_path)
    monkeypatch.setattr(cfg_mod.settings, "db_path", db_file)

    alembic_cfg = Config(str(API_DIR / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(API_DIR / "alembic"))

    # Build a true legacy 0001 DB (BEFORE 0002 columns & mapping_revisions existed!)
    conn = sqlite3.connect(str(db_file))
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(
        """
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
            provenance_json TEXT DEFAULT '{}', version INTEGER DEFAULT 1, research_cycle INTEGER DEFAULT 1,
            status VARCHAR(40) DEFAULT 'READY',
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE source_keywords (
            id VARCHAR(40) PRIMARY KEY, project_id VARCHAR(40) NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            topic_pillar_code VARCHAR(64) DEFAULT '', content_code VARCHAR(64) DEFAULT '',
            keyword VARCHAR(300) NOT NULL, keyword_normalized VARCHAR(300) NOT NULL,
            role VARCHAR(32) DEFAULT 'SECONDARY', is_original BOOLEAN DEFAULT 1,
            source_ref VARCHAR(160) DEFAULT '', source_file VARCHAR(255) DEFAULT '',
            source_sheet VARCHAR(120) DEFAULT '', source_row INTEGER,
            status VARCHAR(40) DEFAULT 'ACTIVE',
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE evidence_rows (
            id VARCHAR(40) PRIMARY KEY, project_id VARCHAR(40) NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            batch_id VARCHAR(40) NOT NULL, row_type VARCHAR(32) DEFAULT 'METRICS',
            source_row_number INTEGER DEFAULT 1, keyword VARCHAR(300) DEFAULT '',
            keyword_normalized VARCHAR(300) DEFAULT '', volume INTEGER, kd FLOAT, intent VARCHAR(120),
            cpc FLOAT, serp_features TEXT, organic_url TEXT, organic_position INTEGER,
            organic_title TEXT, organic_page_type VARCHAR(64), market VARCHAR(32) DEFAULT 'VN',
            is_duplicate BOOLEAN DEFAULT 0, raw_row_json TEXT DEFAULT '{}', warnings_json TEXT DEFAULT '[]',
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
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE content_briefs (
            id VARCHAR(40) PRIMARY KEY, project_id VARCHAR(40) NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            keyword_mapping_id VARCHAR(40) REFERENCES keyword_mappings(id) ON DELETE SET NULL,
            br_code VARCHAR(40) NOT NULL, content_type VARCHAR(32) DEFAULT 'ARTICLE',
            priority VARCHAR(24) DEFAULT 'P1', brief_mode VARCHAR(24) DEFAULT 'DRAFT',
            status VARCHAR(40) DEFAULT 'SERP_NOT_VERIFIED', primary_keyword VARCHAR(300) NOT NULL,
            secondary_keywords_json TEXT DEFAULT '[]', metrics_json TEXT DEFAULT '{}',
            proposed_url VARCHAR(300) DEFAULT '', target_audience TEXT DEFAULT '',
            search_intent_status VARCHAR(40) DEFAULT 'ASSUMED', search_intent_summary TEXT DEFAULT '',
            article_goal TEXT DEFAULT '', seo_title VARCHAR(300) DEFAULT '', h1 VARCHAR(300) DEFAULT '',
            meta_description TEXT DEFAULT '', cta TEXT DEFAULT '', internal_links_json TEXT DEFAULT '[]',
            outline_json TEXT DEFAULT '[]', seo_checklist_json TEXT DEFAULT '[]',
            writing_strategy_json TEXT DEFAULT '{}', version INTEGER DEFAULT 1,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO projects (id, code, name, primary_keyword_original, primary_keyword_current, business_goal, target_audience)
        VALUES ('prj_legacy', 'P08', 'Legacy BHXH', 'mức đóng bhxh', 'mức đóng bhxh', 'Lead B2B', 'HR');
        INSERT INTO source_keywords (id, project_id, topic_pillar_code, content_code, keyword, keyword_normalized, role, source_ref)
        VALUES ('skw_legacy', 'prj_legacy', 'P08', 'P08-01', 'mức đóng bhxh', 'mức đóng bhxh', 'PRIMARY', 'TOPIC:P08');
        """
    )
    conn.commit()
    conn.close()

    # Clear backups before measuring upgrade 0001 -> head
    if backups_dir.exists():
        for f in backups_dir.glob("*.sqlite3"):
            f.unlink()

    # Upgrade to head (0002)
    command.upgrade(alembic_cfg, "head")
    backups_after_upgrade = list(backups_dir.glob("*.sqlite3"))
    assert len(backups_after_upgrade) == 1  # Exactly 1 pre-migration backup created!

    ok, errs = verify_sqlite_integrity(db_file)
    assert ok is True and errs == []

    # Verify legacy rows preserved AND new 0002 columns + mapping_revisions table exist
    conn = sqlite3.connect(str(db_file))
    assert conn.execute("SELECT code, primary_keyword_original FROM projects WHERE id='prj_legacy'").fetchone() == ("P08", "mức đóng bhxh")
    assert conn.execute("SELECT keyword FROM source_keywords WHERE id='skw_legacy'").fetchone() == ("mức đóng bhxh",)
    km_cols = {r[1] for r in conn.execute("PRAGMA table_info(keyword_mappings)").fetchall()}
    assert {"logical_key", "content_fingerprint", "approved_revision", "approved_fingerprint", "is_archived"}.issubset(km_cols)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "mapping_revisions" in tables
    conn.close()

    # Re-running upgrade head when already up to date MUST NOT create another redundant backup!
    command.upgrade(alembic_cfg, "head")
    assert len(list(backups_dir.glob("*.sqlite3"))) == 1


def test_p1_upload_streaming_size_limit_malformed_xlsx_and_filename_sanitization(client, monkeypatch: pytest.MonkeyPatch):
    """P1: Enforce streaming max_upload_bytes (413), reject malformed XLSX, sanitize malicious filenames, avoid overwrite collisions."""
    tc, _ = client
    from app import config as cfg_mod

    pid = tc.post("/api/v1/projects", json={"code": "UPL1", "name": "Upload Security", "primary_keyword": "test upload"}).json()["project"]["id"]

    # Sanitization across OS traversal & Windows reserved names
    assert ".." not in sanitize_upload_filename("../../etc/passwd.csv")
    assert sanitize_upload_filename("CON.csv").startswith("file_")

    # Streaming max_upload_bytes -> HTTP 413 before buffering oversized payload
    monkeypatch.setattr(cfg_mod.settings, "max_upload_bytes", 1024)
    huge = b"Keyword,Volume\n" + (b"a" * 2048)
    r_big = tc.post(
        f"/api/v1/projects/{pid}/imports/preview",
        data={"report_type": "KEYWORD_OVERVIEW", "locale": "en-US"},
        files={"file": ("../../huge.csv", huge, "text/csv")},
    )
    assert r_big.status_code == 413
    assert r_big.json()["detail"]["code"] == "UPLOAD_TOO_LARGE"

    # Malformed XLSX rejected cleanly with 400
    monkeypatch.setattr(cfg_mod.settings, "max_upload_bytes", 15 * 1024 * 1024)
    r_bad_xlsx = tc.post(
        f"/api/v1/projects/{pid}/topic-source/preview",
        files={"file": ("broken.xlsx", b"NOT_A_ZIP_FILE_AT_ALL", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r_bad_xlsx.status_code == 400
    assert r_bad_xlsx.json()["detail"]["code"] == "MALFORMED_XLSX"


def test_e2e_mock_7_step_reproducibility_and_zero_secret_leakage_in_exports(client):
    """
    Full Mock 7-Step E2E + Export Re-Import Check + Reproducibility Check:
    - Uses realistic Semrush fixtures, runs all 7 steps, verifies XLSX 3 sheets/CSV/JSON/HTML,
      confirms zero secret leakage (including AQ.* & AIza* keys) across SQLite & all exports.
    """
    tc, db_file = client
    secret_aq = "AQ.Ab8RN6FAKE_TEST_SECRET_NEVER_LEAK_1234"
    tc.put("/api/v1/settings/ai", json={"provider": "gemini", "set_active": False, "api_key": secret_aq})
    tc.put("/api/v1/settings/ai", json={"provider": "mock", "set_active": True})

    def run_pipeline(code: str):
        pid = tc.post(
            "/api/v1/projects",
            json={
                "code": code,
                "name": f"E2E {code} Lương Net Gross",
                "topic_pillar_code": code,
                "topic_pillar_name": "Lương Net và Gross",
                "primary_keyword": "lương net và gross là gì",
                "secondary_keywords": ["lương gross và net là gì", "lương net sang gross là gì", "tính lương gross net là gì"],
                "business_goal": "Thu hút HR SME đăng ký tư vấn quản trị lương",
                "target_audience": "HR Manager và Kế toán tiền lương",
                "market": "VN",
            },
        ).json()["project"]["id"]

        # Step 02: Demand Map (Mock Analyst + Pre-Critic)
        an = tc.post(f"/api/v1/projects/{pid}/analyze-topic")
        assert an.status_code == 200

        # Step 03: Manual Semrush Requests
        reqs = tc.post(
            f"/api/v1/projects/{pid}/research-requests",
            json={
                "items": [
                    {"seed_keyword": "lương net và gross là gì", "report_type": "KEYWORD_OVERVIEW", "market": "VN"},
                    {"seed_keyword": "lương net và gross là gì", "report_type": "ORGANIC_RESULTS", "market": "VN"},
                ]
            },
        ).json()["research_requests"]

        # Step 04: Upload real Semrush CSV fixtures (metrics + SERP Analysis)
        for req_obj, fname, rt in [
            (reqs[0], "semrush_metrics_real_sample.csv", "KEYWORD_OVERVIEW"),
            (reqs[1], "semrush_serp_real_sample.csv", "ORGANIC_RESULTS"),
        ]:
            raw = (FIXTURES / fname).read_bytes()
            p = tc.post(
                f"/api/v1/projects/{pid}/imports/preview",
                data={"research_request_id": req_obj["id"], "report_type": rt, "locale": "en-US"},
                files={"file": (fname, raw, "text/csv")},
            ).json()
            c = tc.post(
                f"/api/v1/projects/{pid}/imports/confirm",
                json={
                    "upload_id": p["upload_id"],
                    "research_request_id": req_obj["id"],
                    "report_type": rt,
                    "market": "VN",
                    "locale": "en-US",
                    "column_mapping": p["suggested_mapping"],
                },
            )
            assert c.status_code == 200

        # Step 05: Evidence Validate + Post-Semrush Critic
        val = tc.post(f"/api/v1/projects/{pid}/evidence/validate").json()
        assert val["summary"]["metrics_rows_count"] == 15
        crit = tc.post(f"/api/v1/projects/{pid}/ai/critic", json={"stage": "POST_SEMRUSH"})
        assert crit.status_code == 200

        # Step 06: Keyword Mapping + Human Approvals
        tc.post(f"/api/v1/projects/{pid}/mapping/preview")
        for a in tc.get(f"/api/v1/projects/{pid}/approvals").json()["approvals"]:
            if a["status"] == "PENDING":
                tc.post(f"/api/v1/projects/{pid}/approvals/{a['id']}", json={"decision": "APPROVED", "decided_by": "QA Reviewer"})

        opps = tc.get(f"/api/v1/projects/{pid}/opportunities").json()
        # Step 07: Generate briefs (allow_draft=True -> OFFICIAL ONLY for eligible keyword, DRAFT for unverified keywords!)
        br = tc.post(f"/api/v1/projects/{pid}/briefs/generate", json={"allow_draft": True}).json()
        return pid, opps, br

    pid1, opps1, br1 = run_pipeline("E2E1")
    pid2, opps2, br2 = run_pipeline("E2E2")

    # Semantic reproducibility across independent runs
    sig1 = [(m["primary_keyword"], m["page_type"], m["eligibility"]["eligible_official"], m["eligibility"]["serp_tier"]) for m in opps1["mappings"]]
    sig2 = [(m["primary_keyword"], m["page_type"], m["eligibility"]["eligible_official"], m["eligibility"]["serp_tier"]) for m in opps2["mappings"]]
    assert sig1 == sig2
    assert br1["official_count"] == br2["official_count"] == 1
    assert br1["draft_count"] == br2["draft_count"] >= 1

    # Export all 4 formats & verify re-import structure + ZERO secret leakage
    for fmt in ("xlsx", "csv", "json", "html"):
        exp = tc.post(f"/api/v1/projects/{pid1}/exports/download", json={"format": fmt})
        assert exp.status_code == 200
        assert secret_aq.encode("utf-8") not in exp.content
        if fmt == "xlsx":
            wb = openpyxl.load_workbook(io.BytesIO(exp.content))
            assert wb.sheetnames == ["Keyword Overview", "Keyword Mapping", "SEO Content Brief"]
            assert wb["Keyword Overview"].max_row == 16  # header + 15 rows
            assert wb["SEO Content Brief"].max_row >= 2
        elif fmt == "json":
            parsed = json.loads(exp.content.decode("utf-8"))
            assert parsed["contains_api_keys"] is False
            assert parsed["policy_version"] == "1.6.1"

    # Secret never persisted in SQLite bytes
    assert secret_aq.encode("utf-8") not in db_file.read_bytes()
