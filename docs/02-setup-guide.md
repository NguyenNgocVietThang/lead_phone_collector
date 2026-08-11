# 02 — Hướng dẫn cài đặt & Vận hành

Tài liệu chi tiết hướng dẫn cài đặt môi trường, cấu hình biến hệ thống, khởi động Web UI, vận hành câu lệnh CLI, đồng bộ Google Sheets và xử lý các sự cố thường gặp.

---

## Yêu cầu hệ thống

- **Hệ điều hành**: Windows 10/11, macOS, hoặc Linux.
- **Python**: Môi trường Python **3.10** trở lên.
- **Trình duyệt**: Playwright Chromium (tự động cài đặt thông qua câu lệnh).
- **Quyền mạng**: Kết nối Internet không bị chặn bởi Firewall/Proxy đối với Google Maps và Facebook.

---

## Các bước cài đặt chi tiết

### Bước 1 — Clone / Tải dự án

Mở Terminal / PowerShell và di chuyển vào thư mục dự án:

```bash
cd "d:\Tool map fb"
```

### Bước 2 — Tạo Môi trường ảo (Virtual Environment)

Tạo và kích hoạt venv để cô lập dependencies:

```bash
# Tạo môi trường ảo venv
python -m venv venv

# Windows (PowerShell / CMD)
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### Bước 3 — Cài đặt Dependencies & Playwright Browser

Cài đặt tất cả thư viện Python từ `requirements.txt` và tải bản Chromium tương thích với Playwright:

```bash
pip install -r requirements.txt
playwright install chromium
```

### Bước 4 — Cấu hình File `.env`

Sao chép file `.env.example` thành `.env` để cài đặt cấu hình:

```bash
# Trên Windows PowerShell
copy .env.example .env

# Mở file .env để chỉnh sửa
notepad .env
```

#### Các biến cấu hình quan trọng trong `.env`:

| Biến Môi Trường | Loại | Mặc Định | Mô Tả & Hướng Dẫn |
|-----------------|------|----------|-------------------|
| `FLASK_SECRET_KEY` | Bắt buộc | `replace-with-a...` | Chuỗi ký tự ngẫu nhiên dùng để mã hóa Session Web UI. |
| `APP_BASE_URL` | Bắt buộc | `http://localhost:5000` | Domain/URL gốc của Web UI. |
| `GOOGLE_SHEET_ID` | Tùy chọn | Empty | ID Google Sheet cần sync (Lấy từ URL spreadsheet). |
| `GOOGLE_SHEETS_CREDENTIALS_FILE` | Tùy chọn | `config/google-service-account.json` | Đường dẫn file JSON key Service Account của Google Cloud. |
| `GOOGLE_CLIENT_ID` | OAuth | Empty | Client ID từ Google Cloud Console (Dùng cho Web UI OAuth). |
| `GOOGLE_CLIENT_SECRET` | OAuth | Empty | Client Secret từ Google Cloud Console. |
| `FACEBOOK_APP_ID` | OAuth | Empty | App ID từ Meta Developers Console (Dùng cho Web UI OAuth). |
| `FACEBOOK_APP_SECRET` | OAuth | Empty | App Secret từ Meta Developers Console. |
| `PLAYWRIGHT_HEADLESS` | System | `true` | `true` để chạy ẩn trình duyệt; `false` để bật cửa sổ trực quan. |
| `PLAYWRIGHT_DELAY_MIN` | Delay | `2.0` | Thời gian nghỉ tối thiểu giữa các thao tác (giây). |
| `PLAYWRIGHT_DELAY_MAX` | Delay | `5.0` | Thời gian nghỉ tối đa giữa các thao tác (giây). |
| `PLAYWRIGHT_NAV_TIMEOUT` | Timeout | `30000` | Thời gian chờ tối đa khi load trang (milliseconds). |

---

## Bước 5 — Đăng nhập tương tác lưu Session Cookies Collector

Để thu thập bài viết/bình luận từ **Facebook Groups** hoặc **Tìm kiếm từ khóa Facebook**, bạn cần lưu Cookies phiên đăng nhập trình duyệt:

```bash
python main.py login --service facebook
```

1. Cửa sổ Chromium trực quan sẽ mở ra.
2. Bạn thực hiện đăng nhập tài khoản Facebook cá nhân hoặc tài khoản phụ.
3. Sau khi đăng nhập hoàn tất và vào đến bảng tin Facebook, đóng trình duyệt hoặc quay lại terminal.
4. Session Cookies sẽ tự động lưu vào `data/cookies/fb_cookies.json` để các lần cào sau sử dụng tự động.

---

## Bước 6 — Thiết lập Google Sheets Sync (Đồng bộ Tự động)

