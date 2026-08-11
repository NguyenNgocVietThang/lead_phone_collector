# 07 — Hướng dẫn Export & Tích hợp Google Sheets

Tài liệu chi tiết hướng dẫn xuất báo cáo dữ liệu số điện thoại ra định dạng **Excel (.xlsx)**, **CSV (UTF-8 BOM)** và cơ chế **Đồng bộ Tự động với Google Sheets**.

---

## Các định dạng xuất dữ liệu được hỗ trợ

| Định Dạng | File Thực Thi | Phù Hợp Cho | Đặc Điểm Nổi Bật |
|-----------|---------------|-------------|------------------|
| **Excel (.xlsx)** | `exporters/excel_export.py` | Báo cáo chuyên nghiệp, trình trình bày lãnh đạo | Hỗ trợ 2 Sheet (Danh sách Leads chi tiết + Sheet Thống kê nguồn & thị phần nhà mạng), format cột đẹp mắt. |
| **CSV (.csv)** | `exporters/csv_export.py` | Tích hợp hệ thống CRM, Telesale, Auto-dialer | Mã hóa `UTF-8 với BOM` (`utf-8-sig`) giúp Microsoft Excel mở trực tiếp không bị lỗi font tiếng Việt. |
| **Google Sheets** | `storage/sheets.py` | Quản lý đội nhóm thời gian thực | Tự động đẩy bản ghi mới sang Google Sheet trực tuyến sau mỗi lần scraper chạy thành công. |

---

## 1. Xuất file Excel (.xlsx)

### Thao tác trên Web UI

1. Truy cập Web UI tại: `http://localhost:5000/leads`.
2. Áp dụng các bộ lọc tùy chọn (Từ khóa Fuzzy Search, Nguồn, Nhà mạng, Trạng thái).
3. Nhấp vào nút **"Xuất Excel"** trên thanh công cụ để tải file xuống trình duyệt.

### Thao tác qua CLI (Command Line)

```bash
# Xuất toàn bộ danh sách leads ra file Excel mặc định trong data/exports/
python main.py export --format excel

# Xuất có bộ lọc Nguồn và Trạng thái
python main.py export --format excel --source fb_group_post --status new

# Chỉ định tên file và đường dẫn xuất cụ thể
python main.py export --format excel --output "d:\baocao_leads_kinhdoanh.xlsx"
```

### Cấu trúc File Excel (.xlsx) được tạo:

- **Sheet 1: "Leads"**:
  - Cột A: `ID` (Mã số lead)
  - Cột B: `Tên trang / Khách hàng`
  - Cột C: `Số điện thoại` (Định dạng Text chuẩn giữ số `0` ở đầu)
  - Cột D: `Nhà mạng` (Viettel, Vinaphone, Mobifone, Vietnamobile, ...)
  - Cột E: `Nguồn thu thập`
  - Cột F: `URL` (Đường dẫn bài viết / trang / Maps)
  - Cột G: `Địa chỉ`
  - Cột H: `Website`
  - Cột I: `Trạng thái` (`new`, `contacted`, `qualified`, `rejected`)
  - Cột J: `Ghi chú`
  - Cột K: `Ngày thu thập`

- **Sheet 2: "Thống kê"**:
  - Bảng tổng hợp số lượng SĐT thu thập theo từng Nguồn dữ liệu.
  - Bảng tổng hợp cơ cấu thị phần số lượng SĐT theo từng Nhà mạng viễn thông.

---

## 2. Xuất file CSV (.csv)

```bash
# Xuất dữ liệu ra file CSV
python main.py export --format csv --output "data/exports/leads_moi.csv"
```

### Đặc tính kỹ thuật CSV:
- **Encoding**: `UTF-8 với BOM` (`utf-8-sig`).
- **Ký tự phân cách**: Dấu phẩy (`,`).
- **Khắc phục lỗi font**: Khi nhấp đúp mở trực tiếp file CSV bằng Microsoft Excel trên Windows, tất cả ký tự tiếng Việt có dấu và số điện thoại giữ nguyên chữ số `0` đầu tiên đều hiển thị mượt mà không bị lỗi mã mã hiển thị.

---

## 3. Đồng bộ Tự động với Google Sheets (`storage/sheets.py`)

Hệ thống tích hợp thư viện `gspread` kết hợp Google Sheets API v4 để tự động đẩy dữ liệu sang Cloud.

### Cấu hình biến môi trường trong `.env`

```dotenv
GOOGLE_SHEET_ID=1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms
GOOGLE_SHEETS_CREDENTIALS_FILE=config/google-service-account.json
```

### Tiêu đề Cột Chuẩn trên Google Sheet (Header Row - Dòng 1)

Ensure dòng đầu tiên trên Google Sheet có thứ tự cột như sau:

```text
ID | Tên | Số điện thoại | Nhà mạng | Nguồn | URL | Địa chỉ | Website | Trạng thái | Ngày thu thập
```

### Nguyên lý hoạt động Sync Tự động:

1. Ngay khi một Job scraper hoàn tất (Maps hoặc Facebook), hệ thống gọi `GoogleSheetsSync().sync_leads(...)`.
2. Đọc danh sách `phone_normalized` hiện đã có trên Sheet.
3. Chỉ thực hiện **`append_rows`** đối với các số điện thoại mới chưa có trên Sheet.
4. Quá trình chạy ngầm mượt mà, không làm gián đoạn scraper hay treo giao diện Web UI.

---

## Quản lý Thư mục File Export

Các file xuất tự động qua CLI hoặc tự động sau scraper sẽ được lưu trữ tại thư mục `data/exports/` kèm dấu mốc thời gian (Timestamp):

```text
data/exports/
├── leads_20260811_143022.xlsx
├── leads_20260811_143022.csv
└── leads_facebook_20260811_150000.xlsx
```
