# Nghiệm thu FinZ SEO Workbench V2.0 — 23/11/2026

## Thay đổi theo 5 giai đoạn

| Giai đoạn | Nhánh | File chính và mục đích | Kiểm tra tại thời điểm hoàn tất giai đoạn |
|---|---|---|---|
| 1. Đầu vào | `upgrade/v2-01-input` | `taxonomy_parser.py`, `topic_source.py`, `models.py`, migration `0004_v2_source_metadata`: alias Bộ key, NFC, metadata nguồn và F0 theo dòng/cột; hai fixture P01 | 36 test, TypeScript và build web đạt |
| 2. Playbook | `upgrade/v2-02-playbook` | `knowledge/`, `gateway.py`, `settings_knowledge.py`, `KnowledgeSettings.tsx`: tri thức tài chính, ngưỡng runtime, hash prompt và Settings | 38 test, TypeScript và build web đạt |
| 3. Nghiên cứu | `upgrade/v2-03-research` | Schema/phạm vi pillar, mapping engine, parser Semrush, research routes, UI bước 01/03: nhiều mã nội dung, phiếu VN, ưu tiên dùng Volume/KD và dữ liệu từng dòng cho Critic | 39 test, TypeScript và build web đạt |
| 4. Viết brief | `upgrade/v2-04-brief-writer` | `brief_writer.py`, prompts/adapters, brief engine, F7: schema, ví dụ tham khảo, Mock, sửa lỗi và fallback có nhãn | 41 test, TypeScript và build web đạt |
| 5. Xuất và nghiệm thu | `upgrade/v2-05-exports` | Exporter 5 sheet; bàn giao nghiên cứu; bổ sung đầy đủ F1/F2/F3, đọc SERP an toàn, nhãn do người sửa, xử lý riêng dòng, mã brief ổn định, nhật ký và tài liệu | 55 test, TypeScript và build web đạt |

Các nhánh nối tiếp nhau; review/merge theo thứ tự. Giai đoạn 5 bao gồm các bổ sung tích hợp sau nghiệm thu P01, không chỉ thay bố cục XLSX. Không tự merge vào `main`.

## Bằng chứng nghiệm thu

- `npm test`: **55 passed**; TypeScript `tsc --noEmit` đạt. Có một cảnh báo deprecation từ FastAPI TestClient/httpx hiện có.
- `npm run build:web`: build production thành công, xuất đủ 15 route.
- Chrome headless: chụp 7 màn hình, không có `pageerror`. Backend QA dùng SQLite tạm riêng; không sửa dữ liệu làm việc của người dùng.
- Cả `bo_key_p01.tsv` và `bo_key_p01_original.tsv`: 1 pillar, 2 mã nội dung, 12 keyword; key chính là “lương gross net là gì” và “cách deal lương”.
- Mock Analyst đọc cả hai mã. Phiếu gồm 1 Overview lô 12 key, 2 Related, 2 Questions và 2 SERP. Chạy lại giữ ID phiếu.
- Lượt 2 dùng nguyên `semrush_metrics_real_sample.csv` và `semrush_serp_real_sample.csv`: key gross/net có **Volume 140, KD 20 → P2** theo ngưỡng đề xuất; không nâng bài đầu tiên thành P1. File SERP không cần Keyword/Title, gắn được qua tên file khớp nguồn.
- Hai brief có outline khác nhau; công cụ tính gross/net nằm ở Backlog. Thiếu số hoặc chưa duyệt không được coi là brief chính thức.
- Chạy lại một dòng giữ ID, mã bài và phê duyệt khi fingerprint/bằng chứng không đổi. Khi import thay đổi bằng chứng, bộ test cũ tiếp tục kiểm việc hết hiệu lực phê duyệt/brief/export.
- Keyword phụ mới từ Related chỉ thêm vào nguồn sau phê duyệt rõ ràng; không thay key chính. Gửi lại cùng quyết định bị từ chối.
- JSON/schema brief hỏng: retry đúng 1 lần rồi trả bản dự phòng `DRAFT`, `NEEDS_HUMAN_EDIT`, `generation_source=FALLBACK`. F7 kiểm Title, Meta, key phụ, link, nguồn pháp lý, chiến thuật và outline trùng.
- Đọc trang: chặn IP nội bộ, DNS hỗn hợp và redirect về nội bộ; kết nối TLS ghim IP công khai đã kiểm tra. Trang lỗi ghi “Không đọc được”.
- Link “Xem Brief” được test trỏ đúng dòng tiêu đề khối, không dùng offset cố định.

## Ảnh UI và file mẫu

- [Nguồn chủ đề](01-source.png)
- [Settings/ngưỡng](02-settings.png)
- [Phiếu Semrush](03-tickets.png)
- [Phân tích SERP](04-serp.png)
- [Mapping và bàn giao](05-mapping.png)
- [Brief](06-brief.png)
- [Nhật ký](07-logs.png)
- [XLSX P01 từ Mock và file Semrush mẫu — DỰ THẢO](P01-Luong-Mock-DRAFT.xlsx)

## Giới hạn kiểm chứng và quyết định cần chốt

Chưa gọi Gemini/OpenAI/Claude bằng API key thật trong lần nâng cấp này; các adapter được kiểm bằng Mock và giả lập lỗi như bộ test cũ. Đọc trang ngoài được kiểm về bảo mật bằng unit test, không coi là đã nghiên cứu live SERP hay xác minh văn bản pháp luật hiện hành. File XLSX mẫu là bản nháp nghiệm thu.

Các ngưỡng vẫn là **đề xuất — chờ sếp chốt**. P0 chưa có quy tắc xếp hạng được chốt; cờ cấu hình không tự tạo bài P0. Cho phép nháp chưa duyệt, số vòng sửa/bổ sung và đọc website ngoài đều do Settings kiểm soát. Văn bản, hiệu lực và tỷ lệ pháp lý phải được biên tập viên kiểm trước khi xuất bản bài.
