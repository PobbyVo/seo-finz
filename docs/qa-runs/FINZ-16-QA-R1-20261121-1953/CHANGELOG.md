# FINZ-16-QA-R1 — Chi Tiết Các File & Hàm Đã Thay Đổi

## Backend (`services/api`)
- `app/domain/eligibility_policy.py` *(mới)*:
  - `POLICY_VERSION = "1.6.1"`
  - `evaluate_serp_for_keyword()`: Kiểm chứng SERP theo đúng project + exact keyword + market, loại `AI_OVERVIEW`/URL lỗi/Position lỗi, tính `SERP_NOT_VERIFIED` / `PARTIAL_SERP_EVIDENCE` / `SERP_VERIFIED` / `TOP_10_VERIFIED`.
  - `compute_mapping_fingerprint()`: Băm SHA-256 chuẩn hóa toàn bộ trường trọng yếu & mã bằng chứng của Mapping.
  - `verify_batch_integrity()`: Kiểm tra toàn vẹn `ResearchBatch` & `FileUpload` (F2) thay vì chỉ đếm dòng.
  - `evaluate_mapping_eligibility()`: Chính sách Phase 1 duy nhất cho quyết định đủ điều kiện Brief CHÍNH THỨC.
  - `evaluate_brief_quality()`: Hậu kiểm Phase 2 (`F7`) độc lập để tránh vòng lặp phụ thuộc.
- `app/domain/quality_gates.py`:
  - `evaluate_all_gates()`: Tái cấu trúc hoàn toàn trên `eligibility_policy.py`; trả về `mapping_eligibilities` từng từ khóa; loại bỏ các trạng thái `PASSED` giả cho F2/F3/F4/F5.
- `app/domain/mapping_engine.py`:
  - `build_keyword_mapping_preview()`: Bỏ bulk `DELETE` trên `KeywordMapping`; giữ ID ổn định theo `logical_key`; ghi `MappingRevision`; idempotent khi không đổi; vô hiệu hóa approval cũ (`SUPERSEDED`) và đánh dấu `is_stale=True` + hạ `DRAFT` cho Brief cũ khi dữ liệu/bằng chứng thay đổi.
- `app/domain/brief_engine.py`:
  - `generate_content_briefs()`, `serialize_brief()`: Ép dùng `evaluate_mapping_eligibility()`, chặn hoàn toàn lách gate qua `allow_draft=True`, lưu `mapping_revision`, `mapping_fingerprint`, `is_stale`, `eligibility_snapshot_json`.
- `app/domain/semrush_parser.py`:
  - `validate_organic_url()`, `normalize_serp_result_type()`, `suggest_column_mapping()`, `parse_semrush_rows()`: Hỗ trợ trọn vẹn file Semrush SERP Analysis thực tế (`Type=Organic` vs `AI Overview`, `Domain`, `fallback_keyword`, lọc & lưu raw các dòng lỗi).
- `app/domain/exporter.py` & `app/domain/workflow.py`:
  - Đồng bộ nhãn `SERP Tier`, `Top 10 Verified`, `Approval State`, `Stale` vào XLSX 3 sheet, CSV, JSON, HTML in ấn và Dashboard workflow state.
- `app/models.py` & `alembic/versions/0002_revision_fingerprint_and_serp_provenance.py` *(mới)*:
  - Migration forward-only không phá hủy dữ liệu cũ, bổ sung cột provenance SERP, fingerprint, stale brief và bảng `mapping_revisions`.
- `app/db.py` & `alembic/env.py` & `alembic.ini`:
  - Thay `shutil.copy2()` bằng online `sqlite3.Connection.backup()` + atomic rename + `verify_sqlite_integrity()` (`PRAGMA quick_check` + `PRAGMA foreign_key_check`), fail-closed khi lỗi đĩa.
  - Sửa lỗi giao dịch ngầm SQLAlchemy 2.0 trong `alembic/env.py` và chỉ tạo pre-migration backup khi thật sự có migration chờ chạy.
- `app/security/upload_guard.py` *(mới)*, `app/ai/errors.py`, `app/routers/{topic_source,research,mapping,briefs,projects}.py`, `app/schemas.py`:
  - Đọc upload dạng chunk stream chặn quá 15MB (HTTP 413) trước khi nạp RAM, chống XLSX zip-bomb, sanitize tên file đa HĐH, đường dẫn lưu không đè khi trùng prefix hash.
  - Redact thêm prefix key `AQ.*` trong `sanitize_secret_text()`.
  - Siết `decide_approval()` trả `409 Conflict` khi approval hết hiệu lực/trùng lặp/sai revision-fingerprint và chặn duyệt chéo dự án.

## Frontend (`apps/web`)
- `src/components/CompletionPopup.tsx`: Sửa bug đóng popup ngay lập tức khi tạo dự án đầu tiên (`null -> firstProjectId`), giữ đúng hủy timer khi chuyển dự án khác, đổi route, bấm "Ở lại" hoặc `Escape`.
- `src/app/steps/04-upload/page.tsx`: Hỗ trợ ghép cột `Type (Organic/AI Overview)`, `Domain` và nhập `target_keyword` cho file Semrush SERP Analysis không có cột `Keyword`.
- `src/app/steps/05-evidence/page.tsx`, `06-mapping/page.tsx`, `07-brief/page.tsx`, `approvals/page.tsx`: Chống race condition khi chuyển dự án; hiển thị điểm nghẽn cụ thể + nút sửa từng Mapping, nhãn `"Cần duyệt lại"`, nút `Tạo Brief CHÍNH THỨC` chỉ bật khi toàn bộ Mapping đang chọn đều đạt `eligible_official`, cảnh báo Brief `STALE`, và hiển thị `rev`/`fingerprint` trên màn hình phê duyệt.
- `src/lib/types.ts`, `src/components/StatusBadge.tsx`: Bổ sung kiểu `MappingEligibility` và badge trạng thái trung thực.

## QA & Test Tooling
- `services/api/tests/test_p0_qa_r1_gates_serp_revisions.py` *(mới)*
- `services/api/tests/test_p1_backup_migration_uploads_e2e.py` *(mới)*
- `services/api/tests/fixtures/semrush_{metrics,serp}_real_sample.csv` *(mới)*
- `scripts/qa-parallel-check.py` *(mới)* & `scripts/qa-browser-t27-t29.mjs` *(mới)*
