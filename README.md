# 📱 Lead Phone Collector

Tool tự động thu thập số điện thoại khách hàng tiềm năng từ **Google Maps** và **Facebook (public data)**.

## Tính năng

- 🗺️ **Google Maps** — Tìm doanh nghiệp theo từ khóa/khu vực, lấy SĐT, địa chỉ, website
- 📘 **Facebook** — Thu thập SĐT từ public posts, comments, About section
- 📞 **Phone Processing** — Nhận diện 10+ định dạng SĐT VN, chuẩn hóa, kiểm tra nhà mạng
- 🔄 **Deduplication** — Tự động loại trùng
- 📊 **Google Sheets** — Sync tự động sau mỗi lần thu thập
- 📥 **Export** — Excel (.xlsx) và CSV
- 🌐 **Web UI** — Dashboard Flask để thao tác dễ dàng

## Cài đặt nhanh

```bash
# 1. Cài dependencies
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

# 2. Cấu hình
copy .env.example .env
# Mở .env và điền thông tin

# 3. Chạy Web UI
python main.py ui
# Mở http://localhost:5000
```

## Sử dụng CLI

```bash
# Thu thập từ Google Maps
python main.py maps --keyword "nhà hàng" --area "Hà Nội" --limit 50

# Thu thập từ Facebook page công khai
python main.py facebook --url "https://facebook.com/tenpage"

# Xuất kết quả
python main.py export --format excel
python main.py export --format csv

# Xem thống kê
python main.py stats
```

## Cấu trúc project

```
├── collectors/      # Thu thập từ Google Maps, Facebook
├── processors/      # Extractor + Normalizer SĐT
├── storage/         # SQLite DB + Google Sheets sync
├── exporters/       # Excel + CSV export
├── ui/              # Flask Web UI
├── config/          # Settings + .env
├── docs/            # Tài liệu chi tiết
├── tests/           # Unit tests
├── data/            # Database + file export
└── main.py          # CLI entry point
```

## Tài liệu

| File | Nội dung |
|------|---------|
| [01-architecture.md](docs/01-architecture.md) | Kiến trúc hệ thống |
| [02-setup-guide.md](docs/02-setup-guide.md) | Hướng dẫn cài đặt chi tiết |
| [03-google-maps-module.md](docs/03-google-maps-module.md) | Module Google Maps |
| [04-facebook-module.md](docs/04-facebook-module.md) | Module Facebook |
| [05-phone-processing.md](docs/05-phone-processing.md) | Xử lý số điện thoại |
| [06-database-schema.md](docs/06-database-schema.md) | Database schema |
| [07-export-guide.md](docs/07-export-guide.md) | Hướng dẫn xuất file |

## Lưu ý pháp lý

- Chỉ thu thập dữ liệu **công khai** mà không cần đăng nhập
- Không bypass CAPTCHA, login, hay cơ chế bảo vệ
- Không thu thập dữ liệu cá nhân không công khai
- Sử dụng hợp lý và tuân thủ Terms of Service của từng nền tảng

## Tech Stack

`Python 3.10+` · `Selenium` · `Flask` · `SQLite` · `gspread` · `openpyxl`
