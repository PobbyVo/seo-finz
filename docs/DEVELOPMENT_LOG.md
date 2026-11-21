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
