# 01 — Kiến trúc hệ thống

## Tổng quan

**Lead Phone Collector** là giải pháp phần mềm tự động thu thập, trích xuất và quản lý dữ liệu số điện thoại khách hàng tiềm năng từ các nguồn công khai trực tuyến (**Google Maps**, **Facebook Fanpages**, **Facebook Groups**, **Facebook Keyword Search**). 

Hệ thống tích hợp quy trình xử lý dữ liệu chuẩn hóa 10 chữ số, nhận diện nhà mạng viễn thông Việt Nam, loại bỏ trùng lặp tự động, tìm kiếm Fuzzy Search không dấu, lưu trữ SQLite, đồng bộ tự động Google Sheets và cung cấp giao diện Web UI Dashboard kèm bộ công cụ CLI mạnh mẽ.

---

## Sơ đồ luồng dữ liệu (Dataflow Diagram)

```text
┌────────────────────────────────────────────────────────────────────────┐
│                          NGUỒN DỮ LIỆU ĐẦU VÀO                        │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
       ┌────────────────────────────┼────────────────────────────┐
       ▼                            ▼                            ▼
┌─────────────┐              ┌─────────────┐              ┌─────────────┐
│ Google Maps │              │ FB Pages    │              │ FB Groups & │
│ (Playwright)│              │ Public      │              │ FB Search   │
└──────┬──────┘              └──────┬──────┘              └──────┬──────┘
       │                            │                            │
       │                            └────────────┬───────────────┘
       │                                         │
       │                                ┌────────┴────────┐
       │                                │ Cookie Session  │ (storage/auth.py)
       │                                └────────┬────────┘
       │                                         │
       └────────────────────┬────────────────────┘
                            ▼
                ┌───────────────────────┐
                │ Phone Extractor       │ ← Regex VN Phone Patterns (10+ định dạng)
                └───────────┬───────────┘
                            ▼
                ┌───────────────────────┐
                │ Phone Normalizer      │ ← Chuẩn hóa 10 chữ số (đầu 0) + Phân loại nhà mạng
                └───────────┬───────────┘
                            ▼
                ┌───────────────────────┐
                │ Deduplicator Engine   │ ← Bỏ trùng tự động qua phone_normalized UNIQUE
                └───────────┬───────────┘
                            │
       ┌────────────────────┼────────────────────┐
       ▼                    ▼                    ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ SQLite DB    │    │ Google Sheets│    │ File Export  │
│ (leads.db)   │    │ Cloud Sync   │    │ (Excel/CSV)  │
└──────────────┘    └──────────────┘    └──────────────┘
```

---

## Kiến trúc Cấu trúc Thư mục

```text
lead-phone-collector/
├── collectors/              # Các Module thu thập dữ liệu (Playwright Chromium)
│   ├── google_maps.py       # Scraper trích xuất chi tiết doanh nghiệp Google Maps
│   └── facebook.py          # Scraper trích xuất Facebook Pages, Groups, Search & Graph API
├── processors/              # Các Module xử lý & chuẩn hóa dữ liệu SĐT
│   ├── extractor.py         # Regex phát hiện SĐT VN trong văn bản thô & context
│   └── normalizer.py        # Chuẩn hóa SĐT 10 chữ số & nhận diện 6 nhà mạng Việt Nam
├── storage/                 # Module Lưu trữ, Phiên làm việc & Đồng bộ Cloud
│   ├── database.py          # SQLite CRUD, User/OAuth Auth DB, Jobs & Fuzzy Search Engine
│   ├── auth.py              # Playwright Interactive Cookie Session Manager
│   └── sheets.py            # Automatic Sync Google Sheets API (gspread)
├── exporters/               # Module Xuất file báo cáo
│   ├── excel_export.py      # Xuất file Excel (.xlsx) kèm sheet Thống kê & format chuẩn
│   └── csv_export.py        # Xuất file CSV định dạng UTF-8 BOM
├── ui/                      # Giao diện Flask Web UI Dashboard
│   ├── app.py               # Routes Handler, API endpoints & OAuth Callbacks
│   ├── templates/           # Giao diện HTML Jinja2 (Dashboard, Leads, Jobs, Auth, Export)
│   └── static/              # Asset CSS, Client-side JavaScript & Logos
├── config/                  # Quản lý Cấu hình & Môi trường
│   ├── settings.py          # Class Settings đọc cấu hình từ .env
│   └── .env.example         # File mẫu cấu hình biến môi trường
├── docs/                    # Tài liệu hướng dẫn kỹ thuật từ 01 đến 07
├── tests/                   # Bộ kiểm thử tự động pytest
├── data/                    # Thư mục lưu DB SQLite (leads.db), exports & cookies
│   ├── leads.db             # Cơ sở dữ liệu SQLite
│   ├── cookies/             # File session cookies (fb_cookies.json)
│   └── exports/             # Thư mục chứa các file Excel/CSV xuất ra
├── logs/                    # Thư mục chứa file nhật ký hệ thống (system.log)
├── main.py                  # CLI Entrypoint thực thi các câu lệnh
├── requirements.txt         # Khai báo dependencies thư viện Python
└── AUTHENTICATION_FIXES.md  # Tài liệu chi tiết xác thực Web UI & OAuth 2.0
```

