# FINZ-16-QA-R1 — QA & Hardening Run Summary

- **Task ID:** `FINZ-16-QA-R1`
- **Repository:** `https://github.com/quocan050302/Finz`
- **Target Branch:** `fix/v1-6-quality-gates-mapping-qa` (`main` untouched at `60448cc667113b8bbd7e2ac5a0449c836974cbaf`)
- **Base Commit SHA:** `60448cc667113b8bbd7e2ac5a0449c836974cbaf`
- **Final Source Commit SHA:** `74b81763e08c39a79de862cb86623669d702ffc8`
- **Policy Version:** `1.6.1`
- **Date:** `2026-11-21`
- **Final Verdict:** **PASS** *(all mandatory P0/P1 gates, T01–T30 checks, G1–G8, M1–M8, serial/parallel parity, SQLite migration/backup integrity, and headless Chrome UI tests executed and passed)*

## Key Outcomes
1. **Authoritative Eligibility Policy (P0):** Replaced fragmented gate checks with a single deterministic policy (`services/api/app/domain/eligibility_policy.py`) shared across Quality Gates (`F0–F7`, `E0–E2`), Mapping UI, Approvals, Brief Generation, and Exports. Separated Phase 1 pre-generation eligibility from Phase 2 post-generation brief quality (`F7`) to eliminate circular logic.
2. **Per-Keyword, Per-Market SERP Provenance (P0):** Eliminated project-global SERP fallback. Distinguished `SERP_NOT_VERIFIED`, `PARTIAL_SERP_EVIDENCE` (1–2 URLs), `SERP_VERIFIED` (≥3 valid ranked organic URLs), and `TOP_10_VERIFIED` (full positions 1–10). Added full support for real Semrush SERP Analysis CSVs (`Position,Type,Domain,URL,...`), separating `AI Overview` rows from `Organic` ranks and binding target keyword cleanly from `ResearchRequest` or explicit user input.
3. **Non-Destructive Mapping Revisions & Fingerprint-Bound Approvals (P0):** Removed destructive bulk `DELETE` on `KeywordMapping`. Stable logical IDs, immutable `MappingRevision` snapshots, canonical SHA-256 `content_fingerprint`, idempotent reruns, HTTP `409 Conflict` on stale/replayed/superseded approvals, and automatic staleness downgrade (`is_stale=True`, `brief_mode="DRAFT"`) on outdated `OFFICIAL` briefs.
4. **SQLite Online WAL Backup, Forward Migration & Streaming Upload Safety (P1):** Replaced raw `shutil.copy2` with `sqlite3.Connection.backup()` + atomic rename + `PRAGMA quick_check` / `PRAGMA foreign_key_check` fail-closed verification. Fixed SQLAlchemy 2.0 implicit outer-transaction rollback in `alembic/env.py` and avoided redundant backups when already at `head`. Added streaming chunked upload size enforcement (HTTP 413) and XLSX zip-bomb guard.
5. **Frontend Truthfulness & Real Browser QA (P1):** Fixed `CompletionPopup` initial-project race condition caught by headless Chrome E2E, added per-mapping blockers & `"Cần duyệt lại"` badges, strict per-selection `OFFICIAL` button gating on Step 07, and cross-project async race guards.

## Artifacts in This Run Folder
- `MANIFEST.json`: Machine-readable environment, baseline/final SHAs, commands, and gate outcomes.
- `TEST_RESULTS.md`: Full `T01–T30`, `G1–G8`, `M1–M8`, serial vs bounded-parallel (4 workers), browser E2E, migration, and owner-authorized live Gemini check matrix.
- `CHANGELOG.md`: Detailed file/function diff rationale.
- `RISKS.md`: Honest remaining untested boundaries and operational notes.
