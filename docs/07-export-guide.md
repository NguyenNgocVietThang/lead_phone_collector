# 07 — Hướng dẫn Export & Tích hợp Google Sheets

## Các định dạng xuất dữ liệu

| Định dạng | File thực thi | Phù hợp cho |
|-----------|---------------|-------------|
| **Excel (.xlsx)** | `exporters/excel_export.py` | Báo cáo chuyên nghiệp, có định dạng cột, màu sắc & sheet Thống kê |
| **CSV (.csv)** | `exporters/csv_export.py` | Tích hợp CRM, hệ thống Telesale, Google Sheets thủ công (UTF-8 BOM) |
| **Google Sheets** | `storage/sheets.py` | Đồng bộ dữ liệu tự động thời gian thực qua Cloud API |

---

## 1. Export Excel (.xlsx)

### Qua Web UI

1. Đăng nhập Web UI tại `http://localhost:5000/leads`.
2. Áp dụng bộ lọc tùy chọn (Từ khóa fuzzy search, Nguồn, Nhà mạng, Trạng thái, Khoảng ngày).
3. Bấm nút **"Xuất Excel"** để tải file xuống trình duyệt.

### Qua CLI

```bash
# Xuất toàn bộ danh sách leads
python main.py export --format excel

# Xuất có bộ lọc nguồn & trạng thái
python main.py export --format excel --source fb_group_post --status new

# Chỉ định đường dẫn lưu file cụ thể
python main.py export --format excel --output "d:\bao_cao_khach_hang.xlsx"
```

### Cấu trúc file Excel được tạo

- **Sheet 1: "Leads"** (Định dạng tiêu đề nổi bật, tự động căn chỉnh độ rộng cột):
 - Cột A: ID
 - Cột B: Tên trang / Khách hàng
 - Cột C: Số điện thoại (Format Text giữ nguyên số `0` ở đầu)
 - Cột D: Nhà mạng (Viettel, Vinaphone, Mobifone, ...)
 - Cột E: Nguồn thu thập
 - Cột F: Đường dẫn URL bài viết / trang
 - Cột G: Địa chỉ (Google Maps)
 - Cột H: Website
 - Cột I: Trạng thái (`new`, `contacted`, `qualified`, `rejected`)
 - Cột J: Ghi chú
 - Cột K: Thời điểm thu thập

- **Sheet 2: "Thống kê"**:
 - Bảng tổng hợp số lượng SĐT theo từng Nguồn dữ liệu.
 - Bảng phân bố thị phần theo từng Nhà mạng viễn thông.

---

## 2. Export CSV (.csv)

```bash
python main.py export --format csv --output "leads.csv"
```

- **Mã hóa Encoding**: `UTF-8 với BOM` (`utf-8-sig`) — Tự động hiển thị đúng tiếng Việt có dấu khi mở trực tiếp bằng Microsoft Excel mà không bị lỗi font.
- **Ký tự phân cách (Delimiter)**: Dấu phẩy (`,`).

---

## 3. Tự động Sync với Google Sheets (`storage/sheets.py`)

Hệ thống hỗ trợ tự động đẩy dữ liệu SĐT mới thu thập sang Google Sheet trực tuyến sau mỗi lần scraper chạy thành công.

### Cấu hình `.env`

```env
GOOGLE_SHEET_ID=1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms
GOOGLE_SHEETS_CREDENTIALS_FILE=config/google-service-account.json
```

### Cấu trúc Google Sheet

Dòng 1 là Tiêu đề cột (Header row) chuẩn:
```
ID | Tên | Số điện thoại | Nhà mạng | Nguồn | URL | Địa chỉ | Website | Trạng thái | Ngày thu thập
```

### Nguyên lý hoạt động Sync

1. Khi một job thu thập hoàn tất, hệ thống nạp các bản ghi SĐT mới.
2. Kiểm tra danh sách `phone_normalized` đã tồn tại trên Sheet hay chưa.
3. Chỉ thực hiện **`append_rows`** đối với các bản ghi mới (không ghi đè, không nhân bản dữ liệu cũ).
4. Đảm bảo chạy mượt mà không làm gián đoạn tiến trình scraper chính.

---

## Quản lý File Export tự động

Các file xuất mặc định được lưu tự động tại thư mục `data/exports/` gắn kèm timestamp thời gian:

```
data/exports/
├── leads_20260810_143022.xlsx
├── leads_20260810_143022.csv
└── leads_facebook_20260810_150000.xlsx
```