---

## Các Module chính & Vai trò

| Module / Component | File thực thi | Vai trò & Chức năng chi tiết |
|--------------------|---------------|------------------------------|
| **Google Maps Collector** | `collectors/google_maps.py` | Scraping danh sách địa điểm, tên, SĐT, địa chỉ, website, rating trên Google Maps qua Playwright. |
| **Facebook Collector** | `collectors/facebook.py` | Scraping SĐT từ Fanpages (About, Post, Comments), Groups và Keyword Search. |
| **Phone Extractor** | `processors/extractor.py` | Trích xuất tất cả định dạng SĐT Việt Nam (10+ mẫu) và lấy văn bản ngữ cảnh xung quanh SĐT. |
| **Phone Normalizer** | `processors/normalizer.py` | Chuẩn hóa SĐT về 10 chữ số (đầu `0`), xác minh độ hợp lệ và nhận diện nhà mạng (Viettel, Vina, Mobi, ...). |
| **Database Engine** | `storage/database.py` | Quản lý SQLite database (`leads`, `collection_jobs`, `users`, `oauth_identities`), Fuzzy Search tiếng Việt không dấu, dedup UNIQUE. |
| **Session & Auth Manager** | `storage/auth.py` | Quản lý việc đăng nhập tương tác bằng trình duyệt để lưu Playwright Browser Context Cookies. |
| **Google Sheets Sync** | `storage/sheets.py` | Tự động kiểm tra và đẩy các bản ghi SĐT mới sang Google Sheet qua Service Account Key. |
| **Excel Exporter** | `exporters/excel_export.py` | Xuất dữ liệu ra file Excel (.xlsx) 2 sheet (Bảng Leads chuẩn định dạng + Sheet Thống kê nguồn/nhà mạng). |
| **CSV Exporter** | `exporters/csv_export.py` | Xuất dữ liệu ra file CSV mã hóa `UTF-8 với BOM` (`utf-8-sig`) giúp Excel mở không bị lỗi font. |
| **Web UI Application** | `ui/app.py` | Ứng dụng Flask Web UI cung cấp Dashboard điều khiển, Auth đăng nhập (Email/OAuth), bộ lọc tra cứu & API endpoints. |
| **CLI Entrypoint** | `main.py` | Giao diện dòng lệnh (CLI) điều khiển các tác vụ scraping, login, export và thống kê. |

---

## Stack công nghệ chi tiết

- **Ngôn ngữ phát triển**: Python 3.10+
- **Thu thập dữ liệu (Scraping)**: Playwright Chromium (hỗ trợ headless/headful mode, stealth options & isolated context).
- **Web UI & REST API**: Flask, Werkzeug, Jinja2.
- **Xác thực Web UI**: Flask Session, OAuth 2.0 / OpenID Connect (Google, Facebook), Werkzeug Password Hashing.
- **Cơ sở dữ liệu**: SQLite3 (chỉ mục indexing, foreign keys, UTF-8 accent removal).
- **Bộ lọc & Xử lý văn bản**: Regex (re), `unicodedata` (loại bỏ dấu tiếng Việt).
- **Đồng bộ Cloud**: `gspread`, Google Cloud Sheets API & Drive API.
- **Xuất báo cáo**: `openpyxl` (Excel), Python stdlib `csv` (UTF-8-SIG CSV).
- **Automated Testing**: `pytest`.
