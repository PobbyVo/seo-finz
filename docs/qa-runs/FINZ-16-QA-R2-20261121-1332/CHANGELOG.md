# FINZ-16-QA-R2 — Nhật Ký Thay Đổi File & Hàm

## Backend (`services/api/`)
- **`app/models.py` & `alembic/versions/0003_snapshot_integrity_and_export_provenance.py` *(mới)***:
  - Thêm cột provenance & manifest cho `ResearchBatch` (`import_seq`, `target_keyword`, `keyword_binding_source`, `source_observation_at`, `source_file_sha256`, `manifest_sha256`, `integrity_status`) và `ExportRecord` (`evidence_state_hash`, `brief_fingerprints_json`, `is_superseded`, `superseded_reason`).
  - Migration `0003` chạy forward-only an toàn (không làm mất dữ liệu cũ; batch cũ để `manifest_sha256=NULL` → `UNVERIFIED`).
- **`alembic/versions/0002_revision_fingerprint_and_serp_provenance.py`**:
  - Thay `downgrade(): pass` bằng `raise RuntimeError("FINZ_UNSUPPORTED_DOWNGRADE: ...")` để ngăn Alembic hạ phiên bản giả khi schema SQLite không đổi ngược.
- **`app/db.py` & `alembic/env.py`**:
  - Thêm `resolve_sqlite_db_path()` dùng `sqlalchemy.engine.make_url` (xử lý đường dẫn tương đối, có dấu cách, Windows drive, fail-closed `:memory:` / non-SQLite).
  - Cập nhật `backup_database()` và `run_migrations_online()` luôn backup đúng file SQLite hiệu lực từ `FINZ_DATABASE_URL`, kiểm tra `db_existed_before` trước khi kết nối để không tạo backup rỗng khi khởi tạo DB mới.
- **`app/domain/eligibility_policy.py` (Policy `v1.6.2`)**:
  - Thêm `compute_file_sha256_streaming()`, `compute_batch_manifest_sha256()`, `verify_batch_integrity_detailed()`, `select_effective_metrics_row()`, `compute_metrics_evidence_hash()`, `_evaluate_single_serp_snapshot()`, `compute_effective_brief_freshness()`.
  - Viết lại `evaluate_serp_for_keyword()` theo mô hình **1 snapshot thống nhất** (không gộp URL/vị trí xuyên batch, không băm cắt 20 dòng đầu, loại `AI Overview` trước khi đếm duplicate rank, chọn snapshot mới nhất xác định bất kể thứ tự đọc).
  - Cập nhật `compute_mapping_fingerprint()` dùng digest ngữ nghĩa (loại bỏ UUID ngẫu nhiên để re-import giống hệt là idempotent) và cập nhật `evaluate_mapping_eligibility()` tính `live_fingerprint` động trên mọi lần đọc/duyệt/xuất.
- **`app/domain/mapping_engine.py`**:
  - Thêm `reconcile_project_freshness()`, `_ensure_pending_approval_for_mapping()`, `_invalidate_linked_briefs_and_exports()` chạy đồng bộ trong cùng giao dịch import để tự động vô hiệu hóa approval/brief/export bị ảnh hưởng mà không ảnh hưởng từ khóa khác.
- **`app/routers/research.py`**:
  - `confirm_semrush_import()`: stream-hash kiểm tra file trên đĩa khớp preview SHA-256 trước khi ghi (`409 UPLOAD_TAMPERED_BETWEEN_PREVIEW_AND_CONFIRM`), tính `manifest_sha256`, gán `import_seq` và `keyword_binding_source`, gọi `reconcile_project_freshness()` trước `db.commit()`.
- **`app/domain/brief_engine.py`, `app/domain/exporter.py`, `app/routers/briefs.py`, `app/routers/mapping.py`, `app/domain/workflow.py`, `app/main.py`**:
  - `serialize_brief()`, `evaluate_all_gates()`, `refresh_workflow_state()`, `compute_project_export_state()`, `evaluate_export_record_freshness()`, `download_existing_export()` đồng bộ 100% theo trạng thái freshness động; chặn tải âm thầm bản xuất lịch sử đã thay thế (`409 HISTORICAL_EXPORT_SUPERSEDED`), cho phép tải rõ ràng qua `?acknowledge_historical=true` nguyên byte gốc; `decide_approval()` kiểm tra lại `live_fingerprint` trước khi duyệt (`409`).
  - `main.py` bổ sung `X-FinZ-Export-Id`, `X-FinZ-Export-Freshness`, `X-FinZ-Export-Warning` vào CORS `expose_headers`.

## Frontend (`apps/web/src/`)
- **`lib/types.ts` & `components/StatusBadge.tsx`**: Bổ sung kiểu `ExportHistoryItem`, `snapshot_identity`, `stale_reasons` và nhãn `VERIFIED`, `UNVERIFIED`, `CURRENT`, `OUTDATED_SUPERSEDED`, `HISTORICAL_SUPERSEDED`.
- **`app/steps/05-evidence/page.tsx`**: Hiển thị bảng lịch sử Batch kèm trạng thái toàn vẹn F2 Manifest và nguồn ràng buộc từ khóa.
- **`app/steps/06-mapping/page.tsx`**: Hiển thị `selected_batch_id` + loại timestamp (`INGESTED_AT` / `SOURCE_OBSERVED`) và ghi chú chính sách 1 snapshot `v1.6.2`.
- **`app/steps/07-brief/page.tsx`**: Tải & hiển thị mục **Lịch sử các bản xuất** phân tách rõ bản `CURRENT` vs `OUTDATED_SUPERSEDED`, hiển thị lý do `stale_reasons` cụ thể trên banner Brief cũ.

## Kiểm thử & CI
- **`.github/workflows/finz-qa.yml` *(mới)***: Workflow CI 2 job (`backend-qa` + `web-build-and-browser-e2e`) chạy thật trên `ubuntu-latest` không dùng API key trả phí.
- **`scripts/qa-parallel-check.py`**: Nâng cấp so khớp chính xác từng nodeid test case (`case_identity_parity`) và tách chạy tuần tự các module migration/backup.
- **`scripts/qa-browser-t27-t29.mjs`**: Cấp phát cổng OS động, pre-warming route cho CI 2 vCPU, cờ Chrome Linux an toàn, bổ sung test hủy timer bằng Browser Back / chuyển dự án / lỗi submit, test luồng stale freshness + historical export `409`, và responsive `320/768/1440px` trên 9 màn hình cốt lõi.
- **Test suites mới**: `test_r2_p0a_serp_snapshots.py`, `test_r2_p0b_freshness_invalidation.py`, `test_r2_p1_backup_f2_downgrade.py`.
