# 01 — Kiến trúc hệ thống

## Tổng quan

**Lead Phone Collector** là hệ thống tự động thu thập số điện thoại khách hàng tiềm năng từ các nguồn dữ liệu công khai (**Google Maps**, **Facebook Fanpage**, **Facebook Groups**, **Facebook Keyword Search**), nhận diện, chuẩn hóa, loại trùng và lưu vào SQLite Database + Google Sheets + file xuất (Excel/CSV).

## Luồng dữ liệu

```
┌────────────────────────────────────────────────────────────────────────┐
│ NGUỒN DỮ LIỆU │
└───────────────────────────────────┬────────────────────────────────────┘
 │
 ┌──────────────────────────┼──────────────────────────┐
 ▼ ▼ ▼
 ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
 │ Google Maps │ │ FB Public │ │ FB Groups / │
 │ (Playwright)│ │ Pages │ │ Search │
 └──────┬──────┘ └──────┬──────┘ └──────┬──────┘
 │ │ │
 │ └────────────┬─────────────┘
 │ │
 │ ┌──────────┴──────────┐
 │ │ Auth / Cookie Session│ (storage/auth.py)
 │ └──────────┬──────────┘
 │ │
 └───────────────────┬───────────────────┘
 ▼
 ┌──────────────────┐
 │ Phone Extractor │ ← Regex VN phone patterns (10+ định dạng)
 └────────┬─────────┘
 ▼
 ┌──────────────────┐
 │ Phone Normalizer │ ← Chuẩn hóa (10 chữ số) + carrier detect
 └────────┬─────────┘
 ▼
 ┌──────────────────┐
 │ Deduplicator │ ← Loại trùng theo phone_normalized UNIQUE
 └────────┬─────────┘
 │
 ┌────────────────────┼────────────────────┐
 ▼ ▼ ▼
 ┌──────────┐ ┌──────────┐ ┌──────────┐
 │ SQLite │ │ Google │ │ Export │
 │ DB │ │ Sheets │ │Excel/CSV │
 └──────────┘ └──────────┘ └──────────┘
```

## Kiến trúc thư mục

```
lead-phone-collector/
├── collectors/ # Module Thu thập (Playwright)
│ ├── google_maps.py # Scraping Google Maps places & contact details
│ └── facebook.py # Facebook collector (Page, Group, Search & Graph API)
├── processors/ # Module Xử lý SĐT
│ ├── extractor.py # Regex nhận diện SĐT trong văn bản
│ └── normalizer.py # Chuẩn hóa 10 chữ số, validate & nhận diện nhà mạng
├── storage/ # Module Lưu trữ & Phiên làm việc
│ ├── database.py # SQLite CRUD, dedup & Fuzzy Search engine
│ ├── auth.py # Session & Cookies Manager (FB/Google login)
│ └── sheets.py # Google Sheets sync (gspread)
├── exporters/ # Module Xuất dữ liệu
│ ├── excel_export.py # Xuất Excel (.xlsx multi-sheet)
│ └── csv_export.py # Xuất CSV (UTF-8 BOM)
├── ui/ # Giao diện web (Flask Dashboard)
│ ├── app.py # Routes & API endpoints
│ ├── templates/ # HTML templates (Dashboard, Leads, Jobs, Login)
│ └── static/ # CSS & Client-side JS
├── config/
│ ├── settings.py # Configuration manager
│ └── .env.example # Environment template
├── docs/ # Tài liệu kỹ thuật & Hướng dẫn (01-07)
├── tests/ # Unit tests (pytest)
├── data/
│ ├── leads.db # Database SQLite
│ ├── cookies/ # Session cookies đã đăng nhập (fb_cookies.json, ...)
│ └── exports/ # File xuất báo cáo
├── logs/ # System log files
├── main.py # CLI entry point
└── requirements.txt
```

## Các module chính

| Module | File | Chức năng |
|--------|------|-----------|
| Collector Maps | `collectors/google_maps.py` | Playwright scraping Google Maps places & contact info |
| Collector FB | `collectors/facebook.py` | Playwright & Graph API scraping Pages, Groups, Search |
| Extractor | `processors/extractor.py` | Nhận diện 10+ mẫu SĐT VN trong văn bản thô |
| Normalizer | `processors/normalizer.py` | Chuẩn hóa SĐT thành 10 chữ số + nhận diện nhà mạng |
| Database | `storage/database.py` | SQLite CRUD, Deduplication & Fuzzy Search (unaccented) |
| Auth Session | `storage/auth.py` | Quản lý phiên đăng nhập tương tác & lưu Playwright cookies |
| Sheets Sync | `storage/sheets.py` | Sync dữ liệu tự động với Google Sheets qua Service Account |
| Export Excel | `exporters/excel_export.py` | Xuất dữ liệu ra Excel (.xlsx) kèm sheet Thống kê |
| Export CSV | `exporters/csv_export.py` | Xuất dữ liệu ra CSV định dạng UTF-8 BOM |
| Web UI | `ui/app.py` | Flask Web UI dashboard điều khiển & quản lý |
| CLI Entry | `main.py` | Command-line interface cho tất cả tác vụ |

## Stack công nghệ

- **Language**: Python 3.10+
- **Scraping Engine**: Playwright Chromium (stealth mode, context isolation)
- **Session & Auth**: Playwright Browser Context Cookie Storage
- **Database**: SQLite (built-in, zero-config, indexing support)
- **Search Engine**: SQLite + Custom Unaccented Fuzzy Matching
- **Google Sheets**: gspread + Google Cloud Service Account
- **Web Framework**: Flask (REST API + Jinja2 Templates)
- **Exporting**: openpyxl (Excel), csv stdlib (CSV)

