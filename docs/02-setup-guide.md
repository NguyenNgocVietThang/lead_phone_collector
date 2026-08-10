# 02 — Hướng dẫn cài đặt & Vận hành

## Yêu cầu hệ thống

- Python **3.10+**
- Playwright Chromium (tự động cài qua command)
- OS: Windows 10/11, macOS, Linux
- Trình duyệt Chrome/Edge (khi dùng tính năng đăng nhập tương tác)

## Bước 1 — Clone / Tải project

```bash
cd "d:\Tool map fb"
```

## Bước 2 — Tạo Virtual Environment

```bash
python -m venv venv

# Windows (PowerShell / CMD)
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

## Bước 3 — Cài đặt Dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

## Bước 4 — Cấu hình .env

```bash
# Copy file template mẫu
copy .env.example .env

# Mở và chỉnh sửa file .env
notepad .env
```

### Các biến bắt buộc

| Biến | Mô tả |
|------|-------|
| `GOOGLE_SHEET_ID` | ID của Google Sheet (lấy từ URL: `https://docs.google.com/spreadsheets/d/[SHEET_ID]`) |
| `GOOGLE_SHEETS_CREDENTIALS_FILE` | Đường dẫn file JSON Service Account (`config/google-service-account.json`) |
| `FLASK_SECRET_KEY` | Chuỗi secret bí mật dùng mã hóa session cho Flask UI |

### Các biến tùy chọn

| Biến | Mô tả | Mặc định |
|------|-------|----------|
| `FACEBOOK_ACCESS_TOKEN` | Token Graph API (dùng nếu cào Page chính chủ) | Empty |
| `PLAYWRIGHT_HEADLESS` | `true` để chạy ẩn, `false` để hiển thị cửa sổ browser | `true` |
| `PLAYWRIGHT_DELAY_MIN` | Delay nhỏ nhất giữa các thao tác (giây) | `2.0` |
| `PLAYWRIGHT_DELAY_MAX` | Delay lớn nhất giữa các thao tác (giây) | `5.0` |
| `PLAYWRIGHT_NAV_TIMEOUT` | Timeout khi load trang (ms) | `30000` |

---

## Bước 5 — Đăng nhập tương tác (Tùy chọn cho Facebook Group/Search)

Nếu muốn thu thập dữ liệu từ **Facebook Groups** hoặc **Facebook Search** yêu cầu tài khoản:

```bash
# Khởi động trình duyệt đăng nhập tương tác cho Facebook
python main.py login --service facebook
```

Trình duyệt sẽ mở ra. Bạn thực hiện đăng nhập tài khoản Facebook cá nhân/phụ. Sau khi hoàn tất, hệ thống sẽ tự động lưu Session Cookies vào `data/cookies/fb_cookies.json` để các lần cào sau tự động sử dụng mà không cần login lại.

---

## Bước 6 — Cấu hình Google Sheets (Sync tự động)

1. Truy cập [Google Cloud Console](https://console.cloud.google.com/)
2. Tạo Project mới và enable **Google Sheets API** & **Google Drive API**.
3. Tạo **Service Account**, tạo JSON key và tải về lưu tại `config/google-service-account.json`.
4. Mở Google Sheet cần lưu dữ liệu → Bấm **Share** → Thêm email Service Account (`client_email` trong JSON) với quyền **Editor**.
5. Copy Sheet ID vào `.env`: `GOOGLE_SHEET_ID=...`.

---

## Bước 7 — Chạy Ứng Dụng

### 7.1 Web UI (Khuyên dùng)

```bash
python main.py ui
# Mở trình duyệt tại: http://localhost:5000
```

Giao diện Web cung cấp:
- Dashboard thống kê tổng quan (Tổng số leads, số mới, phân loại nhà mạng, nguồn).
- Công cụ kích hoạt scraper Google Maps & Facebook (Page/Group/Search) trực tiếp từ giao diện.
- Trình quản lý phiên đăng nhập (Facebook / Google cookies).
- Bảng tra cứu & Tìm kiếm Fuzzy Search (khớp một phần, tìm theo từ khóa không dấu, SĐT, tên).
- Nút xuất file Excel (.xlsx) & CSV tức thì.

### 7.2 CLI (Command Line)

```bash
# 1. Thu thập từ Google Maps
python main.py maps --keyword "nhà hàng" --area "Hà Nội" --limit 50 --show-browser

# 2. Thu thập từ Facebook Page công khai
python main.py facebook --mode page --target "https://facebook.com/tenpage"

# 3. Thu thập từ Facebook Group
python main.py facebook --mode group --target "https://facebook.com/groups/123456" --max-posts 30

# 4. Thu thập từ Facebook Tìm kiếm từ khóa
python main.py facebook --mode search --target "cần tìm mua căn hộ quận 7" --max-posts 50

# 5. Xuất dữ liệu báo cáo
python main.py export --format excel --output "data/exports/leads_moi.xlsx"
python main.py export --format csv --output "data/exports/leads_moi.csv"

# 6. Xem thống kê dữ liệu
python main.py stats
```

---

## Kiểm tra Unit Tests

```bash
pytest tests/ -v
```

---

## Troubleshooting & Khắc phục lỗi

### 1. Lỗi `executable doesn't exist` (Playwright)
```bash
playwright install chromium
```

### 2. Facebook bắt đăng nhập / Không lấy được bài viết Group
- Chạy `python main.py login --service facebook` để lưu cookies phiên làm việc.
- Hoặc bật `--show-browser` trên CLI để kiểm tra giao diện trực quan.

### 3. Google Sheets báo lỗi Permission Denied
- Đảm bảo đã Share Google Sheet cho email của Service Account với quyền **Editor**.
- Kiểm tra lại đường dẫn file JSON `GOOGLE_SHEETS_CREDENTIALS_FILE` trong `.env`.

