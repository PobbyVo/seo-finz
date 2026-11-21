# FINZ-16-QA-R1 — Rủi Ro Còn Lại & Phạm Vi Chưa Kiểm Thử

1. **Nhà cung cấp AI trả phí chưa kiểm thử trực tiếp (`LIVE_NOT_TESTED`)**:
   - **OpenAI** và **Anthropic Claude** chỉ được kiểm thử qua `httpx.MockTransport` (`MOCK`), chưa chạy request thật bằng key trả phí.
   - **Google Gemini** đã xác minh trực tiếp 1 lượt `test_connection()` bằng key chủ dự án cung cấp (kết nối thành công `gemini-3.5-flash-lite` sau 8 bước tự hạ bậc 3/3 lỗi), nhưng toàn bộ bộ test tự động Analyst/Critic vẫn chạy ở chế độ `MOCK`.
2. **Thao tác xuất file trực tiếp trên giao diện Semrush UI (`NOT_RUN`)**:
   - Đã kiểm thử bằng 2 file CSV Semrush thực tế do chủ dự án cung cấp (`Keyword,Volume,Keyword Difficulty` và `Position,Type,Domain,URL,...` có cả `AI Overview` và `Organic`), nhưng không tự động đăng nhập/xuất trực tiếp trên web Semrush (đúng phạm vi MVP).
3. **Ngưỡng đủ bằng chứng SERP (`MIN_ORGANIC_URLS_FOR_SERP_VERIFIED = 3`)**:
   - Chính sách `v1.6.1` phân biệt rõ `SERP_NOT_VERIFIED` (0 URL), `PARTIAL_SERP_EVIDENCE` (1–2 URL — chặn OFFICIAL), `SERP_VERIFIED` (≥3 URL organic hợp lệ cho đúng từ khóa & thị trường — cho phép OFFICIAL nhưng ghi rõ chưa đủ Top 10) và `TOP_10_VERIFIED` (đủ đủ 10 vị trí 1–10). Nếu team SEO muốn siết buộc đủ cả 10 vị trí 1–10 cho mọi bài OFFICIAL, chỉ cần điều chỉnh hằng số tại `services/api/app/domain/eligibility_policy.py`.
4. **Hành vi OS Keychain đa nền tảng (`PARTIAL`)**:
   - Đã chạy kiểm thử secret store ở chế độ memory (pytest) và macOS Keychain trên máy dev; Windows Credential Locker và Linux SecretService chưa kiểm thử trực tiếp trên máy thật của các HĐH đó.
5. **Bản sao lưu DB local (`data/backups/`)**:
   - Đã tránh tạo backup lặp lại mỗi lần chạy `npm run dev` khi DB đã ở `head`, nhưng hệ thống chủ động **không tự xóa** các file backup cũ do người dùng sở hữu; log cảnh báo dung lượng sẽ xuất hiện nếu thư mục `data/backups/` vượt 500 MB.
6. **Quyền phê duyệt nghiệp vụ SEO**:
   - Trạng thái `PASS` của bộ kiểm thử tự động xác nhận phần mềm tuân thủ đúng Quality Gates và an toàn dữ liệu; **không thay thế** quyết định phê duyệt SEO của chuyên viên trên dự án thật.
