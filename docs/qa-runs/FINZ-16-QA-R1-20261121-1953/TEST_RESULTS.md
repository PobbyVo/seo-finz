# FINZ-16-QA-R1 — Ma Trận Kết Quả Kiểm Thử Thực Tế

> Lưu ý trung thực: Mọi bài kiểm thử AI trong bộ `pytest` tự động chạy ở chế độ **`MOCK`** (0 chi phí API). Lượt kiểm tra kết nối trực tiếp tới Google Gemini được chạy riêng 1 lần theo ủy quyền rõ ràng của chủ dự án (key không lưu/ghi vào repo hay SQLite) và tách biệt khỏi kết quả `MOCK`.

## 1. Bảng Tái Hiện Lỗi P0 Trước Khi Sửa vs Sau Khi Sửa (`G1–G8`, `M1–M8`)

| Mã | Kịch bản kiểm chứng | Trước khi sửa (`60448cc`) | Sau khi sửa | File kiểm thử |
| :--- | :--- | :---: | :---: | :--- |
| **G1** | SERP chỉ có cho từ khóa A, duyệt từ khóa B → B phải `official=False` & `SERP_NOT_VERIFIED` | **FAIL** (`KeyError: 'eligibility'`, rò rỉ SERP global) | **PASS** | `test_p0_qa_r1_gates_serp_revisions.py` |
| **G2** | Thiếu KD / lệch thị trường (`US != VN`) / thiếu mục tiêu kinh doanh chặn OFFICIAL | **FAIL** | **PASS** | `test_p0_qa_r1_gates_serp_revisions.py` |
| **G3** | `E0` `source_ref` bịa (`FABRICATED:9999`) chặn OFFICIAL kể cả khi đã có SERP + duyệt | **FAIL** | **PASS** | `test_p1_backup_migration_uploads_e2e.py` |
| **G4** | `F2/F3/F4` không tự `PASSED` chỉ vì bảng có 1 dòng | **FAIL** (`F3=='PASSED'` khi thiếu business goal) | **PASS** | `test_p0_qa_r1_gates_serp_revisions.py` |
| **G5** | `allow_draft=True` không được lách gate tạo `OFFICIAL` cho mapping chưa đạt | **FAIL** | **PASS** | `test_p0_qa_r1_gates_serp_revisions.py` |
| **G6** | Thiếu SERP → `DRAFT` đóng dấu `SERP_NOT_VERIFIED` | **PASS** | **PASS** | `test_p0_qa_r1_gates_serp_revisions.py` |
| **G7** | Đủ bằng chứng đúng từ khóa/thị trường + duyệt đúng rev/fingerprint → `OFFICIAL` | **PASS** | **PASS** | `test_p0_qa_r1_gates_serp_revisions.py` |
| **G8** | 1–2 URL organic chỉ là `PARTIAL_SERP_EVIDENCE`, không được đóng dấu `TOP_10_VERIFIED` hay `OFFICIAL` | **FAIL** | **PASS** | `test_p0_qa_r1_gates_serp_revisions.py` |
| **M1** | Chạy lại `mapping/preview` không đổi đầu vào → giữ nguyên ID, 0 duplicate approval | **FAIL** (ID bị xóa tạo mới) | **PASS** | `test_p0_qa_r1_gates_serp_revisions.py` |
| **M2** | Đổi URL/page_type/bằng chứng → vô hiệu hóa approval cũ, tăng rev, đổi fingerprint | **FAIL** | **PASS** | `test_p0_qa_r1_gates_serp_revisions.py` |
| **M3** | Duyệt lại approval cũ/đã xong sau khi đổi rev → trả `409 Conflict`, không mutate | **FAIL** | **PASS** | `test_p0_qa_r1_gates_serp_revisions.py` |
| **M4** | `REJECTED` / `NEED_MORE_EVIDENCE` giữ chặn OFFICIAL | **PASS** | **PASS** | `test_p0_qa_r1_gates_serp_revisions.py` |
| **M5** | Cross-project approval ID bị từ chối (`404`/`403`) | **PASS** | **PASS** | `test_p0_qa_r1_gates_serp_revisions.py` |
| **M6** | Brief `OFFICIAL` cũ sống sót khi rebuild Mapping, tự đánh dấu `is_stale=True` & hạ `DRAFT` | **FAIL** | **PASS** | `test_p0_qa_r1_gates_serp_revisions.py` |
| **M7** | Bảo toàn snapshot, batch import, `source_keywords` và `mapping_revisions` | **PASS** | **PASS** | `test_p0_qa_r1_gates_serp_revisions.py`, `test_p1_backup_migration_uploads_e2e.py` |
| **M8** | Thay đổi trọng yếu chỉ qua hành động duyệt rõ ràng, không tự duyệt | **PASS** | **PASS** | `test_p0_qa_r1_gates_serp_revisions.py`, `test_p1_backup_migration_uploads_e2e.py` |
| **REAL-CSV** | 2 file Semrush thật (15 metrics + 104 dòng SERP gồm 5 `AI Overview` + 99 `Organic` không có cột `Keyword`) | **FAIL** (`0 == 5` AI Overview) | **PASS** (`TOP_10_VERIFIED` + `OFFICIAL`) | `test_p0_qa_r1_gates_serp_revisions.py` |

