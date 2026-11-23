# FinZ SEO Workbench — Development Log

## 2026-11-21 — Full Rebuild V1.6 on New Remote (`quocan050302/Finz`)

### Implemented
- **Root Launcher**: Created `package.json` and `scripts/dev.mjs` so a single `npm run dev` bootstraps Python venv, runs Alembic SQLite migrations (with pre-migration backup), installs frontend deps if needed, and starts FastAPI (`127.0.0.1:8000`) + Next.js (`127.0.0.1:3000`).
- **Backend (`services/api`)**:
  - SQLAlchemy + Alembic initial schema (`0001_initial_schema`) covering all 25 entities (`projects`, `taxonomy_pillars`, `topic_pillars`, `content_codes`, `source_keywords`, `project_snapshots`, `project_events`, `workflow_steps`, `demand_groups`, `keyword_candidates`, `ai_runs`, `critiques`, `research_requests`, `file_uploads`, `research_batches`, `evidence_rows`, `keyword_evidence_links`, `quality_gates`, `approvals`, `keyword_mappings`, `article_opportunities`, `content_briefs`, `brief_versions`, `exports`, `ai_provider_settings`).
  - Security layer: OS Keychain / env secret store (never plaintext in SQLite) + SSRF host allowlist for OpenAI, Gemini, and Claude.
  - AI Provider Gateway: Native adapters for **Google Gemini** (with auto-latest model discovery via `/v1beta/models` + **automatic model downgrade after 3 consecutive errors**), **OpenAI**, **Anthropic Claude**, and **Mock Provider**.
  - SEO Domain Engine: Dynamic-header XLSX/CSV taxonomy parser (row 4 Topic Pillar + row 1 Keywords), Semrush parser (`vi-VN`/`en-US` locale numbers, `null != 0`, dedup without summing Volume, full-file processing >200 rows, separate `ORGANIC_RESULTS` parser), Quality Gates (`F0`–`F7`, `E0`–`E2`), Keyword Mapping + Approvals, Content Brief Generator (13 writing formulas + 16 whole-article engagement tactics), and XLSX (3 sheets) / CSV / JSON / Printable HTML exporter.
- **Frontend (`apps/web`, Dark Mode)**:
  - Complete Dark Mode UI (`<meta name="color-scheme" content="dark">`, `:root color-scheme: dark`, native `<dialog>` completion popup with 350ms checkmark & safe auto-navigation cancellation, container-query responsive tables, `:user-invalid` ARIA sync).
  - Implemented all screens: Dashboard (`/`), Projects (`/projects`), Steps 01–07 (`/steps/01-topic` .. `/steps/07-brief`), Approvals (`/approvals`), System Logs (`/logs`), and AI Settings (`/settings/ai` with Gemini fallback ladder UI).

### Verification
- Backend `alembic upgrade head` & `pytest` acceptance suite (`T01`–`T26` + Gemini 3-error auto-downgrade).
- Frontend TypeScript typecheck (`tsc --noEmit`) & Next.js production build (`next build`).
- End-to-end live verification of `npm run dev` serving both FastAPI & Next.js.

### Known Limits
- Local single-user SQLite deployment (`127.0.0.1` only).
- Real paid LLM calls are never triggered automatically; live verification requires user-supplied API keys in `/settings/ai`.

## 2026-11-21 — FINZ-16-QA-R1 (Quality Gates, SERP Provenance, Revision-Safe Approvals & End-to-End QA)

- **Branch:** `fix/v1-6-quality-gates-mapping-qa` (base `60448cc667113b8bbd7e2ac5a0449c836974cbaf`, final source commit `74b81763e08c39a79de862cb86623669d702ffc8`, `main` unchanged).
- **Implemented:**
  - Single authoritative pre-generation eligibility policy & Phase 2 post-generation brief quality (`services/api/app/domain/eligibility_policy.py`, policy `v1.6.1`).
  - Per-keyword, per-market SERP provenance supporting real Semrush SERP Analysis CSVs (`AI Overview` vs `Organic`, `SERP_NOT_VERIFIED` / `PARTIAL_SERP_EVIDENCE` / `SERP_VERIFIED` / `TOP_10_VERIFIED`).
  - Non-destructive `KeywordMapping` revisions, `MappingRevision` audit table, canonical SHA-256 content fingerprints, `409 Conflict` stale/replayed approval rejection, and automatic stale downgrading of outdated `OFFICIAL` briefs (forward migration `0002_revision_fingerprint_and_serp_provenance`).
  - Online SQLite WAL backup via `sqlite3.Connection.backup()` + `quick_check` / `foreign_key_check` fail-closed verification, fixed SQLAlchemy 2.0 implicit transaction handling in `alembic/env.py`, and streaming chunked upload guard (`upload_guard.py`).
  - Frontend per-mapping blockers, `"Cần duyệt lại"` state, strict `OFFICIAL` button gating, cross-project async race guards, and `CompletionPopup` first-project creation fix.
- **Verification:**
  - Serial & bounded-parallel (4 workers) `pytest`: 20/20 PASS (`serial_parallel_parity=true`).
  - Real headless Chrome CDP E2E (`scripts/qa-browser-t27-t29.mjs`): T27, T28, T29 (320/768/1440px), UI OFFICIAL gating PASS.
  - Legacy `0001` → `0002` migration on temp copy of local DB: PASS (`quick_check=ok`, `foreign_key_check=0`).
  - `tsc --noEmit` & `next build`: PASS.
  - Detailed QA report: `docs/qa-runs/FINZ-16-QA-R1-20261121-1953/`.

