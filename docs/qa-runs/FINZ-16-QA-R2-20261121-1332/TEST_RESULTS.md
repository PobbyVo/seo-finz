# FINZ-16-QA-R2 — Ma Trận Kết Quả Kiểm Thử Thực Tế

> Tất cả bài kiểm thử AI trong bộ `pytest` và CI chạy ở chế độ **`MOCK`** (0 chi phí API, `FINZ_SECRET_BACKEND=memory`). Không có cuộc gọi trả phí nào tới OpenAI / Gemini / Anthropic trong lần chạy R2 này (`LIVE_NOT_TESTED` cho paid APIs trong R2).

## 1. Kết Quả Các Hạng Mục Mới R2 (`S01–S10`, `F01–F09`, `B01–B06`, `I01–I08`, Downgrade & CI)

| Nhóm / Mã | Kịch bản kiểm chứng | Hàm test / Script | Chế độ | Kết quả | Bằng chứng |
| :--- | :--- | :--- | :---: | :---: | :--- |
| **S01** | 1 snapshot 10 vị trí organic hợp lệ → `TOP_10_VERIFIED` kèm batch & timestamp provenance | `test_r2_p0a_serp_snapshots.py::test_s01_...` | INTEGRATION | **PASS** | `parallel_parity.json` |
| **S02** | Batch 1 (1..5) + Batch 2 (6..10) → không bao giờ `TOP_10_VERIFIED` | `test_r2_p0a_serp_snapshots.py::test_s02_s03_...` | INTEGRATION | **PASS** | `parallel_parity.json` |
| **S03** | 3 batch độc lập mỗi batch 1 URL → giữ `PARTIAL_SERP_EVIDENCE`, chặn OFFICIAL | `test_r2_p0a_serp_snapshots.py::test_s02_s03_...` | INTEGRATION | **PASS** | `parallel_parity.json` |
| **S04** | 2 snapshot mâu thuẫn URL top 1 → chọn 1 snapshot xác định bất kể thứ tự đọc | `test_r2_p0a_serp_snapshots.py::test_s04_s05_s06_...` | INTEGRATION | **PASS** | `parallel_parity.json` |
| **S05** | Trộn thị trường VN/US & từ khóa A/B → cách ly nghiêm ngặt | `test_r2_p0a_serp_snapshots.py::test_s04_s05_s06_...` | INTEGRATION | **PASS** | `parallel_parity.json` |
| **S06** | `AI Overview` rank 1 + `Organic` rank 1 → 0 duplicate organic rank, không giả Top 10 | `test_r2_p0a_serp_snapshots.py::test_s04_s05_s06_...` | INTEGRATION | **PASS** | `parallel_parity.json` |
| **S07** | Đổi URL vị trí #25 đổi `serp_evidence_hash`; từ khóa không liên quan không đổi | `test_r2_p0a_serp_snapshots.py::test_s07_s08_...` | INTEGRATION | **PASS** | `parallel_parity.json` |
| **S08** | Fixture Semrush thật 104 dòng (5 AI Overview + 99 Organic, không cột Keyword) | `test_r2_p0a_serp_snapshots.py::test_s07_s08_...` | INTEGRATION | **PASS** | `parallel_parity.json` |
| **S09** | Thiếu keyword binding hoặc trùng organic rank #1 → không chứng nhận snapshot | `test_r2_p0a_serp_snapshots.py::test_s09_s10_...` | INTEGRATION | **PASS** | `parallel_parity.json` |
| **S10** | Hiệu năng giới hạn với 12 snapshot nhiều từ khóa (<10s, xác định) | `test_r2_p0a_serp_snapshots.py::test_s09_s10_...` | INTEGRATION | **PASS** | `parallel_parity.json` |
| **F01** | SERP mâu thuẫn sau duyệt tự động vô hiệu hóa A không cần bấm Mapping | `test_r2_p0b_freshness_invalidation.py::test_f01_f06_f07_...` | MOCK/INT | **PASS** | `parallel_parity.json` |
| **F02** | Metrics đổi KD/Intent sau duyệt tự động vô hiệu hóa A | `test_r2_p0b_freshness_invalidation.py::test_f02_f04_f05_...` | MOCK/INT | **PASS** | `parallel_parity.json` |
| **F03** | Import cho A không làm mất hiệu lực OFFICIAL của B | `test_r2_p0b_freshness_invalidation.py::test_f01_f06_f07_...` | MOCK/INT | **PASS** | `parallel_parity.json` |
| **F04** | Re-import file giống hệt → idempotent, không tạo approval trùng | `test_r2_p0b_freshness_invalidation.py::test_f02_f04_f05_...` | MOCK/INT | **PASS** | `parallel_parity.json` |
| **F05** | Snapshot mới thiếu (1 URL) hạ A xuống `PARTIAL_SERP_EVIDENCE`, chặn OFFICIAL | `test_r2_p0b_freshness_invalidation.py::test_f02_f04_f05_...` | MOCK/INT | **PASS** | `parallel_parity.json` |
| **F06** | `allow_draft=True`, API brief trực tiếp & tải export cũ không lách được stale (`409`) | `test_r2_p0b_freshness_invalidation.py::test_f01_f06_f07_...` | MOCK/INT | **PASS** | `parallel_parity.json` |
| **F07** | Bảo toàn nguyên vẹn `BriefVersion`, `Approval`, `MappingRevision`, `ExportRecord` & byte file cũ | `test_r2_p0b_freshness_invalidation.py::test_f01_f06_f07_...` | MOCK/INT | **PASS** | `parallel_parity.json` |
| **F08** | Lỗi ngoại lệ trong giao dịch confirm rollback nguyên tử (không nửa vời) | `test_r2_p0b_freshness_invalidation.py::test_f08_f09_...` | MOCK/INT | **PASS** | `parallel_parity.json` |
| **F09** | Duyệt approval fingerprint cũ sau khi có bằng chứng mới → `409 Conflict` | `test_r2_p0b_freshness_invalidation.py::test_f08_f09_...` | MOCK/INT | **PASS** | `parallel_parity.json` |
| **B01** | `FINZ_DATABASE_URL` X != `resolved_db_path` Y → Alembic backup đúng X | `test_r2_p1_backup_f2_downgrade.py::test_b01_...` | SERIAL | **PASS** | `parallel_parity.json` |
| **B02** | Active WAL writer trên custom `FINZ_DATABASE_URL` → backup đọc được khớp 100% dòng | `test_r2_p1_backup_f2_downgrade.py::test_b02_...` | SERIAL | **PASS** | `parallel_parity.json` |
| **B03** | Giả lập lỗi đĩa đầy (`ENOSPC`) → migration dừng trước khi đổi schema | `test_r2_p1_backup_f2_downgrade.py::test_b01_...` | SERIAL | **PASS** | `parallel_parity.json` |
| **B04** | Không có migration chờ → không tạo backup thừa | `test_r2_p1_backup_f2_downgrade.py::test_b01_...` | SERIAL | **PASS** | `parallel_parity.json` |
| **B05** | Phân giải URL tương đối, có dấu cách, Windows drive (unit) & chặn `:memory:` / non-SQLite | `test_r2_p1_backup_f2_downgrade.py::test_b01_...` | UNIT | **PASS** *(Windows live: `NOT_RUN`)* | `parallel_parity.json` |
| **B06** | Khởi tạo DB hoàn toàn mới không tạo backup giả của file rỗng | `test_r2_p1_backup_f2_downgrade.py::test_b01_...` | SERIAL | **PASS** | `parallel_parity.json` |
| **I01–I05** | F2 manifest đầy đủ, chặn sửa file giữa preview/confirm (`409`), phát hiện sửa dòng #10, sửa/xóa file trên đĩa | `test_r2_p1_backup_f2_downgrade.py::test_i01_to_i08_...` | SERIAL | **PASS** | `parallel_parity.json` |
| **I06–I07** | 266 dòng xử lý toàn bộ, `0 != null`, trùng không cộng Volume, cách ly 2 dự án + export cross-project `404` | `test_r2_p1_backup_f2_downgrade.py::test_b02_i06_i07_...` | SERIAL | **PASS** | `parallel_parity.json` |
| **I08** | Batch cũ thiếu `manifest_sha256` gắn `UNVERIFIED` (không tự `PASSED`) | `test_r2_p1_backup_f2_downgrade.py::test_i01_to_i08_...` | SERIAL | **PASS** | `parallel_parity.json` |
| **P1-E** | `alembic downgrade 0001_initial_schema` ném `FINZ_UNSUPPORTED_DOWNGRADE`, giữ nguyên schema/version/rows | `test_r2_p1_backup_f2_downgrade.py` + temp copy DB thật | SERIAL | **PASS** | `parallel_parity.json` |
| **QA-F (CI)** | GitHub Actions workflow `.github/workflows/finz-qa.yml` trên commit `6fa1dc1` | Run `#44911120993` (2 jobs: Backend + Web/Chrome E2E) | CI (`ubuntu-latest`) | **PASS** | https://github.com/quocan050302/Finz/actions/runs/44911120993 |