## 2. Ma Trận Nghiệm Thu `T01–T30`

| Mã | Yêu cầu | Vị trí test | Chế độ | Kết quả |
| :--- | :--- | :--- | :---: | :---: |
| T01 | Tạo nhiều dự án P01/P08/Z42 độc lập, lưu SQLite | `test_t01_t05_projects_taxonomy.py` | INTEGRATION | **PASS** |
| T02 | Excel header Topic Pillar dòng 4 & Keywords dòng 1 | `test_t01_t05_projects_taxonomy.py` | INTEGRATION | **PASS** |
| T03 | Xem trước không ghi đè dữ liệu dự án khi chưa xác nhận | `test_t01_t05_projects_taxonomy.py` | INTEGRATION | **PASS** |
| T04 | Không tự đoán / mang nhầm business goal & audience | `test_t01_t05_projects_taxonomy.py` | INTEGRATION | **PASS** |
| T05 | Bảo toàn keyword chính gốc, đổi primary tạo approval | `test_t01_t05_projects_taxonomy.py` | INTEGRATION | **PASS** |
| T06 | AI Settings hỗ trợ OpenAI/Gemini/Claude/Mock | `test_t06_t10_ai_settings_gemini_fallback.py` | INTEGRATION | **PASS** |
| T07 | Test Connection mocked thành công & lỗi 401/403/404/429/timeout + Gemini hạ model sau 3 lỗi | `test_t06_t10_ai_settings_gemini_fallback.py` | MOCK | **PASS** |
| T08 | API key (`AIza*`, `AQ.*`) không lọt SQLite, response, export | `test_t06_t10_ai_settings_gemini_fallback.py`, `test_p1_backup_migration_uploads_e2e.py` | INTEGRATION | **PASS** |
| T09 | Mở Settings không tự gọi API tính phí; live check riêng theo ủy quyền | `test_t06_t10_ai_settings_gemini_fallback.py` + live Gemini ping | MOCK + LIVE (Gemini only) | **PASS** *(OpenAI/Claude: `LIVE_NOT_TESTED`)* |
| T10 | Chưa cấu hình AI trả `AI_NOT_CONFIGURED` kèm CTA `/settings/ai` | `test_t06_t10_ai_settings_gemini_fallback.py` | INTEGRATION | **PASS** |
| T11 | AI `source_refs` sai bị gắn `UNCERTAIN` & chặn OFFICIAL (E0) | `test_t11_t14_demand_map_critic.py`, `test_p1_backup_migration_uploads_e2e.py` | MOCK | **PASS** |
| T12 | Thẻ nhu cầu có đủ bằng chứng, phản biện, dữ liệu thiếu, hành động tiếp | `test_t11_t14_demand_map_critic.py` | MOCK | **PASS** |
| T13 | Keyword Volume thấp sát B2B không bị loại theo ngưỡng cứng | `test_t15_t20_semrush_evidence_gates.py` | INTEGRATION | **PASS** |
| T14 | Critic sinh `followup_requests`, duyệt tạo ResearchRequest, giới hạn 2 lượt/chu kỳ + mở chu kỳ | `test_t11_t14_demand_map_critic.py` | MOCK | **PASS** |
| T15 | Semrush hoàn toàn thủ công, không gọi API/MCP | `test_t15_t20_semrush_evidence_gates.py` | INTEGRATION | **PASS** |
| T16 | Preview file Semrush không ghi SQLite, chỉ Confirm mới lưu | `test_t15_t20_semrush_evidence_gates.py` | INTEGRATION | **PASS** |
| T17 | Upload >200 dòng (263 dòng) được xử lý toàn bộ + chặn file quá 15MB (413) | `test_t15_t20_semrush_evidence_gates.py`, `test_p1_backup_migration_uploads_e2e.py` | INTEGRATION | **PASS** |
| T18 | Locale `vi-VN` (`9.900`, `45,5`) / `en-US` (`9,900`), `null != 0`, trùng không cộng Volume | `test_t15_t20_semrush_evidence_gates.py` | INTEGRATION | **PASS** |
| T19 | Import đủ metrics không tự nâng `READY_FOR_BRIEF` | `test_t15_t20_semrush_evidence_gates.py`, `test_p0_qa_r1_gates_serp_revisions.py` | INTEGRATION | **PASS** |
| T20 | Không có SERP → kế hoạch & brief chỉ là `DRAFT` đóng dấu `SERP_NOT_VERIFIED` | `test_t21_t26_mapping_approvals_brief_export.py`, `test_p0_qa_r1_gates_serp_revisions.py` | INTEGRATION | **PASS** |
| T21 | Không có màn hình bắt buộc nhập SERP thủ công (giữ đúng luồng 7 bước) | `apps/web/src/components/AppShell.tsx`, `scripts/qa-browser-t27-t29.mjs` | BROWSER | **PASS** |
| T22 | Gộp/tách bài ghi rõ là đề xuất cần bằng chứng, không tự kết luận | `test_t21_t26_mapping_approvals_brief_export.py` | INTEGRATION | **PASS** |
| T23 | `TOOL`/`DOWNLOAD`/`SERVICE` không tính vào quota mềm 5–7 bài `ARTICLE` | `test_t21_t26_mapping_approvals_brief_export.py` | INTEGRATION | **PASS** |
| T24 | Brief chính thức chỉ sau phê duyệt đúng phiên bản/fingerprint & đủ gate | `test_t21_t26_mapping_approvals_brief_export.py`, `test_p0_qa_r1_gates_serp_revisions.py` | INTEGRATION | **PASS** |
| T25 | Brief đủ trường SEO, Writing Strategy cấp toàn bài (13 công thức + 16 chiến thuật, không ép H2) | `test_t21_t26_mapping_approvals_brief_export.py` | INTEGRATION | **PASS** |
| T26 | Xuất XLSX đúng 3 bảng (`Keyword Overview`, `Keyword Mapping`, `SEO Content Brief`), tên file động không hardcode `Luong`, + CSV/JSON/HTML | `test_t21_t26_mapping_approvals_brief_export.py`, `test_p1_backup_migration_uploads_e2e.py` | INTEGRATION | **PASS** |
| T27 | Popup hoàn thành chỉ sau commit SQLite và tự chuyển bước sau ~1,8s | `scripts/qa-browser-t27-t29.mjs` (Chrome Headless CDP) | BROWSER E2E | **PASS** |
| T28 | "Ở lại bước này" và phím `Escape` hủy tự chuyển an toàn | `scripts/qa-browser-t27-t29.mjs` (Chrome Headless CDP) | BROWSER E2E | **PASS** |
| T29 | Responsive 320/768/1440px (0 overflow), `<meta name="color-scheme" content="dark">`, bảng focusable keyboard, `prefers-reduced-motion` | `scripts/qa-browser-t27-t29.mjs` (Chrome Headless CDP) | BROWSER E2E | **PASS** |
| T30 | Migration forward `0001` → `0002` + online WAL backup/restore + `quick_check` & `foreign_key_check` bảo toàn 100% dữ liệu | `test_p1_backup_migration_uploads_e2e.py` + temp copy DB thật | INTEGRATION | **PASS** |

