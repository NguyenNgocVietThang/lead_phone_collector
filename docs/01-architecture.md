# 01 — Kiến trúc hệ thống

## Tổng quan

**Lead Phone Collector** là tool tự động thu thập số điện thoại khách hàng tiềm năng từ các nguồn dữ liệu công khai, chuẩn hóa, loại trùng và lưu vào database + Google Sheets.

## Luồng dữ liệu

```
┌─────────────────────────────────────────────────────┐
│                   NGUỒN DỮ LIỆU                     │
└───────────────────┬─────────────────────────────────┘
                    │
         ┌──────────┴──────────┐
         ▼                     ▼
   ┌─────────────┐      ┌─────────────┐
   │ Google Maps │      │  Facebook   │
   │  (Selenium) │      │ Graph API / │
   │             │      │  Selenium   │
   └──────┬──────┘      └──────┬──────┘
          │                    │
          └──────────┬──────────┘
                     ▼
          ┌──────────────────┐
          │  Phone Extractor │  ← Regex VN phone patterns
          └────────┬─────────┘
                   ▼
          ┌──────────────────┐
          │ Phone Normalizer │  ← Chuẩn hóa + validate
          └────────┬─────────┘
                   ▼
          ┌──────────────────┐
          │   Deduplicator   │  ← Loại trùng theo normalized
          └────────┬─────────┘
                   │
       ┌───────────┼───────────┐
       ▼           ▼           ▼
 ┌──────────┐ ┌────────┐ ┌──────────┐
 │  SQLite  │ │ Google │ │  Export  │
 │    DB    │ │ Sheets │ │Excel/CSV │
 └──────────┘ └────────┘ └──────────┘
```

## Kiến trúc thư mục

```
lead-phone-collector/
├── collectors/          # Module 1 — Thu thập
│   ├── google_maps.py   
│   └── facebook.py      
├── processors/          # Module 2+3 — Xử lý
│   ├── extractor.py     
│   └── normalizer.py    
├── storage/             # Module 4 — Lưu trữ
│   ├── database.py      
│   └── sheets.py        
├── exporters/           # Module 5 — Xuất file
│   ├── excel_export.py  
│   └── csv_export.py    
├── ui/                  # Giao diện web (Flask)
│   ├── app.py           
│   ├── templates/       
│   └── static/          
├── config/
│   ├── settings.py      
│   └── .env.example     
├── docs/                # Tài liệu
├── tests/               # Unit tests
├── data/
│   ├── leads.db         # Database SQLite
│   └── exports/         # File xuất
├── logs/
├── main.py              # CLI
└── requirements.txt
```

## Các module chính

| Module | File | Chức năng |
|--------|------|-----------|
| Collector | `collectors/google_maps.py` | Selenium scraping Google Maps |
| Collector | `collectors/facebook.py` | Graph API + Selenium public pages |
| Extractor | `processors/extractor.py` | Regex nhận diện SĐT VN |
| Normalizer | `processors/normalizer.py` | Chuẩn hóa + validate + carrier detect |
| Database | `storage/database.py` | SQLite CRUD + dedup |
| Sheets | `storage/sheets.py` | Google Sheets sync |
| Export | `exporters/excel_export.py` | Xuất Excel |
| Export | `exporters/csv_export.py` | Xuất CSV |
| Web UI | `ui/app.py` | Flask dashboard |
| CLI | `main.py` | Command-line interface |

## Stack công nghệ

- **Language**: Python 3.10+
- **Scraping**: Selenium + undetected-chromedriver
- **Database**: SQLite (không cần cài đặt server)
- **Google Sheets**: gspread + Service Account
- **Web UI**: Flask (lightweight)
- **Export**: openpyxl (Excel), csv stdlib (CSV)
