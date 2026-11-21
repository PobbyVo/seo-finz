# FINZ-16-QA-R2 — Rủi Ro Còn Lại & Phạm Vi Chưa Kiểm Thử

1. **Nhà cung cấp AI trả phí trong R2 (`LIVE_NOT_TESTED`):**
   - Toàn bộ bài test tự động `pytest`, Browser E2E và GitHub Actions CI trong R2 chạy với `MockAdapter` (`MOCK`, `FINZ_SECRET_BACKEND=memory`, 0 chi phí API). OpenAI, Anthropic Claude và luồng AI Analyst/Critic dài bằng Gemini key thật không được gọi tự động trong R2 (lần ping kết nối live Gemini duy nhất thuộc R1 theo ủy quyền chủ dự án).
2. **Thao tác xuất file trực tiếp trên web Semrush (`NOT_RUN`):**
   - Đúng phạm vi thủ công của FinZ V1.6; đã replay bằng fixture Semrush CSV thật từ R1 (15 metrics + 104 SERP gồm 5 AI Overview) và các bộ fixture đối kháng R2.
3. **Môi trường hệ điều hành Windows & Linux Keychain (`PARTIAL`):**
   - Logic phân giải URL SQLite kiểu Windows (`C:/...`) đã được kiểm thử bằng unit test trên macOS và Linux CI (`ubuntu-latest`), nhưng chưa chạy trực tiếp trên Windows runner thật hay kiểm thử Windows Credential Locker / Linux SecretService với GUI keyring.
4. **ESLint script `apps/web` (`next lint`):**
   - Chạy thực tế `npm --prefix apps/web run lint` xác nhận Next.js 15 nhắc tương tác cấu hình ESLint vì dự án chưa tạo `.eslintrc` (đồng thời thông báo `next lint` deprecated trong Next 16). Do đó CI sử dụng trung thực `tsc --noEmit` + `next build` và không giả mạo cổng lint.
5. **Bố cục mobile 320px trang Bước 07:**
   - Trên Chrome Headless, tất cả 9 màn hình đạt `noOverflow: true` (`scrollWidth <= innerWidth + 2`), riêng `/steps/07-brief` ở viewport `320px` có `innerWidth=355` do chuỗi dài không ngắt dòng làm trình duyệt tự scale nhẹ từ 320→355 (vẫn không tràn ngang). Có thể tinh chỉnh thêm CSS `break-all` ở vòng UI nhỏ sau nếu cần hiển thị chặt đúng 320px không scale.
6. **Chính sách chọn snapshot khi batch mới bị thiếu (`F05`):**
   - Policy `v1.6.2` áp dụng nguyên tắc **an toàn fail-closed**: snapshot mới nhất luôn là nguồn sự thật hiện hành; nếu người dùng tải lên một file SERP mới bị thiếu (1–2 URL) cho cùng từ khóa, hệ thống hạ trạng thái từ khóa đó xuống `PARTIAL_SERP_EVIDENCE` và yêu cầu bổ sung thay vì âm thầm giữ trạng thái xanh cũ.
7. **Phân tách quyền phê duyệt:**
   - Kết quả **`PASS`** của kiểm thử tự động và CI chỉ xác nhận các cổng kiểm soát bằng chứng, toàn vẹn dữ liệu và UI hoạt động đúng kỹ thuật — **không thay thế** quyết định phê duyệt nghiệp vụ SEO của chuyên viên.