## 3. Đối Chiếu Chạy Tuần Tự (Serial) vs Song Song Có Giới Hạn (4 Workers)

- **Lệnh:** `services/api/.venv/bin/python scripts/qa-parallel-check.py`
- **CPU / RAM:** 8 cores / 16 GB RAM → giới hạn worker `min(4, 8) = 4`.
- **Serial:** `exit_code=0`, `20 passed, 0 failed` trong `6.497s`.
- **Parallel (4 workers, mỗi worker `TMPDIR` & SQLite độc lập):** `exit_code=0`, `20 passed, 0 failed` trên cả 7 module trong `4.714s`.
- **Parity (`serial_parallel_parity`):** `true` (khớp hoàn toàn).

## 4. Kiểm Tra Kết Nối Trực Tiếp Gemini (Theo Ủy Quyền Chủ Dự Án — Tách Khỏi Bộ Test Tự Động)

- Kết nối thật qua `GeminiAdapter.test_connection()` với key chủ dự án cung cấp qua stdin tạm (không lưu repo/DB/log):
  - Phát hiện **16 model Gemini text** sạch (đã loại bỏ toàn bộ model ảnh/audio/transcribe/omni).
  - Bắt đầu từ `gemini-4-carbon`, tự động hạ bậc **8 lần** sau đủ **3/3 lỗi** trên mỗi model bị hết quota/timeout (`gemini-4-carbon → gemini-4-argon → gemini-4-neon → gemini-4-hydrogen → gemini-3.8-flash → gemini-3.7-flash → gemini-3.6-flash → gemini-3.5-flash → gemini-3.5-flash-lite`) và kết nối thành công `CONNECTED` tại **`gemini-3.5-flash-lite`** (`37,174 ms`).
