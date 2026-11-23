# Hướng dẫn sử dụng FinZ SEO Workbench V2.0

Tài liệu dành cho người trực tiếp nghiên cứu SEO và bàn giao Content Brief. Bạn sẽ đi từ một chủ đề và bộ từ khóa đầu vào đến Keyword Mapping đã được xem xét, rồi xuất tài liệu cho người viết bài.

Ứng dụng chạy trên máy của bạn. AI hỗ trợ phân tích và phản biện; bạn quyết định thay đổi keyword chính, mở chủ đề mới và phê duyệt mapping. Volume, KD và bằng chứng SERP phải đến từ file Semrush thực tế.

## Mục lục

- [Chuẩn bị và mở ứng dụng](#chuan-bi)
- [Cấu hình AI lần đầu](#cau-hinh-ai)
- [Tạo và chọn dự án](#tao-du-an)
- [Bước 01 — Thiết lập chủ đề](#buoc-01)
- [Bước 02 — Phân tích nhu cầu bằng AI](#buoc-02)
- [Bước 03 — Lấy báo cáo Semrush](#buoc-03)
- [Bước 04 — Tải file và ghép cột](#buoc-04)
- [Bước 05 — Kiểm tra dữ liệu và chạy AI Critic](#buoc-05)
- [Bước 06 — Lập và phê duyệt Keyword Mapping](#buoc-06)
- [Bước 07 — Tạo Content Brief và xuất file](#buoc-07)
- [Cập nhật dữ liệu và sao lưu](#sao-luu)
- [Xử lý tình huống thường gặp](#xu-ly-loi)
- [Checklist cho mỗi dự án](#checklist)

<a id="chuan-bi"></a>

## Chuẩn bị và mở ứng dụng

Chuẩn bị trước:

- Chủ đề cần nghiên cứu, keyword chính và các keyword phụ đang có.
- Mục tiêu kinh doanh và đối tượng độc giả cụ thể.
- File Excel/CSV Topic Pillar & Keywords nếu đã có. Bạn cũng có thể nhập tay.
- Quyền truy cập Semrush để tự xuất báo cáo khi làm nghiên cứu thực tế.
- API key của nhà cung cấp AI bạn chọn, hoặc dùng **Mock Provider (0đ)** để làm quen thao tác.

### Mở tool trên máy hiện tại

1. Mở Terminal.
2. Chạy lần lượt:

   ```bash
   cd /Users/vodaiphuoc/Documents/finzacademy-2.0
   npm run dev
   ```

3. Giữ cửa sổ Terminal này mở. Lần đầu, chương trình tự thiết lập thư viện và cơ sở dữ liệu; cần kết nối mạng để tải thư viện.
4. Khi frontend đã khởi động, mở [http://127.0.0.1:3000](http://127.0.0.1:3000). Nếu trang chưa lên ngay, đợi quá trình khởi động hoàn tất rồi tải lại.
5. Khi kết thúc buổi làm việc, nhấn **Ctrl + C** trong Terminal để dừng ứng dụng.

Nếu chuyển sang máy mới, xem phần cài đặt trong [README](../README.md). Dự án yêu cầu Node.js từ phiên bản 20 và Python từ phiên bản 3.11.

### Nhận biết các khu vực trên giao diện

| Khu vực | Dùng để làm gì |
| --- | --- |
| **Dự án đang hoạt động** ở thanh bên | Chọn dự án bạn đang thao tác. Luôn kiểm tra mã dự án trước khi import hoặc phê duyệt. |
| **Tổng quan** | Xem tiến độ, điểm nghẽn và hành động tiếp theo. |
| Các mục **01–07** | Thực hiện luồng nghiên cứu SEO. |
| **Chờ phê duyệt** | Xem và quyết định các đề xuất cần người duyệt. |
| **Nhật ký hệ thống** | Xem lượt chạy AI, model thực tế, sự kiện và lịch sử phiên bản. |
| **Settings → AI Providers** | Chọn AI, lưu API key và kiểm tra kết nối. |

Sau một số thao tác lưu thành công, hộp thoại sẽ tự chuyển bước sau khoảng **1,8 giây**. Bấm **Ở lại bước này** hoặc nhấn **Esc** nếu muốn đọc lại; bấm **Đi tiếp ngay** để chuyển ngay.

<a id="cau-hinh-ai"></a>

## Cấu hình AI lần đầu

Mở **Settings → AI Providers** ở cuối thanh bên, hoặc truy cập [trang cấu hình AI](http://127.0.0.1:3000/settings/ai).

### Cách làm quen không cần API key

1. Chọn **Mock Provider (0đ)**.
2. Giữ tùy chọn đặt provider này làm nhà cung cấp đang hoạt động.
3. Bấm **Lưu cấu hình**.
4. Bấm **Kiểm tra kết nối** và kiểm tra trạng thái `CONNECTED`.

Mock mô phỏng đầu ra phân tích để bạn tập thao tác, không gọi dịch vụ AI trả phí. Mock không tạo dữ liệu Semrush và không thay thế nghiên cứu thực tế.

### Cách cấu hình Google Gemini

1. Chọn **Google Gemini**.
2. Dán API key của bạn vào ô **API Key** theo chỉ dẫn trên màn hình.
3. Giữ bật **Tự động lấy model Gemini mới nhất (Auto-Latest)**.
4. Giữ ngưỡng **Tự hạ model sau 3 lần lỗi**.
5. Giữ **Dùng chung một model cho cả AI Topic Analyst & AI SEO Critic** nếu chưa cần cấu hình nâng cao.
6. Giữ endpoint chính thức được điền sẵn và chọn đặt Gemini làm nhà cung cấp đang hoạt động.
7. Bấm **Lưu cấu hình**, sau đó **Kiểm tra kết nối**.
8. Kiểm tra nhãn **ĐANG DÙNG**, trạng thái kết nối và mục **Model đang dùng**.

Khi đã có key, bạn có thể bấm **Đồng bộ model mới nhất từ Google**. Với các lỗi phù hợp cơ chế dự phòng như quota, quá tải, model không khả dụng hoặc timeout, Gemini sẽ hạ sang model tiếp theo sau 3 lỗi liên tiếp. Xem model thực tế và lý do hạ model trong **Nhật ký hệ thống**.

OpenAI và Anthropic Claude cũng được cấu hình tại màn hình này: chọn provider, nhập API key và Model ID được tài khoản hỗ trợ, lưu rồi kiểm tra kết nối. Các lệnh kiểm tra kết nối và phân tích bằng provider thật có thể phát sinh chi phí API.

API key được quản lý qua OS Keychain hoặc biến môi trường phía server. Chỉ nhập key vào màn hình cấu hình AI; không đưa key vào file chủ đề, file Semrush, ghi chú phê duyệt hay tài liệu bàn giao. Nếu máy không hỗ trợ Keychain, xem phần cấu hình biến môi trường trong [README](../README.md).

**Hoàn tất khi:** provider bạn chọn có nhãn **ĐANG DÙNG** và kiểm tra kết nối thành công.

<a id="tao-du-an"></a>

## Tạo và chọn dự án

1. Mở [trang quản lý dự án](http://127.0.0.1:3000/projects), hoặc bấm **Tạo dự án SEO đầu tiên** khi chưa có dự án.
2. Trong **Tạo dự án mới**, nhập mã và tên dự án.
3. Điền Pillar lớn, keyword chính, thị trường, mục tiêu kinh doanh và đối tượng độc giả.
4. Bấm **Tạo dự án & lưu SQLite**.
5. Kiểm tra mã dự án ở đầu màn hình và ô **Dự án đang hoạt động**.

Ví dụ thông tin đầu vào để tập thao tác dưới đây chỉ minh họa cách điền form, không chứa số liệu SEO:

| Trường | Ví dụ |
| --- | --- |
| Mã dự án / Topic Pillar | `P08` — dùng mã khác nếu đã tồn tại |
| Tên dự án / Topic Pillar | Lương gross và net |
| Pillar lớn | Tiền lương và nhân sự |
| Keyword chính gốc | lương gross và net |
| Thị trường | `VN` |
| Mục tiêu kinh doanh | Thu hút người đọc quan tâm kiến thức tiền lương và đăng ký nhận tài liệu |
| Đối tượng độc giả | Nhân viên văn phòng và người làm nhân sự |

Để tiếp tục dự án cũ, chọn tại ô **Dự án đang hoạt động**, hoặc bấm **Chọn dự án này** trong danh sách dự án. Sau đó mở bước cần làm ở thanh bên.

<a id="buoc-01"></a>

## Bước 01 — Thiết lập chủ đề

Mở **01. Thiết lập chủ đề** — [mở màn hình](http://127.0.0.1:3000/steps/01-topic).

### Cách A — Nhập trực tiếp

1. Nhập **Mã Topic Pillar**, **Tên Topic Pillar** và **Keyword chính**.
2. Bổ sung Pillar, Loại topic, Trục chia và Chủ đề chính nếu có.
3. Điền **Mã nội dung**, **Tiêu đề dự kiến** nếu đã lên khung bài.
4. Nhập keyword phụ, ngăn cách bằng dấu phẩy hoặc xuống dòng.
5. Điền **Mục tiêu kinh doanh** và **Đối tượng độc giả**. Đây là thông tin cần có để đủ điều kiện tạo brief chính thức.
6. Kiểm tra **Thị trường** và **Ngôn ngữ**, ví dụ `VN` và `vi`.
7. Giữ mục tiêu mềm **5–7 bài ARTICLE**, hoặc điều chỉnh theo phạm vi công việc.
8. Bấm **Lưu cấu hình vào SQLite**.

### Cách B — Nhập từ Excel hoặc CSV

1. Bấm **Chọn file .XLSX / .CSV**.
2. Đọc bản xem trước: tên file, sheet, dòng tiêu đề và cảnh báo.
3. Chọn đúng **Topic Pillar** và **Mã nội dung**.
4. Bấm **Điền vào form**.
5. Kiểm tra lại các trường vừa điền, đặc biệt keyword chính, mục tiêu kinh doanh và độc giả.
6. Bấm **Xác nhận nhập file & Lưu SQLite**.

**Chọn file** mới tạo bản xem trước; **Điền vào form** mới điền dữ liệu vào biểu mẫu. Bạn cần bấm nút lưu cuối cùng để xác nhận dữ liệu nghiệp vụ.

Nếu chuẩn bị một workbook mới, có thể tổ chức 2 sheet theo các tên cột được hỗ trợ:

| Sheet gợi ý | Các cột |
| --- | --- |
| `Topic Pillar` | `topic_pillar_code`, `topic_pillar_name`, `pillar`, `topic_type`, `split_axis`, `main_topic` |
| `Keywords` | `topic_pillar_code`, `content_code`, `content_title`, `primary_keyword`, `secondary_keywords` |

Mã `topic_pillar_code` trong hai bảng cần khớp nhau. Nên đặt tiêu đề cột ở dòng đầu, tránh gộp ô trong vùng dữ liệu. Tool cũng nhận diện được một số tên cột tiếng Việt và tìm tiêu đề trong 15 dòng đầu.

Nếu bạn thay keyword chính đã lưu, hệ thống có thể tạo quyết định chờ duyệt. Mở **Chờ phê duyệt**, đọc giá trị gốc và đề xuất rồi quyết định trước khi tiếp tục với keyword mới.

**Hoàn tất khi:** có xác nhận lưu thành công, thông tin dự án đúng và mọi thay đổi keyword chính cần duyệt đã được xử lý.

<a id="buoc-02"></a>

## Bước 02 — Phân tích nhu cầu bằng AI

Mở **02. Bản đồ nhu cầu AI** — [mở màn hình](http://127.0.0.1:3000/steps/02-demand-map).

1. Bấm **AI phân tích nhu cầu** và chờ hoàn tất.
2. Đọc thông báo provider và model thực tế đã chạy.
3. Với mỗi nhóm nhu cầu, kiểm tra người tìm kiếm muốn gì, keyword seed và loại trang giả định.
4. Đọc **Bằng chứng ủng hộ & nguồn**, **Phản biện mạnh nhất**, **Dữ liệu cần bổ sung** và **Hành động tiếp theo**.
5. Tích các nhóm bạn muốn nghiên cứu. Bỏ chọn nhóm không phù hợp trước khi tạo phiếu.
6. Bấm **Tạo yêu cầu Semrush (... nhóm đã chọn)**.

Nếu có ứng viên keyword mở rộng, bạn có thể bấm **Đưa vào Bản đồ nhu cầu** hoặc **Chuyển Chờ phê duyệt** để xem xét đề xuất. Với chủ đề mới hoặc thay đổi phạm vi quan trọng, xử lý quyết định tại **Chờ phê duyệt**.

Search Intent và loại trang ở bước này là giả định của AI. Hãy dùng dữ liệu Semrush ở các bước tiếp theo để kiểm chứng.

**Hoàn tất khi:** đã đọc phản biện, chọn nhóm cần nghiên cứu và tạo được các phiếu Semrush.

<a id="buoc-03"></a>

## Bước 03 — Lấy báo cáo Semrush

Mở **03. Yêu cầu Semrush** — [mở màn hình](http://127.0.0.1:3000/steps/03-semrush).

1. Mở từng phiếu, kiểm tra **Seed**, **Market**, mục đích và loại báo cáo.
2. Đọc **Hướng dẫn thao tác trên Semrush UI** của phiếu; có thể bấm **Sao chép hướng dẫn** để dùng khi chuyển cửa sổ.
3. Mở Semrush bằng tài khoản của bạn và lấy báo cáo theo phiếu. Chọn đúng keyword và cơ sở dữ liệu/thị trường tương ứng.
4. Xuất CSV hoặc XLSX và giữ lại file gốc.
5. Quay lại phiếu, bấm **Gửi file** để mở Bước 04 với phiếu đã chọn.
6. Lặp lại cho các phiếu còn lại.

| Loại báo cáo trong tool | Mục đích | Dữ liệu cần chú ý |
| --- | --- | --- |
| `KEYWORD_OVERVIEW` | Kiểm tra chỉ số từ khóa | Keyword, Volume, KD; Intent và CPC nếu có |
| `RELATED` | Nghiên cứu từ khóa liên quan | Keyword và các chỉ số đi kèm |
| `QUESTIONS` | Nghiên cứu câu hỏi | Câu hỏi/keyword và các chỉ số đi kèm |
| `ORGANIC_RESULTS` | Kiểm chứng kết quả tìm kiếm tự nhiên | URL, Position, Type; Keyword, Domain, Title nếu có |

Để thêm phiếu, nhập **Keyword seed**, chọn **Loại báo cáo**, điền **Mục đích nghiên cứu** rồi bấm **Tạo phiếu yêu cầu**.

Tool không đăng nhập Semrush thay bạn và không yêu cầu mật khẩu, API token hay MCP Semrush. Luồng làm việc dùng file xuất từ giao diện Semrush; không có bước nhập tay danh sách SERP.

**Hoàn tất khi:** bạn có file báo cáo thật cho các keyword cần đánh giá. Nếu chưa lấy được `ORGANIC_RESULTS`, bạn vẫn có thể làm kế hoạch và brief dự thảo với nhãn chưa xác minh SERP.

<a id="buoc-04"></a>

## Bước 04 — Tải file và ghép cột

Mở **04. Tải file & ghép cột** — [mở màn hình](http://127.0.0.1:3000/steps/04-upload).

1. Kiểm tra dự án đang hoạt động.
2. Chọn đúng **phiếu Yêu cầu Semrush**. Nếu tải file tự do, tự kiểm tra kỹ loại báo cáo và keyword mục tiêu.
3. Kiểm tra **Loại báo cáo** và **Thị trường file**.
4. Chọn **Định dạng số (Locale)** theo dữ liệu trong file:

   | Locale | Hàng nghìn | Thập phân |
   | --- | --- | --- |
   | `en-US` | `9,900` | `45.5` |
   | `vi-VN` | `9.900` | `45,5` |

5. Với `ORGANIC_RESULTS`, kiểm tra ô **Từ khóa SERP (khi CSV không có cột Keyword)**. Nhập đúng keyword đã dùng để xuất báo cáo; tránh để nhầm keyword mặc định của dự án.
6. Bấm **Chọn file CSV / XLSX từ Semrush**.
7. Kiểm tra tên file, sheet, tổng số dòng và 15 dòng mẫu.
8. Kiểm tra từng ô **Ánh xạ cột** theo bảng dưới.
9. Bấm **Xác nhận import toàn bộ ... dòng** và chờ thông báo kết quả.
10. Sang Bước 05 để kiểm tra dữ liệu đã chuẩn hóa; quay lại import các file còn lại.

| File đang nhập | Cách ghép cột |
| --- | --- |
| Metrics | Ghép `Keyword` vào Keyword, `Volume` vào Volume, `Keyword Difficulty` hoặc `KD` vào KD (%), Intent vào Search Intent. Keyword là cột bắt buộc của parser metrics. |
| Organic Results | Ghép `URL` vào URL Organic, `Position` vào Position / Thứ hạng và `Type` vào Type (Organic / AI Overview). URL là cột bắt buộc của parser organic; cần thứ hạng hợp lệ để chứng nhận SERP. |

Trong báo cáo SERP, cột **Type** phân biệt kết quả như `Organic` và `AI Overview`; nó không phải cột loại trang `ARTICLE`/`TOOL`. Hãy ghép vào đúng trường của tool.

Nếu chọn nhầm file hoặc thiết lập sai loại báo cáo/locale, bấm **Hủy bản xem trước**, sửa thiết lập và chọn lại file trước khi xác nhận. Bản xem trước chưa xác nhận không phải batch dữ liệu đã import.

Sau import, `PROCESS_COMPLETED` chỉ cho biết xử lý file đã hoàn tất. Tool vẫn phải kiểm tra bằng chứng, keyword, thị trường và điều kiện phê duyệt. Các dòng trùng được nhận diện, không cộng dồn Volume.

**Hoàn tất khi:** có batch đã import, số dòng được thông báo rõ và dữ liệu chuẩn hóa ở Bước 05 đúng với file nguồn.

<a id="buoc-05"></a>

## Bước 05 — Kiểm tra dữ liệu và chạy AI Critic

Mở **05. Kiểm tra & AI Critic** — [mở màn hình](http://127.0.0.1:3000/steps/05-evidence).

1. Xem tổng số dòng Metrics, bằng chứng Organic SERP và tỷ lệ bao phủ keyword nguồn.
2. Xem **Lịch sử Batch & Toàn vẹn nguồn**, kiểm tra loại báo cáo và thị trường của từng batch.
3. Mở tab **Keyword Metrics**: đối chiếu keyword, Volume, KD, Intent và cảnh báo trùng/thiếu dữ liệu.
4. Mở tab **Organic Results / SERP**: kiểm tra keyword, vị trí, URL, loại kết quả và các dòng bị loại khỏi Organic rank.
5. Bấm **Chạy AI Critic**.
6. Đọc bằng chứng ủng hộ, phản biện mạnh nhất, dữ liệu còn thiếu và hành động tiếp theo.
7. Nếu cần bổ sung, bấm **Duyệt yêu cầu nghiên cứu bổ sung**, rồi quay lại Bước 03 → 04 để lấy và import file thật.
8. Sau khi bổ sung, chạy Critic tiếp nếu còn lượt. Mỗi chu kỳ có tối đa **2 lượt**; bấm **Mở chu kỳ mới** khi cần nghiên cứu tiếp.
9. Bấm **Sang Bước 06 Mapping →** khi sẵn sàng lập kế hoạch, kể cả khi kế hoạch vẫn cần mang nhãn dự thảo.

Giá trị `null` hoặc **thiếu** có nghĩa là chưa có dữ liệu, khác với giá trị 0. Không tự điền Volume/KD ước lượng để vượt điều kiện. Keyword Volume thấp vẫn có thể được giữ để đánh giá theo giá trị kinh doanh.

**Hoàn tất khi:** bạn hiểu dữ liệu nào đã có, dữ liệu nào còn thiếu và đã xem kết luận Critic. Điểm nghẽn của từng mapping sẽ được hiển thị cụ thể ở Bước 06.

<a id="buoc-06"></a>

## Bước 06 — Lập và phê duyệt Keyword Mapping

Mở **06. Kế hoạch & Mapping** — [mở màn hình](http://127.0.0.1:3000/steps/06-mapping).

1. Bấm **Lập / Cập nhật Keyword Mapping**.
2. Xem từng dòng: keyword chính/phụ, loại trang, URL đề xuất, Volume/KD, nguồn dữ liệu và độ ưu tiên.
3. Đọc cột **Điểm nghẽn cụ thể & Hành động sửa**. Bấm liên kết khắc phục của từng lỗi để quay về bước cần bổ sung.
4. Kiểm tra số bài `ARTICLE`, tài nguyên phi bài viết và khoảng trống nghiên cứu.
5. Bấm **Mở Chờ phê duyệt** để xem các quyết định được tạo.

Mục tiêu **5–7 ARTICLE** là mục tiêu mềm. `TOOL`, `DOWNLOAD`, `SERVICE` và `PRODUCT` không tính vào số bài ARTICLE. Nếu chưa đủ nhu cầu độc lập hoặc bằng chứng, hãy giữ khoảng trống nghiên cứu để làm tiếp.

### Đọc trạng thái SERP của từng mapping

| Trạng thái | Ý nghĩa và cách xử lý |
| --- | --- |
| `SERP_NOT_VERIFIED` | Chưa có bằng chứng organic đủ điều kiện cho đúng keyword và thị trường. Bổ sung file `ORGANIC_RESULTS` ở Bước 03–04. |
| `PARTIAL_SERP_EVIDENCE` | Bằng chứng còn một phần, chưa đủ chứng nhận. Xem điểm nghẽn và bổ sung snapshot phù hợp. |
| `SERP_VERIFIED` | Đủ bằng chứng cơ bản theo chính sách hiện tại; chưa đồng nghĩa đã xác minh đủ Top 10. |
| `TOP_10_VERIFIED` | Đã kiểm chứng các vị trí organic 1–10 trong cùng snapshot cho đúng keyword và thị trường. |

Chính sách hiện tại yêu cầu tối thiểu **3 URL organic duy nhất có thứ hạng hợp lệ trong cùng một snapshot** để xác minh SERP cơ bản, cùng các kiểm tra toàn vẹn nguồn. Tool không ghép nhiều batch rời rạc để tuyên bố đủ Top 10. Một keyword đã xác minh không tự xác minh các keyword khác trong dự án.

### Duyệt quyết định

Tại [Chờ phê duyệt](http://127.0.0.1:3000/approvals):

1. Đọc loại quyết định, giá trị gốc, giá trị đề xuất, lý do, mức ảnh hưởng và bằng chứng.
2. Kiểm tra phạm vi `scope` và phiên bản mapping:

   | Phạm vi | Ý nghĩa |
   | --- | --- |
   | `RESEARCH_ONLY` | Cho phép tiếp tục nghiên cứu. Chưa đủ để phát hành brief chính thức. |
   | `BRIEF_ELIGIBILITY` | Phê duyệt phục vụ brief, gắn với đúng phiên bản mapping và bằng chứng hiện hành. Các gate khác vẫn phải đạt. |

3. Điền ghi chú nếu cần, rồi chọn **Phê duyệt**, **Yêu cầu bổ sung bằng chứng** hoặc **Từ chối**.
4. Quay lại Bước 06, kiểm tra trạng thái từng dòng và số mapping **ĐỦ ĐIỀU KIỆN**.

Nếu có `STALE_SUPERSEDED` hoặc yêu cầu duyệt lại, mapping/bằng chứng đã thay đổi. Kiểm tra và duyệt phiên bản hiện hành trước khi tạo brief chính thức. Bấm lập lại mapping cũng có thể tạo revision mới; nên hoàn thiện dữ liệu trước khi chốt duyệt.

**Hoàn tất khi:** mapping đã được xem xét, các quyết định cần thiết được xử lý và bạn biết dòng nào đủ điều kiện chính thức, dòng nào cần dự thảo.

<a id="buoc-07"></a>

## Bước 07 — Tạo Content Brief và xuất file

Mở **07. Content Brief & Xuất** — [mở màn hình](http://127.0.0.1:3000/steps/07-brief).

1. Tại **Chọn Mapping để tạo Content Brief**, tích các mapping muốn tạo.
2. Kiểm tra trạng thái đủ điều kiện hoặc danh sách mã chặn dưới mỗi keyword.
3. Chọn cách tạo:

   | Nút | Khi dùng |
   | --- | --- |
   | **Tạo Brief CHÍNH THỨC** | Tất cả mapping đang chọn đều đủ điều kiện và được duyệt theo phiên bản hiện hành. |
   | **Tạo Brief DỰ THẢO / Hỗn hợp** | Muốn làm tiếp khi một số mapping chưa đủ điều kiện. Mapping đạt điều kiện có thể thành chính thức; mapping còn thiếu vẫn là dự thảo. |

4. Nếu nút chính thức bị mờ, bỏ chọn các mapping chưa đủ điều kiện để tạo cho phần đã đạt, hoặc quay lại khắc phục các mã chặn.
5. Sau khi tạo, đọc từng brief: keyword, tiêu đề SEO, URL đề xuất, H1, meta description, intent, độc giả, mục tiêu, CTA, outline, checklist và internal links.
6. Đọc **Writing Strategy**: công thức chính, công thức bổ trợ, ý tưởng mở bài và chiến thuật thu hút độc giả áp dụng cấp toàn bài. Có thể mở **Thư viện 13 công thức & 16 chiến thuật** để tham khảo.
7. Kiểm tra nhãn **CHÍNH THỨC / DỰ THẢO**, phiên bản và cảnh báo brief cũ trước khi bàn giao.
8. Bấm nút xuất định dạng phù hợp:

   | Định dạng | Cách sử dụng |
   | --- | --- |
   | **Xuất XLSX (5 bảng)** | Dùng trong Excel hoặc tự tải lên Google Sheets. Có 5 sheet theo chủ đề: `Keyword Research`, `SERP Check`, `Keyword Mapping`, `Nhat ky`, `SEO Content Brief`. |
   | **CSV** | Dùng khi cần xử lý dữ liệu dạng bảng. |
   | **JSON** | Dùng khi cần dữ liệu có cấu trúc cho công cụ khác. |
   | **Bản in HTML** | Mở file bằng trình duyệt để đọc hoặc in; có thể dùng chức năng In → Lưu dưới dạng PDF của trình duyệt. |

Nút chọn mapping điều khiển việc **tạo brief**. Các nút xuất tạo bộ tài liệu theo **dự án**, không chỉ xuất các checkbox đang chọn. Nếu bộ brief có bản dự thảo hoặc bản đã cũ, tên file xuất sẽ mang nhãn `DRAFT`; hãy đọc trạng thái từng brief bên trong.

Tool tải file về máy, không tự ghi lên Google Sheets. Bảng mapping và brief là đề xuất bàn giao; bạn cần rà soát nội dung, URL, CTA và nguồn chuyên môn trước khi triển khai bài viết.

**Hoàn tất khi:** file đã tải xuống, mở được, có dữ liệu mong muốn và trạng thái phù hợp với mức bằng chứng của từng brief.

<a id="sao-luu"></a>

## Cập nhật dữ liệu và sao lưu

### Khi có báo cáo Semrush mới hoặc thay đổi đầu vào

1. Chọn đúng dự án.
2. Sửa đầu vào tại Bước 01 hoặc import báo cáo mới tại Bước 04.
3. Kiểm tra dữ liệu tại Bước 05 và chạy Critic khi cần.
4. Về Bước 06, xem lại mapping; lập/cập nhật nếu cần và xử lý phê duyệt phiên bản hiện hành.
5. Về Bước 07, tạo lại brief rồi xuất file mới.

Brief có nhãn **STALE** là bản đã cũ do đầu vào/mapping/bằng chứng thay đổi. Mục **Lịch sử các bản xuất** phân biệt bản hiện hành và bản lịch sử đã thay thế. Dùng **Tải lại bản hiện hành** cho công việc hiện tại; **Tải bản lịch sử (đã hết hiệu lực)** phục vụ đối chiếu.

### Sao lưu cuối buổi

1. Mở trang quản lý dự án.
2. Bấm **Backup an toàn** ở dự án cần lưu.
3. Kiểm tra thông báo sao lưu thành công. Tool tạo bản sao SQLite tại `data/backups/` và tải snapshot JSON của thông tin dự án về máy.
4. Nếu cần sao lưu đầy đủ hoặc chuyển máy, dừng ứng dụng bằng **Ctrl + C**, rồi sao chép toàn bộ thư mục `data/`, gồm cơ sở dữ liệu, uploads, backups và exports.

Snapshot JSON tải xuống không chứa toàn bộ file nguồn và cơ sở dữ liệu; không dùng riêng file đó thay cho bản sao lưu đầy đủ. API key không nằm trong bản sao dữ liệu, nên cần cấu hình lại AI trên máy mới. Giao diện hiện tại không có nút khôi phục toàn bộ dự án từ snapshot JSON.

<a id="xu-ly-loi"></a>

## Xử lý tình huống thường gặp

| Tình huống | Thao tác tiếp theo |
| --- | --- |
| Không mở được tool | Kiểm tra Terminal còn chạy `npm run dev`; đợi frontend khởi động xong rồi tải lại `http://127.0.0.1:3000`. |
| Báo cổng 3000 hoặc 8000 đang được dùng | Dừng phiên tool cũ bằng Ctrl + C. Nếu cần đổi cổng trên macOS: chạy `FINZ_WEB_PORT=3001 FINZ_API_PORT=8001 npm run dev`, rồi mở `http://127.0.0.1:3001`. |
| Chưa chọn dự án hoặc dữ liệu không như mong đợi | Kiểm tra mã tại **Dự án đang hoạt động**. Về Tổng quan, bấm **Làm mới trạng thái thật**. |
| Đã chọn file nhưng chưa thấy dữ liệu | Hoàn tất nút xác nhận lưu ở Bước 01 hoặc **Xác nhận import toàn bộ ... dòng** ở Bước 04. |
| Volume/KD sai dấu hoặc sai độ lớn | Đối chiếu file gốc với locale. Trước xác nhận, hủy preview và chọn lại đúng locale. Nếu đã import, import lại đúng dữ liệu rồi kiểm tra mapping và yêu cầu duyệt lại. |
| Thiếu Volume/KD hoặc `F1_METRICS_MISSING` | Lấy báo cáo có đúng keyword và thị trường, kiểm tra ghép cột ở Bước 04. Giữ nhãn dự thảo khi chưa có bằng chứng. |
| Có file SERP nhưng vẫn chưa xác minh | Kiểm tra keyword mục tiêu, market, URL, Position, Type, số URL hợp lệ và trạng thái toàn vẹn của cùng snapshot. Xem điểm nghẽn từng dòng ở Bước 06. |
| Chưa có file Organic Results | Tiếp tục bằng brief dự thảo có nhãn `SERP_NOT_VERIFIED`; bổ sung báo cáo qua Bước 03–04 khi có. |
| `F0_PROJECT_CONTEXT_INCOMPLETE` | Về Bước 01, bổ sung chủ đề, keyword chính, mục tiêu kinh doanh và độc giả; lưu lại. |
| `F2_IMPORT_INTEGRITY_FAILED` | Xem cảnh báo batch và file nguồn. Import lại file gốc đáng tin cậy qua Bước 04; kiểm tra và phê duyệt lại khi được yêu cầu. |
| Đã duyệt nhưng nút brief chính thức vẫn bị mờ | Kiểm tra scope `BRIEF_ELIGIBILITY`, revision hiện hành, bằng chứng mới và các mapping đang tích. Mọi mapping trong lựa chọn đều phải đạt điều kiện. |
| `EVIDENCE_UPDATED_REAPPROVAL_REQUIRED` hoặc `STALE_SUPERSEDED` | Mở **Chờ phê duyệt**, xem và duyệt lại phiên bản hiện hành sau khi đối chiếu bằng chứng. |
| Critic đã đủ 2 lượt | Bổ sung dữ liệu cần thiết rồi bấm **Mở chu kỳ mới** để nghiên cứu tiếp. |
| AI không kết nối hoặc hết quota | Kiểm tra provider đang hoạt động, key và trạng thái tại Settings; xem mã lỗi trong Nhật ký. Nếu chỉ cần tập thao tác, chuyển sang Mock rồi lưu cấu hình. |
| Lưu key thất bại | Kiểm tra quyền truy cập OS Keychain; nếu không khả dụng, dùng cấu hình biến môi trường theo README. |
| Không tải được file xuất | Kiểm tra đã tạo brief cho mapping mong muốn, đọc thông báo lỗi và thử lại. Nếu tải bản cũ đã hết hiệu lực, dùng đúng liên kết bản lịch sử. |
| File quá lớn | Giới hạn mặc định là 15 MiB và 25.000 dòng. Chọn báo cáo gọn hơn; khi chia file metrics, giữ nguyên nguồn dữ liệu. Với SERP, mỗi snapshot dùng để chứng nhận phải tự đủ bằng chứng, không ghép nhiều batch để đủ Top 10. |

Khi cần kiểm tra sâu hơn, mở **Nhật ký hệ thống → Làm mới**. Ghi lại mã dự án, bước đang làm, thao tác gây lỗi và mã lỗi; không đưa API key vào ảnh chụp hoặc nội dung gửi hỗ trợ.

<a id="checklist"></a>

## Checklist cho mỗi dự án

- [ ] Đã chọn đúng dự án và thị trường.
- [ ] Đã lưu chủ đề, keyword chính, mục tiêu kinh doanh và đối tượng độc giả.
- [ ] Đã chọn provider AI và kiểm tra kết nối.
- [ ] Đã đọc nhóm nhu cầu, phản biện và tạo phiếu Semrush phù hợp.
- [ ] Đã lấy file Semrush thật, ghép đúng cột và locale, xác nhận import.
- [ ] Đã đối chiếu Metrics/Organic và xem kết luận AI Critic.
- [ ] Đã xem từng mapping, xử lý điểm nghẽn và duyệt quyết định phiên bản hiện hành.
- [ ] Đã tạo brief cho các mapping mong muốn và kiểm tra nhãn dự thảo/chính thức.
- [ ] Đã xuất file, mở kiểm tra và bàn giao đúng bản hiện hành.
- [ ] Đã sao lưu dữ liệu trước khi kết thúc buổi làm việc.

## Nâng cấp V2.0 — nghiên cứu theo chủ đề

1. Bước 01: tải Bộ key, xem lỗi F0 theo dòng/cột. Mỗi mã có đúng một key Chính; giai đoạn TOFU/MOFU/BOFU. Khi xác nhận, chọn **Nghiên cứu toàn bộ mã nội dung trong pillar** để giữ toàn bộ Bộ key. Tắt lựa chọn để dùng chế độ một mã như trước.
2. Settings → AI Providers → **Playbook & ngưỡng nghiệp vụ**: xem/sửa các ngưỡng đề xuất. Keychain/env tiếp tục là nơi duy nhất lưu API key. Danh sách thương hiệu và quy tắc chuyển pillar được quản lý trong `services/api/app/knowledge/routing.yaml`.
3. Bước 03: **Tạo phiếu Semrush từ Bộ key đã xác nhận**. F2 giữ riêng biến thể không dấu mơ hồ; key ở hai mã phải sửa/duyệt nguồn trước. Phiếu VN gồm Overview theo lô tối đa 100 key và Related, Questions, SERP cho từng key chính. Xuất file trên Semrush rồi tải lên Bước 04.
4. File SERP không cần cột Keyword/Title: gắn bằng phiếu, hoặc tên `SERP-<key chính>.csv` khớp duy nhất với Bộ key. AI Overview được giữ riêng; Page AS và Ref.Domains còn trong dữ liệu gốc và bảng SERP Check.
5. Bước 05: **AI phân tích SERP theo từng key chính**. Mặc định không đọc website ngoài. Bật tùy chọn trong Settings nếu cần; trang không tải được phải ghi rõ. Ý bắt buộc chỉ lấy khi có đủ bài đã đọc làm bằng chứng theo ngưỡng; không suy đoán độ dài khi chưa đủ bài.
6. Bước 06: xem **Bàn giao nghiên cứu theo chủ đề**: góc bài, giai đoạn, keyword phụ có số, câu hỏi chưa xác minh, phân bố SERP và lý do ưu tiên. Có thể sửa nhãn từng dòng SERP; chạy lại phân tích và mapping để đưa thay đổi vào phiên bản cần duyệt. Nút **Sửa · chạy lại F5/F6** chỉ xử lý dòng đã chọn và lưu ghi chú. Các phê duyệt cũ chỉ giữ hiệu lực khi fingerprint và bằng chứng không đổi.
7. Bước 07: AI viết brief từ bàn giao. Thiếu phân tích SERP hiện hành hoặc chưa duyệt chỉ được nháp khi cấu hình cho phép và người dùng yêu cầu. Công cụ/tệp/dữ liệu nằm ở Backlog. F7 kiểm Title, Meta, vị trí key phụ, URL nội bộ, nguồn pháp lý và trùng outline; quá số lần sửa thì hiển thị `NEEDS_HUMAN_EDIT` (Cần người sửa), `generation_source=FALLBACK` (Bản dự phòng).
8. Xuất XLSX 5 sheet. Sheet brief có bảng điều hành, tổng quan và liên kết đến từng khối brief, phần Backlog cuối sheet. `/logs` lọc theo mã lý do và cờ Cần duyệt.

### Chờ sếp chốt

Ngưỡng P1/P2, số trang đọc, tuổi dữ liệu, số vòng bổ sung và sửa brief đều là đề xuất và có thể sửa trong Settings. Quyết định giữ P0 và cho phép brief nháp chưa duyệt nằm trong cấu hình; chưa tự tạo ưu tiên P0 khi chưa có quy tắc nghiệp vụ được chốt. Tỷ lệ thuế/bảo hiểm và văn bản hiện hành cần biên tập viên xác minh trước khi xuất bản bài viết.
