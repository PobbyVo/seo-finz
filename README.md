# FinZ SEO Workbench V1.6 — Hướng Dẫn Tải, Cài Đặt & Chạy Local

Ứng dụng web local (**Dark Mode**, vận hành 1 người dùng trên máy tính, lưu dữ liệu vào SQLite) hỗ trợ chuyên viên SEO thực hiện quy trình nghiên cứu có kiểm chứng **7 bước**:
`Nhập Topic Pillar/Keywords` → `AI phân tích & phản biện` → `Yêu cầu Semrush thủ công` → `Upload CSV/XLSX & ghép cột` → `Quality Gates & AI Critic` → `Keyword Mapping & Phê duyệt` → `SEO Content Brief & Xuất XLSX/CSV/JSON/HTML`.

**Hướng dẫn thao tác chi tiết:** [Hướng dẫn sử dụng từng bước](docs/HUONG_DAN_SU_DUNG.md) — từ mở ứng dụng, cấu hình AI đến phê duyệt mapping, xuất Content Brief và sao lưu dữ liệu.

---

## 1. Yêu cầu môi trường trên máy mới

Trước khi tải source, máy tính (macOS / Windows / Linux) cần cài sẵn 3 công cụ miễn phí sau:

1. **Git**: [https://git-scm.com/downloads](https://git-scm.com/downloads)
2. **Node.js (khuyên dùng bản LTS >= 20)**: [https://nodejs.org/](https://nodejs.org/)
3. **Python 3.11+ (khuyên dùng 3.12 hoặc 3.13)**: [https://www.python.org/downloads/](https://www.python.org/downloads/)
   - *Lưu ý cho Windows*: Khi cài Python, nhớ tick vào ô **"Add python.exe to PATH"**.

Kiểm tra nhanh trong Terminal (macOS/Linux) hoặc PowerShell/CMD (Windows):

```bash
git --version
node -v      # cần >= v20
python3 --version   # trên Windows có thể dùng: python --version
```

---

## 2. Tải source về máy & chạy ngay bằng 1 lệnh

Mở Terminal tại thư mục bạn muốn lưu dự án, chạy lần lượt:

```bash
# Bước 1: Tải mã nguồn từ GitHub
git clone https://github.com/quocan050302/Finz.git

# Bước 2: Đi vào thư mục dự án
cd Finz

# Bước 3: Khởi động toàn bộ hệ thống (tự cài thư viện + tạo DB + chạy API & Web)
npm run dev
```

### Lệnh `npm run dev` tự làm những gì?
Bạn **không cần** tạo virtualenv hay `npm install` thủ công. Lần đầu chạy, script `scripts/dev.mjs` sẽ tự động:
1. Tạo môi trường ảo Python tại `services/api/.venv` và cài toàn bộ thư viện FastAPI (`requirements.txt`).
2. Tự chạy migration SQLite (`alembic upgrade head`) để khởi tạo 25 bảng dữ liệu trong `data/finz_workbench.sqlite3`.
3. Cài thư viện Frontend Next.js trong `apps/web/node_modules`.
4. Khởi động đồng thời cả 2 dịch vụ:
   - **Giao diện Web (Dark Mode):** `http://127.0.0.1:3000`
   - **Backend API (FastAPI):** `http://127.0.0.1:8000` *(Tài liệu API Swagger: `http://127.0.0.1:8000/docs`)*

Khi thấy dòng:
```text
[FINZ] Sẵn sàng! Mở trình duyệt tại: http://127.0.0.1:3000
```
→ Mở trình duyệt và truy cập **`http://127.0.0.1:3000`**.

> Để dừng ứng dụng: nhấn `Ctrl + C` tại cửa sổ Terminal đang chạy `npm run dev`.

*(Tùy chọn)* Nếu chỉ muốn cài môi trường trước mà chưa mở server:
```bash
npm run setup
```

---

## 3. Cấu hình AI API Key lần đầu (Gemini / OpenAI / Claude / Mock)

Ứng dụng cấu hình AI trực tiếp trên giao diện, **không cần sửa file `.env.local`**.

1. Mở `http://127.0.0.1:3000/settings/ai` (nút **Settings → AI Providers** ở cuối thanh sidebar bên trái).
2. Chọn nhà cung cấp bạn muốn dùng:
   - **Google Gemini (Khuyên dùng):**
     - Lấy API key tại [Google AI Studio](https://aistudio.google.com/apikey).
     - Dán key vào ô **API Key**, giữ nguyên tùy chọn **"Tự động lấy model Gemini mới nhất (Auto-Latest)"** và ngưỡng **"Tự hạ model sau 3 lần lỗi"**.
     - Hệ thống sẽ tự ưu tiên model Gemini text mới nhất (có thể bấm **Đồng bộ model mới nhất từ Google**); nếu model đó gặp lỗi 3 lần liên tiếp (hết quota/rate limit/quá tải/404/timeout), backend tự động hạ sang model kế tiếp trong chuỗi dự phòng.
   - **OpenAI:** Dùng OpenAI Platform API key lấy tại `platform.openai.com/api-keys` (lưu ý: không dùng tài khoản ChatGPT/Codex).
   - **Anthropic Claude:** Dùng API key tại `console.anthropic.com`.
   - **Mock Provider (0đ):** Không cần API key — dùng khi muốn test toàn bộ luồng SEO offline không tốn phí API.
3. Bấm **Lưu cấu hình** → sau đó bấm **Kiểm tra kết nối** để xác nhận kết nối thành công.

### Bảo mật API Key
- API key được lưu an toàn trong **OS Keychain** (macOS Keychain / Windows Credential Locker / Linux SecretService).
- Nếu máy không có Keychain khả dụng, có thể truyền qua biến môi trường trước khi chạy `npm run dev`:
  - `GEMINI_API_KEY` (hoặc `FINZ_GEMINI_API_KEY`)
  - `OPENAI_API_KEY` (hoặc `FINZ_OPENAI_API_KEY`)
  - `ANTHROPIC_API_KEY` (hoặc `FINZ_CLAUDE_API_KEY`)
- **Tuyệt đối không lưu plaintext API key** vào SQLite, `localStorage`, log hay file export.

---

## 4. Hướng dẫn dùng nhanh quy trình 7 bước

1. **Quản lý dự án (`/projects`):** Tạo dự án mới cho bất kỳ Topic Pillar nào (`P01`, `P08`, `P25`, `Z42`…).
2. **Bước 01 — Thiết lập chủ đề:** Nhập tay hoặc upload file Excel/CSV chứa bảng Topic Pillar & Keywords (tự nhận diện header dù ở dòng 4 hay dòng 1) → chọn Topic Pillar & Mã nội dung → bấm **Điền vào form** → bổ sung Mục tiêu kinh doanh & Đối tượng độc giả → **Lưu vào SQLite**.
3. **Bước 02 — Bản đồ nhu cầu AI:** Bấm **AI phân tích nhu cầu** để nhận nhóm nhu cầu kèm bằng chứng, phản biện mạnh nhất, dữ liệu thiếu và đề xuất báo cáo Semrush.
4. **Bước 03 — Yêu cầu Semrush:** Đọc hoặc sao chép hướng dẫn từng bước để tự xuất báo cáo CSV/XLSX trên giao diện Semrush của bạn (không cần API/MCP/mật khẩu Semrush).
5. **Bước 04 — Tải file & ghép cột:** Chọn đúng phiếu yêu cầu, chọn định dạng số (`vi-VN` cho `9.900` hoặc `en-US` cho `9,900`), kiểm tra preview & cột ghép (hỗ trợ cả báo cáo metrics và `ORGANIC_RESULTS`) → bấm **Xác nhận import**.
6. **Bước 05 — Kiểm tra dữ liệu & AI Critic:** Xem Quality Gates (`F0–F7`, `E0–E2`), chạy **AI Critic sau Semrush** (tối đa 2 lượt/chu kỳ, có thể duyệt tạo yêu cầu bổ sung hoặc mở chu kỳ mới).
7. **Bước 06 — Kế hoạch bài viết & Keyword Mapping:** Lập mapping dựa trên bằng chứng (tách riêng bài `ARTICLE` với `TOOL`/`DOWNLOAD`/`SERVICE`; gắn `SERP_NOT_VERIFIED` nếu chưa có `ORGANIC_RESULTS`) → vào **Chờ phê duyệt (`/approvals`)** để duyệt các quyết định quan trọng.
8. **Bước 07 — SEO Content Brief & Xuất:** Tạo bản Brief **CHÍNH THỨC** (khi đã duyệt + đạt đủ gate) hoặc bản **DỰ THẢO** (`SERP_NOT_VERIFIED`) gồm đầy đủ 13 công thức viết & 16 chiến thuật cấp toàn bài → xuất **XLSX (3 sheet)**, **CSV**, **JSON** hoặc **Bản in HTML**.

---

## 5. Cập nhật phiên bản mới & chạy kiểm thử

Khi có bản cập nhật mới trên GitHub:

```bash
git pull origin main
npm run dev
```

Chạy bộ kiểm thử tự động (Backend pytest + Frontend TypeScript check):

```bash
npm test
npm run build:web
```

---

## 6. Xử lý các lỗi thường gặp khi cài lại

| Vấn đề | Nguyên nhân & Cách xử lý |
| :--- | :--- |
| **`python3 not found` / không tìm thấy Python** | Cài Python 3.11+ từ `python.org`. Trên Windows nhớ tick **Add python.exe to PATH**, sau đó mở lại Terminal mới. |
| **Trùng cổng `3000` hoặc `8000` (`EADDRINUSE`)** | Tắt ứng dụng khác đang dùng cổng đó, hoặc chạy với cổng tùy chỉnh:<br>`FINZ_WEB_PORT=3001 FINZ_API_PORT=8001 npm run dev` |
| **macOS hỏi mật khẩu Keychain khi lưu/đọc API key** | Bấm **Always Allow (Luôn cho phép)** để ứng dụng đọc key từ macOS Keychain mượt mà mà không cần lưu plaintext. |
| **Cài bị lỗi giữa chừng do mạng chập chờn** | Xóa thư mục `services/api/.venv` và `apps/web/node_modules`, sau đó chạy lại `npm run dev` để script cài lại sạch sẽ. |
| **Muốn sao lưu dữ liệu sang máy khác** | Copy thư mục `data/` (gồm `finz_workbench.sqlite3`, `uploads/`, `backups/`, `exports/`). Hoặc dùng nút **Backup an toàn** trong trang `/projects` (file JSON xuất ra hoàn toàn không chứa API key). |

---

## 7. Cấu trúc thư mục chính

```text
Finz/
├── package.json            # Chứa lệnh `npm run dev`, `npm run setup`, `npm test`
├── scripts/dev.mjs         # Script khởi động tự động cả Backend + Frontend
├── services/api/           # Backend FastAPI + SQLAlchemy + Alembic + AI Gateway
├── apps/web/               # Frontend Next.js 15 + TypeScript + Tailwind (Dark Mode)
├── docs/DEVELOPMENT_LOG.md # Nhật ký phát triển
└── data/                   # (Tự sinh khi chạy, không push lên Git) SQLite DB, uploads, backups, exports
```
