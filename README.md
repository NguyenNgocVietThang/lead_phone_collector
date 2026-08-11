# Lead Phone Collector

Tool tự động thu thập số điện thoại khách hàng tiềm năng từ **Google Maps** và **Facebook (public data, groups, keyword search)**, kết hợp bộ lọc chuẩn hóa SĐT Việt Nam, phát hiện nhà mạng, tìm kiếm Fuzzy Search không dấu, lưu trữ SQLite DB, đồng bộ tự động Google Sheets và xuất báo cáo Excel/CSV.

---

## Tính năng nổi bật

- **Google Maps Collector** — Tìm kiếm doanh nghiệp/địa điểm theo từ khóa và khu vực bằng Playwright Chromium, tự động trích xuất SĐT, địa chỉ, website, đánh giá và vị trí Google Maps.
- **Facebook Collector** — Thu thập SĐT đa kênh từ Fanpage công khai (About, Bài viết, Comments), Facebook Groups (nhóm công khai & nhóm đã tham gia) và Tìm kiếm từ khóa bài viết (Public search).
- **Xác thực Web UI (OAuth & Email)** — Hệ thống quản lý tài khoản Web UI bảo mật, hỗ trợ Đăng ký/Đăng nhập bằng Email & Mật khẩu, Google OpenID Connect và Facebook OAuth.
- **Session & Cookie Storage độc lập** — Quản lý phiên đăng nhập Playwright Cookies cho collector hoàn toàn độc lập với tài khoản Web UI, cho phép lưu và tái sử dụng session Facebook/Google mà không ảnh hưởng tới người dùng ứng dụng.
- **Phone Extractor & Normalizer** — Nhận diện 10+ định dạng SĐT Việt Nam trong văn bản thô, chuẩn hóa về đúng 10 chữ số (đầu `0`), kiểm tra tính hợp lệ và tự động phân loại nhà mạng (Viettel, Vina, Mobi, Vietnamobile, Gmobile, Itelecom/Wintel).
- **Fuzzy Search Engine** — Tìm kiếm linh hoạt loại bỏ dấu tiếng Việt, khớp một phần từ khóa, SĐT, tên hoặc nội dung trên Web UI & Database.
- **Deduplication** — Tự động loại trùng lặp dữ liệu theo SĐT đã chuẩn hóa (`phone_normalized UNIQUE`).
- **Google Sheets Sync** — Đồng bộ dữ liệu SĐT mới thu thập tự động và tức thì sang Google Sheet trực tuyến via Service Account API.
- **Export báo cáo đa định dạng** — Xuất file Excel (.xlsx multi-sheet kèm bảng thống kê nhà mạng/nguồn) và CSV (UTF-8 BOM hỗ trợ mở trực tiếp bằng Excel không lỗi font).
- **Modern Web UI Dashboard** — Giao diện Flask tinh gọn, tối giản, hiển thị thống kê visual, quản lý tiến trình scraping, lọc tra cứu và xuất dữ liệu dễ dàng.

---

## Cài đặt nhanh

```bash
# 1. Tạo và kích hoạt môi trường ảo Python 3.10+
python -m venv venv

# Windows
venv\Scripts\activate
# Linux/macOS
# source venv/bin/activate

# 2. Cài đặt thư viện dependencies & Playwright Chromium
pip install -r requirements.txt
playwright install chromium

# 3. Khởi tạo cấu hình môi trường
copy .env.example .env
# Mở .env và điền thông tin (FLASK_SECRET_KEY, OAuth credentials, Google Sheet ID, ...)

# 4. Khởi động Web UI Dashboard
python main.py ui
# Truy cập tại: http://localhost:5000
```

---

## Cấu hình Xác thực & OAuth cho Web UI

Trong file `.env`, thiết lập các thông số callback OAuth:

```dotenv
FLASK_SECRET_KEY=replace-with-a-long-random-secret
APP_BASE_URL=http://localhost:5000

GOOGLE_CLIENT_ID=your-google-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-google-client-secret

FACEBOOK_APP_ID=your-facebook-app-id
FACEBOOK_APP_SECRET=your-facebook-app-secret
```

Đăng ký chính xác Authorized Redirect URIs tại Google Cloud Console & Meta Developers Console:
- **Local Development**:
  - `http://localhost:5000/auth/google/callback`
  - `http://localhost:5000/auth/facebook/callback`
- **Production**:
  - `https://your-domain.com/auth/google/callback`
  - `https://your-domain.com/auth/facebook/callback` (Đặt `APP_BASE_URL=https://your-domain.com`)

