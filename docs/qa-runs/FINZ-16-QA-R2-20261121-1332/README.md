# FINZ-16-QA-R2 — QA & Hardening Run Summary

- **Task ID:** `FINZ-16-QA-R2`
- **Repository:** `https://github.com/quocan050302/Finz`
- **Target Branch:** `fix/v1-6-quality-gates-mapping-qa` *(cùng nhánh đã tồn tại từ R1; không tạo nhánh mới)*
- **Main Baseline (Verified Unchanged):** `60448cc667113b8bbd7e2ac5a0449c836974cbaf`
- **R2 Baseline SHA (Branch Tip Before R2):** `2e6c5573cb90c0701ffe9b84f31d1c0f77ea3dd9`
- **Final Verified Source Code SHA:** `6fa1dc1930ef0521577025803fe37235a6f1fde0` *(gồm 2 commit code: `2e7f55c` + `6fa1dc1`)*
- **Policy Version:** `1.6.2`
- **Date:** `2026-11-21`
- **Verified Remote CI Run (Code SHA `6fa1dc1`):** Run `#44911120993` (`completed / success`) — https://github.com/quocan050302/Finz/actions/runs/44911120993
- **Final Verdict:** **PASS** *(đã đóng toàn bộ 5 lỗi P0/P1 + thiết lập và xác minh chạy thật CI trên GitHub Actions, 31/31 pytest serial/parallel parity 100%, Chrome Headless E2E PASS trên cả 9 màn hình cốt lõi)*

## Tóm tắt 6 hạng mục đã đóng trong R2
1. **P0-A — Coherent Single-Snapshot SERP (`eligibility_policy.py`):** Loại bỏ hoàn toàn việc gộp URL/thứ hạng xuyên nhiều `ResearchBatch`. Mỗi đánh giá SERP chỉ chọn **duy nhất 1 snapshot hợp lệ mới nhất** theo thứ tự xác định (`source_observation_at`/`import_seq`/`batch.id`), phát hiện xung đột rank Organic trùng lặp trong cùng snapshot, tách riêng `AI Overview`, và băm SHA-256 đầy đủ trên **toàn bộ** URL hợp lệ trong snapshot (không cắt 20 dòng đầu).
2. **P0-B — Automatic Evidence-Freshness Invalidation (`mapping_engine.py`, `research.py`, `eligibility_policy.py`, `exporter.py`, `briefs.py`):** Cả lớp cập nhật giao dịch ngay tại `confirm_semrush_import()` (`reconcile_project_freshness()`) lẫn lớp tính động `live_fingerprint` trong `evaluate_mapping_eligibility()` đảm bảo bằng chứng thay đổi sau phê duyệt lập tức vô hiệu hóa phê duyệt cũ, chuyển Brief `OFFICIAL` cũ sang `STALE`/`DRAFT` và đánh dấu các bản xuất lịch sử là `OUTDATED_SUPERSEDED` (chặn tải âm thầm bằng HTTP `409 Conflict`, chỉ cho tải nguyên bản lịch sử khi xác nhận `?acknowledge_historical=true`) mà **không cần người dùng bấm lại Bước 06**. Import lại file giống hệt là idempotent (0 tạo approval trùng); import từ khóa B không ảnh hưởng từ khóa A.
3. **P1-C — Effective `FINZ_DATABASE_URL` SQLite Backup (`db.py`, `alembic/env.py`):** Phân giải chính xác đường dẫn SQLite bằng `sqlalchemy.engine.make_url` (`resolve_sqlite_db_path`), hỗ trợ đường dẫn có dấu cách, tương đối và định dạng Windows, fail-closed với `:memory:` / non-SQLite / lỗi ổ đĩa, và bỏ qua backup sạch khi khởi tạo DB mới hoàn toàn.
4. **P1-D — Full Tamper-Evident F2 Batch Integrity (`eligibility_policy.py`, `research.py`, `quality_gates.py`, Migration `0003`):** Stream-hash file nguồn trước khi confirm (trả HTTP `409` nếu file bị sửa giữa Preview và Confirm), tính `manifest_sha256` trên **toàn bộ** các dòng `EvidenceRow` (không chỉ 5 dòng đầu) + kiểm tra file trên đĩa theo cache bounded 1 lần/request; batch cũ thiếu manifest được gắn `UNVERIFIED` (không bao giờ tự `PASSED`).
5. **P1-E — Forward-Only Migration Rejects `downgrade()` (`0002`, `0003`):** Thay `pass` bằng `RuntimeError("FINZ_UNSUPPORTED_DOWNGRADE: ...")` ở cả migration `0002` và `0003`; đã kiểm chứng `alembic downgrade 0001_initial_schema` thoát lỗi khác 0 và giữ nguyên version, schema, dữ liệu và khóa ngoại.
6. **QA-F — Real GitHub Actions CI & Expanded E2E (`.github/workflows/finz-qa.yml`, `qa-parallel-check.py`, `qa-browser-t27-t29.mjs`):** Thiết lập CI 2 job (`backend-qa` + `web-build-and-browser-e2e`), nâng cấp `qa-parallel-check.py` so khớp chính xác từng nodeid/kết quả (`case_identity_parity=true`) giữa serial và 4-worker bounded parallel, và mở rộng Headless Chrome E2E với cổng động OS + các kịch bản tiêu cực popup timer, stale freshness, historical export và responsive `320/768/1440px` trên 9 màn hình cốt lõi.

## Danh mục bằng chứng trong thư mục chạy R2
- `MANIFEST.json`: Siêu dữ liệu máy đọc được về SHA, môi trường, lệnh thực thi, cổng local và CI run thật.
- `REPRO_CASES.md`: Bằng chứng tái hiện lỗi đỏ (RED) trước khi sửa → xanh (GREEN) sau khi sửa kèm ví dụ 2 từ khóa / 2 batch.
- `TEST_RESULTS.md`: Ma trận đầy đủ `T01–T30`, R1 `G1–G8` / `M1–M8`, R2 `S01–S10`, `F01–F09`, `B01–B06`, `I01–I08`, downgrade negative tests, Browser E2E và GitHub Actions CI.
- `CHANGELOG.md`: Bản đồ file/hàm thay đổi và lý do kỹ thuật.
- `RISKS.md`: Rủi ro còn lại và ranh giới trung thực `MOCK` vs `LIVE_NOT_TESTED`.
- `phase1_red_repro.log`, `parallel_parity.json`, `browser_e2e.json`: Log kết quả thực thi thô đã làm sạch.
