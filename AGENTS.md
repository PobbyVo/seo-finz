# AGENTS.md — FinZ SEO Workbench V1.6

## Architecture
- Root `package.json` + `scripts/dev.mjs`: Single `npm run dev` starts FastAPI (`127.0.0.1:8000`) and Next.js (`127.0.0.1:3000`).
- Backend (`services/api`): FastAPI + SQLAlchemy 2 + Alembic + SQLite (`data/finz_workbench.sqlite3`).
- Frontend (`apps/web`): Next.js 15 App Router + TypeScript + Tailwind CSS (Dark Mode default).

## Core Domain Guardrails
1. **No fabricated SEO data**: Never invent Volume, KD, or claim verified SERP Top 10 without uploaded Semrush `ORGANIC_RESULTS`.
2. **Human-in-the-loop**: AI proposes and critiques; humans approve primary keyword changes, new topics, and final Keyword Mapping.
3. **Secret hygiene**: API keys live ONLY in OS Keychain or server env vars — never plaintext in SQLite, API JSON responses, localStorage, git, or exports.
4. **Gemini Auto-Latest + 3-Failure Downgrade**: `GeminiAdapter` prioritizes the newest Gemini model and automatically downgrades to the next model in `fallback_chain` after 3 consecutive downgradable failures.
5. **No manual SERP entry step**: Keep the 7-step flow; if no `ORGANIC_RESULTS` CSV/XLSX is uploaded, plans/briefs remain `DRAFT` stamped `SERP_NOT_VERIFIED`.
6. **Non-ARTICLE exclusion**: `TOOL`, `DOWNLOAD`, `SERVICE`, and `PRODUCT` assets never count toward the soft 5–7 `ARTICLE` quota.
7. **Browser Support**: Baseline Widely Available + progressive enhancement with dark-mode `color-scheme: dark`, native `<dialog>` `showModal()`, container-query responsive tables, and `:user-invalid` ARIA sync.