> **Lưu ý**: Đăng nhập OAuth trên Web UI hoàn toàn độc lập với việc lưu Cookies collector (`python main.py login --service facebook`).

---

## Sử dụng qua CLI (Command Line)

```bash
# 1. Thu thập từ Google Maps
python main.py maps --keyword "nhà hàng" --area "Hà Nội" --limit 50 --show-browser

# 2. Thu thập từ Facebook (Page / Group / Search)
python main.py facebook --mode page --target "https://facebook.com/tenpage" --max-posts 30
python main.py facebook --mode group --target "https://facebook.com/groups/12345678" --max-posts 50
python main.py facebook --mode search --target "cần mua căn hộ gia lâm" --max-posts 40

# 3. Đăng nhập tương tác lưu session Cookies collector (Facebook / Google)
python main.py login --service facebook

# 4. Xuất dữ liệu báo cáo
python main.py export --format excel --output "data/exports/leads_moi.xlsx"
python main.py export --format csv --output "data/exports/leads_moi.csv"

# 5. Xem thống kê dữ liệu DB
python main.py stats
```

---

## Cấu trúc Project

```
lead-phone-collector/
├── collectors/          # Module Scraping (Google Maps, Facebook Page/Group/Search)
├── processors/          # Module Extractor & Normalizer SĐT (VN carriers)
├── storage/             # SQLite DB, User & OAuth Storage, Collector Cookies, Google Sheets Sync
├── exporters/           # Module Export Excel (.xlsx) & CSV (UTF-8 BOM)
├── ui/                  # Web UI Dashboard Flask (Routes, Auth, Templates & Assets)
├── config/              # Cấu hình hệ thống & Quản lý file .env
├── docs/                # Tài liệu kỹ thuật chi tiết từ 01 đến 07
├── tests/               # Unit tests (pytest)
├── data/                # Database SQLite (leads.db), export files & session cookies
├── main.py              # CLI Entry Point chính của ứng dụng
├── requirements.txt     # Danh sách thư viện Python
└── AUTHENTICATION_FIXES.md  # Tài liệu chi tiết luồng xác thực & bảo mật Web UI
```

---

## Tài liệu chi tiết

| File Tài Liệu | Nội Dung |
|---------------|----------|
| [01-architecture.md](docs/01-architecture.md) | Kiến trúc tổng quan hệ thống & luồng xử lý dữ liệu |
| [02-setup-guide.md](docs/02-setup-guide.md) | Hướng dẫn cài đặt, cấu hình & vận hành chi tiết |
| [03-google-maps-module.md](docs/03-google-maps-module.md) | Chi tiết Module Google Maps Scraper (Playwright) |
| [04-facebook-module.md](docs/04-facebook-module.md) | Chi tiết Module Facebook Scraper (Page, Group, Search & Cookies) |
| [05-phone-processing.md](docs/05-phone-processing.md) | Trích xuất, chuẩn hóa SĐT, Phân loại nhà mạng & Fuzzy Search |
| [06-database-schema.md](docs/06-database-schema.md) | Database Schema (SQLite), Bảng dữ liệu, Indexes & Queries |
| [07-export-guide.md](docs/07-export-guide.md) | Hướng dẫn Xuất báo cáo Excel, CSV & Sync Google Sheets |
| [AUTHENTICATION_FIXES.md](AUTHENTICATION_FIXES.md) | Cơ chế xác thực Web UI, OAuth Identifiers & Security |

---

## Lưu ý pháp lý & Điều khoản

- Hệ thống chỉ thu thập dữ liệu công khai hoặc dữ liệu mà tài khoản người dùng có quyền truy cập hợp lệ trên Google Maps và Facebook.
- Ứng dụng không thực hiện bypass CAPTCHA hay can thiệp phá hoại hệ thống của bên thứ ba.
- Người sử dụng có trách nhiệm tuân thủ Điều khoản dịch vụ (Terms of Service) của Google Maps và Facebook.

---

## Tech Stack

- **Core**: Python 3.10+
- **Scraping Engine**: Playwright Chromium (stealth mode & context isolation)
- **Web UI & API**: Flask, Jinja2, Werkzeug
- **Authentication**: Email/Password Hash, Google OpenID Connect, Facebook OAuth
- **Database**: SQLite3
- **Google Sheets**: gspread, Google Cloud Service Account API
- **Export Engine**: openpyxl (Excel), csv stdlib (UTF-8 BOM CSV)
- **Testing**: pytest
