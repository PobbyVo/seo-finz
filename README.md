# FinZ SEO Workbench V1.6

Ứng dụng web local (Dark Mode, Human-in-the-Loop) hỗ trợ chuyên viên SEO thực hiện quy trình nghiên cứu có kiểm chứng dựa trên SQLite, AI Provider Gateway (Google Gemini, OpenAI, Anthropic Claude, Mock) và đối chiếu dữ liệu Semrush xuất thủ công.

## Khởi động nhanh (1 lệnh duy nhất)

```bash
npm run dev
```

Lệnh `npm run dev` tại thư mục gốc sẽ tự động:
1. Tạo `services/api/.venv` và cài thư viện FastAPI nếu chưa có.
2. Cài thư viện Next.js trong `apps/web/` nếu chưa có.
3. Sao lưu SQLite (nếu đã có) và chạy Alembic migration (`alembic upgrade head`).
4. Khởi động đồng thời:
   - **Frontend (Next.js Dark Mode):** `http://127.0.0.1:3000`
   - **Backend API (FastAPI):** `http://127.0.0.1:8000` (Swagger Docs: `http://127.0.0.1:8000/docs`)

## Tính năng nổi bật

- **Dark Mode chuẩn hóa** (`color-scheme: dark`, độ tương phản cao, hỗ trợ `prefers-reduced-motion`).
- **Settings → AI Providers (`/settings/ai`)**:
  - Hỗ trợ **Google Gemini**, **OpenAI**, **Anthropic Claude** và **Mock Provider (0 chi phí)**.
  - **Google Gemini Auto-Latest + Tự động hạ model sau 3 lần lỗi**: luôn ưu tiên model Gemini mới nhất (có thể đồng bộ danh sách mới nhất từ Google `/v1beta/models`), tự động theo dõi số lỗi và hạ bậc sang model kế tiếp sau 3 lần lỗi liên tiếp.
  - Bảo mật API key qua OS Keychain (macOS Keychain / Windows Credential Locker / Linux SecretService) hoặc biến môi trường server; **không bao giờ lưu plaintext vào SQLite, localStorage, log hay file export**.
  - Test Connection thật qua backend với mã lỗi chuẩn hóa tiếng Việt (`API_KEY_INVALID`, `PERMISSION_DENIED`, `MODEL_NOT_FOUND`, `QUOTA_EXCEEDED`, `RATE_LIMITED`, `CONNECTION_TIMEOUT`, `PROVIDER_UNAVAILABLE`, `INVALID_PROVIDER_RESPONSE`, `AI_NOT_CONFIGURED`).
- **Luồng 7 bước nghiên cứu có kiểm chứng (bỏ bước nhập SERP thủ công)**:
  1. **Thiết lập chủ đề**: Form + đọc XLSX/CSV tự nhận diện header không cố định dòng (vd: Topic Pillar dòng 4, Keywords dòng 1), quản lý nhiều dự án độc lập (P01/P08/P25/Z42…), bảo toàn keyword chính gốc và tạo phiên bản snapshot.
  2. **Bản đồ nhu cầu AI**: AI Topic Analyst + Critic trước Semrush, đối chiếu `source_refs` với SQLite (mã sai gắn `UNCERTAIN`), mỗi thẻ hiển thị bằng chứng, phản biện, dữ liệu thiếu và hành động tiếp theo.
  3. **Yêu cầu Semrush**: Hướng dẫn thao tác từng bước trên Semrush UI (không cần API/MCP/mật khẩu Semrush).
  4. **Upload, Preview & Ghép cột**: Xử lý toàn bộ file CSV/XLSX (tới 25.000 dòng), phân biệt locale `vi-VN` (`9.900`) và `en-US` (`9,900`), phân biệt `null` khác `0`, không cộng dồn Volume khi trùng keyword, parser riêng cho `ORGANIC_RESULTS`.
  5. **Kiểm tra dữ liệu & AI Critic sau Semrush**: Quality Gates deterministic `F0–F7`, `E0–E2`, bảo toàn keyword Volume thấp có giá trị B2B, giới hạn tối đa 2 lượt Critic/chu kỳ và hỗ trợ mở chu kỳ mới.
  6. **Kế hoạch bài viết / Keyword Mapping**: Tách riêng `ARTICLE` (mục tiêu mềm 5–7, không ép đủ), `TOOL`/`DOWNLOAD`/`SERVICE` (không tính quota ARTICLE) và `RESEARCH_GAP`; gắn `SERP_NOT_VERIFIED` khi chưa có `ORGANIC_RESULTS`.
  7. **SEO Content Brief & Xuất**: Chỉ tạo bản `OFFICIAL` khi đã phê duyệt + đạt đủ gate; Writing Strategy cấp toàn bài (13 công thức viết + 16 chiến thuật thu hút độc giả, không ép từng H2/H3); xuất **XLSX 3 sheet**, **CSV**, **JSON** và **Bản in HTML** theo tên dự án động.
- **Chờ phê duyệt (`/approvals`)** & **Nhật ký (`/logs`)**.

## Chạy kiểm thử

```bash
npm test
npm run build:web
```
