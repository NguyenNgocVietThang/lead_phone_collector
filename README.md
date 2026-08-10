# Lead Phone Collector

Tool tự động thu thập số điện thoại khách hàng tiềm năng từ **Google Maps** và **Facebook (public data, groups, keyword search)**.

## Tính năng

- **Google Maps** — Tìm doanh nghiệp theo từ khóa/khu vực bằng Playwright, lấy SĐT, địa chỉ, website, đánh giá.
- **Facebook** — Thu thập SĐT từ Fanpage công khai, Facebook Groups, và Tìm kiếm từ khóa (Public posts, comments, About section).
- **Session & Login** — Đăng nhập tương tác lưu Cookies Facebook/Google để thu thập nội dung Groups & kết quả tìm kiếm đã xác thực.
- **Phone Processing** — Nhận diện 10+ định dạng SĐT VN, chuẩn hóa (đúng 10 chữ số), kiểm tra và phân loại nhà mạng (Viettel, Vina, Mobi, ...).
- **Fuzzy Search** — Tìm kiếm linh hoạt không dấu, khớp một phần từ khóa và SĐT trên Web UI & Database.
- **Deduplication** — Tự động loại trùng theo SĐT đã chuẩn hóa.
- **Google Sheets** — Sync tự động tức thì hoặc định kỳ sau mỗi lần thu thập.
- **Export** — Xuất báo cáo Excel (.xlsx multi-sheet) và CSV (UTF-8 BOM).
- **Web UI** — Dashboard Flask hiện đại để điều khiển collector, quản lý phiên đăng nhập, lọc & xuất leads dễ dàng.

## Cài đặt nhanh

```bash
# 1. Cài dependencies
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium

# 2. Cấu hình
copy .env.example .env
# Mở .env và điền thông tin (Google Sheet ID, Secret Key, ...)

# 3. Chạy Web UI
python main.py ui
# Mở http://localhost:5000
```

## Sử dụng CLI

```bash
# Thu thập từ Google Maps
python main.py maps --keyword "nhà hàng" --area "Hà Nội" --limit 50 --show-browser

# Thu thập từ Facebook (Page / Group / Keyword Search)
python main.py facebook --mode page --target "https://facebook.com/tenpage"
python main.py facebook --mode group --target "https://facebook.com/groups/123456"
python main.py facebook --mode search --target "cần mua đất gia lâm" --max-posts 30

# Đăng nhập lưu session Cookies (Facebook / Google)
python main.py login --service facebook

# Xuất kết quả
python main.py export --format excel
python main.py export --format csv

# Xem thống kê DB
python main.py stats
```

## Cấu trúc project

```
├── collectors/ # Thu thập từ Google Maps, Facebook (Playwright)
├── processors/ # Extractor + Normalizer SĐT (VN carrier detection)
├── storage/ # SQLite DB, Auth Session Cookies & Google Sheets sync
├── exporters/ # Excel (.xlsx) + CSV export
├── ui/ # Flask Web UI (Dashboard, Filters, Login UI, Export)
├── config/ # Settings + .env
├── docs/ # Tài liệu chi tiết 01-07
├── tests/ # Unit tests (pytest)
├── data/ # Database SQLite + file export + auth cookies
└── main.py # CLI entry point
```

## Tài liệu

| File | Nội dung |
|------|---------|
| [01-architecture.md](docs/01-architecture.md) | Kiến trúc hệ thống & luồng xử lý |
| [02-setup-guide.md](docs/02-setup-guide.md) | Hướng dẫn cài đặt & vận hành |
| [03-google-maps-module.md](docs/03-google-maps-module.md) | Module Google Maps (Playwright) |
| [04-facebook-module.md](docs/04-facebook-module.md) | Module Facebook (Page, Group, Search & Auth) |
| [05-phone-processing.md](docs/05-phone-processing.md) | Xử lý số điện thoại & Fuzzy Search |
| [06-database-schema.md](docs/06-database-schema.md) | Database schema & Query optimization |
| [07-export-guide.md](docs/07-export-guide.md) | Hướng dẫn xuất file Excel & CSV |

## Lưu ý pháp lý

- Thu thập dữ liệu công khai từ Google Maps và Facebook.
- Hỗ trợ lưu Cookies session của chính người dùng để mở rộng khả năng tìm kiếm trong Groups.
- Không bypass CAPTCHA hay phá hoại hệ thống.
- Tuân thủ Terms of Service của từng nền tảng.

## Tech Stack

`Python 3.10+` · `Playwright` · `Flask` · `SQLite` · `gspread` · `openpyxl`
