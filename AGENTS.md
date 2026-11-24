# AGENTS.md — FinZ SEO Workbench V2.0

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

## V2.0 business layer
- Read `app/knowledge/finz_playbook.md` for Vietnamese personal-finance SEO rules. Runtime thresholds live in `app/knowledge/thresholds.yaml`; all values remain proposals pending business approval.
- Source imports preserve NFC, original content code, angle, funnel stage, title-match check and pillar notes. F0 source errors block confirmation.
- Keep `eligibility_policy.py` snapshot, manifest, fingerprint and freshness checks authoritative. Business research and F7 may add blockers; never weaken evidence eligibility.
- `SERP_ANALYST` labels and public-page reads are hypotheses above immutable uploaded evidence. Store human corrections separately in ProjectEvent; do not rewrite uploaded evidence rows.
- `BRIEF_WRITER` must validate structured output and F7. Invalid output gets one retry; quality repairs use runtime thresholds. Failed output stays DRAFT / NEEDS_HUMAN_EDIT, clearly marked FALLBACK.
- Only ARTICLE gets article briefs. Tool/file/data opportunities belong to Backlog and never inflate ARTICLE counts.
- Exports contain only SEO Content Brief; XLSX has one brief sheet; test hyperlinks against actual brief block rows and preserve historical export bytes.

## Research policy for P01 expansion
- Imported projects created through the UI default to excluding missing/zero Semrush Volume from the plan, while preserving all original SourceKeyword rows. Legacy API projects retain their existing policy unless explicitly enabled. Preserve policy on source re-import.
- New research candidates have unknown Volume/KD until a matching upload verifies them. Do not count them toward 5–7 ARTICLEs or create mappings before human topic approval/promotion.
- Keep gross/net synonyms in one intent cluster. New P01 research seeds live in `knowledge/p01_research_seeds.json`; these are hypotheses, never verified search demand.
- Brief exports follow the reference dashboard/overview/block layout. Keep TOOL/DOWNLOAD/data items in Backlog; retain source exclusions and waiting-Semrush candidates in the research sheet.