## 2. Ma Trận Hồi Quy Đầy Đủ `T01–T30` & R1 `G1–G8` / `M1–M8` (Chạy Lại Thực Tế Trong R2)

| Nhóm | Phạm vi | Vị trí kiểm thử | Chế độ | Kết quả |
| :--- | :--- | :--- | :---: | :---: |
| **T01–T05** | Đa dự án, header Excel dòng 4, preview không ghi đè, không đoán goal/audience, bảo toàn keyword gốc | `test_t01_t05_projects_taxonomy.py` | INTEGRATION | **PASS** (3/3) |
| **T06–T10** | AI Settings 4 provider, key bảo mật, CTA `AI_NOT_CONFIGURED`, Gemini hạ model sau 3 lỗi, lỗi 401/403/404/429/timeout | `test_t06_t10_ai_settings_gemini_fallback.py` | MOCK | **PASS** (4/4) *(Paid API live: `LIVE_NOT_TESTED` in R2)* |
| **T11–T14** | `source_refs` → `UNCERTAIN`, thẻ nhu cầu, Critic followups & giới hạn 2 lượt/chu kỳ | `test_t11_t14_demand_map_critic.py` | MOCK | **PASS** (2/2) |
| **T15–T20** | Semrush thủ công, preview không ghi DB, >200 dòng, locale `vi-VN`/`en-US`, `null != 0`, không cộng Volume, `SERP_NOT_VERIFIED` | `test_t15_t20_semrush_evidence_gates.py` | INTEGRATION | **PASS** (1/1) |
| **T21–T26** | Không có trang nhập SERP tay, đề xuất gộp/tách, loại trừ non-ARTICLE khỏi quota 5–7, Brief 13+16 toàn bài, XLSX 3 bảng động | `test_t21_t26_mapping_approvals_brief_export.py` | INTEGRATION | **PASS** (1/1) |
| **G1–G8, M1–M8** | Toàn bộ cổng P0 R1 + revision an toàn + E0 + E2E 7 bước + xuất 4 định dạng không rò rỉ secret | `test_p0_qa_r1_gates_serp_revisions.py`, `test_p1_backup_migration_uploads_e2e.py` | MOCK/INT | **PASS** (9/9) |
| **T27–T29 + R2 UI** | Popup sau commit SQLite, 1.8s nav, hủy Stay/Esc/Back/đổi dự án, lỗi không hiện popup, stale UI/export `409`, responsive `320/768/1440px` trên 9 màn hình | `scripts/qa-browser-t27-t29.mjs` (Chrome CDP thật, cổng động) | BROWSER E2E | **PASS** (5/5 nhóm, 9/9 route) |
| **T30** | Nâng cấp forward `0001 → 0003` + online WAL backup + `quick_check` & `foreign_key_check` + chặn downgrade | `test_p1_backup_migration_uploads_e2e.py`, `test_r2_p1_backup_f2_downgrade.py` + temp copy DB thật | SERIAL | **PASS** (`projects_preserved=2`, `backups=1`) |

## 3. Đối Chiếu Chạy Tuần Tự vs Song Song Có Giới Hạn
- **Lệnh:** `services/api/.venv/bin/python scripts/qa-parallel-check.py` (exit code `0`)
- **Serial (hermetic TMPDIR):** `31/31 PASSED` trong `10.833s`.
- **Bounded Parallel (4 workers cho 8 module độc lập + 2 module migration/backup chạy tuần tự trên TMPDIR riêng):** `31/31 PASSED` trong `12.122s`.
- **Đối chiếu từng test case (`case_identity_parity`):** `true`, `divergences: {}`, `serial_parallel_parity: true`.