1. Truy cập [Google Cloud Console](https://console.cloud.google.com/).
2. Tạo Project mới, sau đó bật (Enable) hai dịch vụ API: **Google Sheets API** và **Google Drive API**.
3. Tạo **Service Account**, vào tab **Keys** -> **Add Key** -> **Create new key (JSON)**.
4. Tải file JSON xuống, đổi tên và lưu tại đường dẫn: `config/google-service-account.json`.
5. Mở file JSON, copy địa chỉ `client_email` (VD: `my-service-account@project.iam.gserviceaccount.com`).
6. Mở Google Sheet trên trình duyệt -> Bấm **Share (Chia sẻ)** -> Dán email Service Account và cấp quyền **Editor (Người chỉnh sửa)**.
7. Copy ID Google Sheet từ URL (ví dụ URL: `https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5n.../edit` -> ID là `1BxiMVs0XRA5n...`).
8. Điền vào `.env`: `GOOGLE_SHEET_ID=1BxiMVs0XRA5n...`.

---

## Bước 7 — Vận hành Hệ thống

### 7.1 Sử dụng Web UI Dashboard (Khuyên dùng)

Khởi động Web UI Server:

```bash
python main.py ui
```

Mở trình duyệt truy cập: `http://localhost:5000`

**Các tính năng nổi bật trên Web UI**:
- **Trang Dashboard**: Hiển thị tổng số leads, số lead trong ngày, biểu đồ phân bố nhà mạng và nguồn thu thập.
- **Tính năng Đăng ký / Đăng nhập**: Hỗ trợ đăng nhập Email hoặc 1-click Google / Facebook OAuth.
- **Trình điều khiển Scraper**: Khởi tạo job thu thập Google Maps và Facebook trực tiếp trên giao diện web.
- **Trình tra cứu Leads**: Tìm kiếm Fuzzy Search (không dấu, khớp SĐT, địa chỉ, tên), lọc theo Nguồn, Nhà mạng, Trạng thái.
- **Quản lý Export**: Xuất dữ liệu ra Excel (.xlsx) hoặc CSV ngay trên Web.

### 7.2 Sử dụng lệnh CLI (Command Line Interface)

```bash
# 1. Thu thập từ Google Maps
python main.py maps --keyword "nhà hàng" --area "Hà Nội" --limit 50 --show-browser

# 2. Thu thập từ Facebook Fanpage
python main.py facebook --mode page --target "https://facebook.com/tenpage" --max-posts 30

# 3. Thu thập từ Facebook Group
python main.py facebook --mode group --target "https://facebook.com/groups/12345678" --max-posts 50

# 4. Thu thập từ Facebook Tìm kiếm từ khóa
python main.py facebook --mode search --target "cần mua đất gia lâm" --max-posts 40

# 5. Xuất dữ liệu báo cáo
python main.py export --format excel --output "data/exports/leads_moi.xlsx"
python main.py export --format csv --output "data/exports/leads_moi.csv"

# 6. Xem thống kê dữ liệu hiện có trong Database
python main.py stats
```

---

## Kiểm thử Đơn vị (Unit Tests)

Chạy bộ kiểm thử tự động với `pytest`:

```bash
pytest tests/ -v
```

---

## Khắc phục lỗi thường gặp (Troubleshooting)

### 1. Lỗi `executable doesn't exist` (Playwright)
- **Nguyên nhân**: Chưa cài đặt bản dựng Chromium cho Playwright.
- **Khắc phục**: Chạy lệnh `playwright install chromium`.

### 2. Facebook yêu cầu đăng nhập / Không cào được Group
- **Nguyên nhân**: Facebook bắt buộc phải có Cookie Session đã đăng nhập để đọc dữ liệu Group hoặc Search.
- **Khắc phục**: Chạy `python main.py login --service facebook` để thực hiện đăng nhập và lưu lại cookie.

### 3. Google Sheets báo lỗi `Permission Denied` hoặc `API Error`
- **Nguyên nhân**: File JSON credential sai hoặc chưa chia sẻ quyền Editor cho email Service Account trên Google Sheet.
- **Khắc phục**: 
  - Kiểm tra xem file JSON đã đặt tại `config/google-service-account.json` hay chưa.
  - Mở Google Sheet, kiểm tra phần Share xem email `client_email` đã được gán quyền Editor chưa.

### 4. Mất kết nối OAuth Callback (`redirect_uri_mismatch`)
- **Nguyên nhân**: URL callback cấu hình tại Google Cloud Console / Meta Developers không khớp với URL thực tế ứng dụng chạy.
- **Khắc phục**: Kiểm tra chính xác URL callback trong app (`http://localhost:5000/auth/google/callback` hoặc `http://localhost:5000/auth/facebook/callback`) và thêm chính xác vào cài đặt Authorized Redirect URIs của nhà cung cấp.