## 2026-11-21 — FINZ-16-QA-R2 (Coherent SERP Snapshots, Auto Freshness Invalidation, Effective DB Backup, F2 Manifest, Downgrade Reject & Real CI)

- **Branch:** `fix/v1-6-quality-gates-mapping-qa` (baseline `2e6c5573cb90c0701ffe9b84f31d1c0f77ea3dd9`, final verified source SHA `6fa1dc1930ef0521577025803fe37235a6f1fde0`, `main` unchanged at `60448cc667113b8bbd7e2ac5a0449c836974cbaf`).
- **Implemented:**
  - **P0-A (Policy `v1.6.2`):** Coherent single-snapshot SERP evaluation (`eligibility_policy.py`) prohibiting cross-batch Top-10 or >=3 URL merging, rejecting duplicate Organic ranks, hashing ALL valid URLs in the selected snapshot, and recording full `snapshot_identity`.
  - **P0-B:** Automatic transactional freshness invalidation (`reconcile_project_freshness()` inside `confirm_semrush_import()`) + dynamic `live_fingerprint` checks across Mapping, Approvals (`409`), Briefs, and Exports (`409 HISTORICAL_EXPORT_SUPERSEDED` on unacknowledged outdated historical download while preserving original immutable bytes).
  - **P1-C:** Effective SQLite path resolution via `sqlalchemy.engine.make_url` (`resolve_sqlite_db_path()` in `db.py`, wired in `alembic/env.py`) so custom `FINZ_DATABASE_URL` backs up the actual target DB and fails closed on errors.
  - **P1-D:** Complete tamper-evident F2 import manifest (`manifest_sha256` over ALL `EvidenceRow`s + preview-to-confirm streaming SHA-256 verification + per-request disk verification); legacy batches missing manifest classify as `UNVERIFIED`.
  - **P1-E:** Forward migration `0003_snapshot_integrity_and_export_provenance` and explicit `FINZ_UNSUPPORTED_DOWNGRADE` exceptions in `0002` & `0003` `downgrade()`.
  - **QA-F:** Added `.github/workflows/finz-qa.yml`, upgraded `scripts/qa-parallel-check.py` (exact per-case nodeid parity), and expanded `scripts/qa-browser-t27-t29.mjs` (dynamic ports, route pre-warming, popup timer negative tests, stale freshness/export UI E2E, and 9-screen responsive verification).
- **Verification:**
  - Serial vs bounded-parallel (4 workers) `pytest`: 31/31 PASS (`case_identity_parity=true`, `serial_parallel_parity=true`).
  - Temp copy local DB migration `0001 -> 0003` + downgrade rejection: PASS (`quick_check=ok`, `foreign_key_check=0`, `projects_preserved=2`, `backups=1`).
  - Headless Chrome E2E (`scripts/qa-browser-t27-t29.mjs`): PASS across all 5 suites & 9 core screens.
  - Real GitHub Actions CI (`ubuntu-latest`) Run `#44911120993` on `6fa1dc1930ef0521577025803fe37235a6f1fde0`: **completed / success** (both Backend and Web+Chrome E2E jobs).
  - Detailed QA report: `docs/qa-runs/FINZ-16-QA-R2-20261121-1332/`.

## 2026-11-23 — Nâng cấp V2.0 theo Bộ key FinZ

- Tách 5 nhánh nối tiếp cho đầu vào, playbook, nghiên cứu, viết brief và xuất file/nghiệm thu.
- Thêm migration `0004_v2_source_metadata`, giữ dữ liệu legacy và cơ chế backup trước migration; không hỗ trợ downgrade phá dữ liệu.
- Đọc header Bộ key/NFC/F0, giữ metadata và phạm vi nhiều mã trong pillar. Playbook/thresholds đọc runtime; Settings ghi rõ ngưỡng đề xuất; AIRun lưu hash prompt thay phiên bản cứng.
- Phiếu Semrush VN, F2/F3 trước xuất, F1 thiếu số/key mới chờ duyệt; Critic nhận dữ liệu từng dòng. Ưu tiên dùng cả Volume/KD. Phân tích SERP, nhãn do người sửa và bài đọc nằm trên bằng chứng gốc, không sửa manifest/snapshot.
- BRIEF_WRITER và SERP_ANALYST chạy được với Mock; brief có schema, few-shot, F7 và số vòng sửa có giới hạn. JSON hỏng retry một lần; lỗi còn lại giữ nháp và nhãn cần người sửa. Bỏ mẫu Title chứa mã pillar và outline chung khỏi đường sinh nội dung.
- Xuất XLSX 5 sheet theo chủ đề, các khối brief/link đúng dòng, Backlog riêng; giữ lịch sử export và kiểm freshness. Chạy lại dòng mapping giữ ID/phê duyệt nếu không đổi fingerprint.
- Nghiệm thu cuối: 55 test + TypeScript đạt; build web đạt; 7 ảnh UI Chrome không lỗi JavaScript. P01 với file Semrush mẫu có Volume 140/KD20 → P2, không bịa số cho key thiếu dữ liệu.
- Báo cáo, ảnh và XLSX nháp: `docs/qa-runs/FINZ-V2-20261123/README.md`. Chưa kiểm provider bằng key thật hay xác minh pháp luật live; các ngưỡng và chính sách P0 tiếp tục chờ chốt.
