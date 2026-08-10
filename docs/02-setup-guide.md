# 02 — Hướng dẫn cài đặt

## Yêu cầu hệ thống

- Python **3.10+**
- Google Chrome đã cài đặt (dùng cho Selenium)
- Internet connection

## Bước 1 — Clone / tải project

```bash
# Hoặc tải ZIP và giải nén vào thư mục mong muốn
cd "d:\Tool map fb"
```

## Bước 2 — Tạo virtual environment

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate
```

## Bước 3 — Cài đặt dependencies

```bash
pip install -r requirements.txt
```

## Bước 4 — Cấu hình .env

```bash
# Copy template
copy .env.example .env

# Mở và điền thông tin
notepad .env
```

### Các biến bắt buộc

| Biến | Mô tả |
|------|-------|
| `GOOGLE_SHEET_ID` | ID của Google Sheet (lấy từ URL) |
| `GOOGLE_SHEETS_CREDENTIALS_FILE` | Đường dẫn tới file JSON Service Account |
| `FLASK_SECRET_KEY` | Chuỗi bí mật bất kỳ cho Flask session |

### Các biến tùy chọn

| Biến | Mô tả |
|------|-------|
| `FACEBOOK_ACCESS_TOKEN` | Token Graph API (chỉ cần nếu dùng Graph API) |
| `SELENIUM_HEADLESS` | `true` để chạy ẩn, `false` để thấy browser |
| `SELENIUM_DELAY_MIN/MAX` | Delay giữa requests (giây) |

## Bước 5 — Cấu hình Google Sheets

### 5.1 — Tạo Google Cloud Project

1. Vào [console.cloud.google.com](https://console.cloud.google.com/)
2. Tạo project mới
3. Enable **Google Sheets API** và **Google Drive API**

### 5.2 — Tạo Service Account

1. IAM & Admin → Service Accounts → Create
2. Cấp role: **Editor**
3. Tạo key → JSON → tải về
4. Đặt file vào `config/google-service-account.json`

### 5.3 — Share Google Sheet

1. Mở Google Sheet muốn sync
2. Share → thêm email của Service Account (trong file JSON, trường `client_email`)
3. Cấp quyền **Editor**
4. Copy Sheet ID từ URL: `https://docs.google.com/spreadsheets/d/[SHEET_ID]/edit`
5. Điền vào `.env`: `GOOGLE_SHEET_ID=...`

## Bước 6 — Chạy ứng dụng

### Web UI (khuyến nghị)

```bash
python main.py ui
# Mở trình duyệt tại: http://localhost:5000
```

### CLI

```bash
# Thu thập từ Google Maps
python main.py maps --keyword "nhà hàng" --area "Hà Nội" --limit 50

# Thu thập từ Facebook page
python main.py facebook --url "https://facebook.com/pagename"

# Xuất kết quả
python main.py export --format excel
python main.py export --format csv
```

## Chạy Tests

```bash
pytest tests/ -v
```

## Troubleshooting

### ChromeDriver không khớp phiên bản Chrome

Dự án dùng `webdriver-manager` — tự tải ChromeDriver phù hợp. Nếu lỗi:
```bash
pip install --upgrade webdriver-manager
```

### Bị block bởi Google Maps

- Tăng delay: `SELENIUM_DELAY_MIN=3` và `SELENIUM_DELAY_MAX=6`
- Thử `SELENIUM_HEADLESS=false` để dùng browser thật

### Google Sheets lỗi permission

- Kiểm tra email Service Account đã được share quyền Editor
- Kiểm tra file JSON đúng đường dẫn trong `.env`
