# 07 — Hướng dẫn Export

## Định dạng hỗ trợ

| Định dạng | File | Phù hợp |
|-----------|------|---------|
| Excel (.xlsx) | `exporters/excel_export.py` | Dùng ngay trong Excel, có format đẹp |
| CSV (.csv) | `exporters/csv_export.py` | Import vào CRM, Google Sheets thủ công |

---

## Export Excel

### Qua Web UI

1. Mở `http://localhost:5000/leads`
2. Áp dụng bộ lọc nếu cần (theo nguồn, trạng thái, ngày)
3. Click nút **"Tải Excel"**

### Qua CLI

```bash
# Xuất tất cả leads
python main.py export --format excel

# Xuất theo nguồn
python main.py export --format excel --source google_maps

# Xuất leads mới (status=new)
python main.py export --format excel --status new

# Chỉ định file output
python main.py export --format excel --output "d:\bao_cao_leads.xlsx"
```

### Cấu trúc file Excel

Sheet **"Leads"**:

| Cột | Nội dung |
|-----|---------|
| A | ID |
| B | Tên |
| C | Số điện thoại |
| D | Nhà mạng |
| E | Nguồn |
| F | URL nguồn |
| G | Địa chỉ |
| H | Website |
| I | Nội dung chứa SĐT |
| J | Trạng thái |
| K | Ngày thu thập |

Sheet **"Thống kê"**: tóm tắt số lượng theo nguồn và nhà mạng.

---

## Export CSV

```bash
python main.py export --format csv --output "leads.csv"
```

- Encoding: **UTF-8 BOM** (tương thích Excel tiếng Việt)
- Delimiter: dấu phẩy (`,`)
- Có header row

---

## Google Sheets (Tự động)

Sync tự động sau mỗi job thu thập. Không cần thao tác thủ công.

### Cấu hình

```env
GOOGLE_SHEET_ID=1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms
GOOGLE_SHEET_NAME=Leads
```

### Cấu trúc Sheet

Row 1 là header cố định:
```
ID | Tên | Số điện thoại | Nhà mạng | Nguồn | URL | Địa chỉ | Website | Trạng thái | Ngày
```

### Logic sync

- Kiểm tra `phone_normalized` đã có trong Sheet chưa
- Nếu chưa → append row mới
- Không ghi đè hay xóa dữ liệu cũ
- Sync bất đồng bộ (không block quá trình thu thập)

---

## File đặt tên tự động

Export files được đặt tên theo timestamp:

```
data/exports/
├── leads_20260810_143022.xlsx
├── leads_20260810_143022.csv
└── leads_google_maps_20260810_150000.xlsx
```
