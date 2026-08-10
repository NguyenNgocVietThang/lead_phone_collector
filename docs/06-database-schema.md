# 06 — Database Schema

## Tổng quan

Dùng **SQLite** — không cần cài đặt server, file database tự tạo tại `data/leads.db`.

---

## Bảng `leads` — Dữ liệu chính

```sql
CREATE TABLE IF NOT EXISTS leads (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT,
    phone_raw           TEXT NOT NULL,
    phone_normalized    TEXT UNIQUE NOT NULL,
    source              TEXT NOT NULL,
    source_url          TEXT,
    content             TEXT,
    address             TEXT,
    website             TEXT,
    carrier             TEXT,
    status              TEXT DEFAULT 'new',
    notes               TEXT,
    collected_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### Mô tả các cột

| Cột | Kiểu | Mô tả |
|-----|------|-------|
| `id` | INTEGER | Primary key tự tăng |
| `name` | TEXT | Tên doanh nghiệp / trang / người |
| `phone_raw` | TEXT | SĐT gốc chưa xử lý |
| `phone_normalized` | TEXT UNIQUE | SĐT đã chuẩn hóa (dùng để dedup) |
| `source` | TEXT | Nguồn dữ liệu (xem bảng dưới) |
| `source_url` | TEXT | URL của trang chứa SĐT |
| `content` | TEXT | Đoạn text xung quanh SĐT (context) |
| `address` | TEXT | Địa chỉ (chủ yếu từ Google Maps) |
| `website` | TEXT | Website (nếu có) |
| `carrier` | TEXT | Nhà mạng (Viettel/Mobifone/...) |
| `status` | TEXT | Trạng thái lead (xem bảng dưới) |
| `notes` | TEXT | Ghi chú thủ công |
| `collected_at` | DATETIME | Thời gian thu thập |
| `updated_at` | DATETIME | Thời gian cập nhật cuối |

### Giá trị `source`

| Giá trị | Mô tả |
|---------|-------|
| `google_maps` | Google Maps (Selenium) |
| `fb_graph_post` | Facebook Graph API — từ post |
| `fb_graph_comment` | Facebook Graph API — từ comment |
| `fb_selenium_about` | Facebook Selenium — phần About |
| `fb_selenium_post` | Facebook Selenium — nội dung post |
| `fb_selenium_comment` | Facebook Selenium — comment |

### Giá trị `status`

| Giá trị | Mô tả |
|---------|-------|
| `new` | Mới thu thập, chưa xử lý |
| `contacted` | Đã liên hệ |
| `qualified` | Đã xác nhận là khách tiềm năng |
| `rejected` | Loại (sai số, không phù hợp) |

---

## Bảng `collection_jobs` — Theo dõi công việc

```sql
CREATE TABLE IF NOT EXISTS collection_jobs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source          TEXT NOT NULL,
    query           TEXT,
    status          TEXT DEFAULT 'running',
    total_found     INTEGER DEFAULT 0,
    new_leads       INTEGER DEFAULT 0,
    duplicates      INTEGER DEFAULT 0,
    started_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    finished_at     DATETIME,
    error_message   TEXT
);
```

| Cột | Mô tả |
|-----|-------|
| `source` | `google_maps` hoặc `facebook` |
| `query` | Từ khóa hoặc URL đã tìm |
| `status` | `running` / `done` / `failed` |
| `total_found` | Tổng SĐT tìm được |
| `new_leads` | SĐT mới (chưa có trong DB) |
| `duplicates` | SĐT bị trùng (đã bỏ qua) |

---

## Indexes

```sql
CREATE INDEX IF NOT EXISTS idx_leads_source ON leads(source);
CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
CREATE INDEX IF NOT EXISTS idx_leads_collected_at ON leads(collected_at);
CREATE INDEX IF NOT EXISTS idx_leads_carrier ON leads(carrier);
```

---

## Queries hữu ích

```sql
-- Đếm lead theo nguồn
SELECT source, COUNT(*) as total FROM leads GROUP BY source;

-- Lead mới hôm nay
SELECT * FROM leads WHERE date(collected_at) = date('now');

-- Leads của Viettel chưa liên hệ
SELECT * FROM leads WHERE carrier = 'Viettel' AND status = 'new';

-- Tổng thống kê
SELECT
    COUNT(*) as total,
    SUM(CASE WHEN status = 'new' THEN 1 ELSE 0 END) as new_count,
    SUM(CASE WHEN status = 'contacted' THEN 1 ELSE 0 END) as contacted,
    COUNT(DISTINCT carrier) as carriers
FROM leads;
```
