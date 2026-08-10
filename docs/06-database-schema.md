# 06 — Database Schema

## Tổng quan

Cơ sở dữ liệu sử dụng **SQLite** (`data/leads.db`) — zero-config, không cần cài đặt database server. Tự động khởi tạo schema & indexes khi ứng dụng chạy lần đầu.

---

## Bảng `leads` — Dữ liệu SĐT & Khách hàng

```sql
CREATE TABLE IF NOT EXISTS leads (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 name TEXT,
 phone_raw TEXT NOT NULL,
 phone_normalized TEXT UNIQUE NOT NULL,
 source TEXT NOT NULL,
 source_url TEXT,
 content TEXT,
 address TEXT,
 website TEXT,
 carrier TEXT,
 status TEXT DEFAULT 'new',
 notes TEXT,
 collected_at DATETIME DEFAULT CURRENT_TIMESTAMP,
 updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### Mô tả các cột

| Cột | Kiểu dữ liệu | Mô tả |
|-----|--------------|-------|
| `id` | INTEGER | Primary Key tự tăng |
| `name` | TEXT | Tên doanh nghiệp / Fanpage / Người đăng bài |
| `phone_raw` | TEXT | SĐT thô ban đầu trích xuất được |
| `phone_normalized` | TEXT UNIQUE | SĐT chuẩn hóa 10 chữ số (khóa loại trùng) |
| `source` | TEXT | Mã nhận diện nguồn dữ liệu (xem bảng dưới) |
| `source_url` | TEXT | Đường dẫn URL bài viết / trang chứa SĐT |
| `content` | TEXT | Đoạn văn bản chứa SĐT (Ngữ cảnh / Context) |
| `address` | TEXT | Địa chỉ (trích xuất từ Google Maps) |
| `website` | TEXT | Trang web chính thức |
| `carrier` | TEXT | Nhà mạng (Viettel, Mobifone, Vinaphone, ...) |
| `status` | TEXT | Trạng thái lead (`new`, `contacted`, `qualified`, `rejected`) |
| `notes` | TEXT | Ghi chú người dùng |
| `collected_at` | DATETIME | Thời điểm thu thập |
| `updated_at` | DATETIME | Thời điểm cập nhật cuối |

### Danh sách đầy đủ giá trị `source`

| Giá trị | Mô tả nguồn dữ liệu |
|---------|---------------------|
| `google_maps` | Thu thập từ Google Maps (Playwright) |
| `fb_playwright_about` | Facebook Fanpage — phần "Giới thiệu" công khai |
| `fb_playwright_post` | Facebook Fanpage — bài viết công khai |
| `fb_playwright_comment` | Facebook Fanpage — bình luận bài viết |
| `fb_group_post` | Facebook Group — bài viết trong nhóm |
| `fb_group_comment` | Facebook Group — bình luận bài viết trong nhóm |
| `fb_search_post` | Facebook Search — bài viết tìm theo từ khóa |
| `fb_search_comment` | Facebook Search — bình luận tìm theo từ khóa |
| `fb_graph_post` | Facebook Graph API — bài viết |
| `fb_graph_comment` | Facebook Graph API — bình luận |

### Giá trị `status`

| Trạng thái | Mô tả |
|------------|-------|
| `new` | Lead mới thu thập, chưa xử lý |
| `contacted` | Đã liên hệ (gọi điện / nhắn tin) |
| `qualified` | Đã xác nhận nhu cầu (khách tiềm năng) |
| `rejected` | Đã loại (sai số / không nghe máy / từ chối) |

---

## Bảng `collection_jobs` — Lịch sử & Tiến độ Thu thập

```sql
CREATE TABLE IF NOT EXISTS collection_jobs (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 source TEXT NOT NULL,
 query TEXT,
 status TEXT DEFAULT 'running',
 total_found INTEGER DEFAULT 0,
 new_leads INTEGER DEFAULT 0,
 duplicates INTEGER DEFAULT 0,
 started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
 finished_at DATETIME,
 error_message TEXT
);
```

| Cột | Mô tả |
|-----|-------|
| `source` | Nguồn thu thập (`google_maps`, `facebook`, ...) |
| `query` | Từ khóa, địa bàn, hoặc URL target |
| `status` | Trạng thái công việc (`running`, `done`, `failed`) |
| `total_found` | Tổng số SĐT quét được |
| `new_leads` | Số SĐT mới được ghi vào DB |
| `duplicates` | Số SĐT trùng đã bỏ qua |

---

## Indexes & Tối ưu truy vấn

```sql
CREATE INDEX IF NOT EXISTS idx_leads_source ON leads(source);
CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
CREATE INDEX IF NOT EXISTS idx_leads_collected_at ON leads(collected_at);
CREATE INDEX IF NOT EXISTS idx_leads_carrier ON leads(carrier);
```

---

## SQL Queries & Python API hữu ích

### 1. Python Fuzzy Search Query (`storage/database.py`)

```python
from storage.database import LeadDatabase

db = LeadDatabase()

# Tìm kiếm fuzzy (không dấu, khớp một phần)
leads = db.search_leads(
 query="ha noi", # Khớp với "Hà Nội", "Hanoi", "HÀ NỘI"
 source="fb_group_post", # Lọc theo nguồn
 carrier="Viettel", # Lọc nhà mạng
 status="new", # Lọc trạng thái
 match_type="fuzzy", # Chế độ fuzzy match
 limit=50
)
```

### 2. Thống kê theo nguồn và nhà mạng

```sql
-- Đếm tổng số SĐT theo nhà mạng
SELECT carrier, COUNT(*) as count FROM leads GROUP BY carrier ORDER BY count DESC;

-- Đếm số leads thu thập theo nguồn
SELECT source, COUNT(*) as total FROM leads GROUP BY source;

-- Tỷ lệ lead mới trong ngày hôm nay
SELECT
 COUNT(*) as total_today,
 SUM(CASE WHEN status = 'new' THEN 1 ELSE 0 END) as new_today
FROM leads
WHERE date(collected_at) = date('now');
```

