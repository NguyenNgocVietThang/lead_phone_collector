# 06 — Cơ sở dữ liệu & Schema

Tài liệu chi tiết về cấu trúc các bảng dữ liệu, ràng buộc khóa, các chỉ mục (Indexes) và truy vấn SQL/Python API trong cơ sở dữ liệu **SQLite** (`data/leads.db`).

---

## Tổng quan

Cơ sở dữ liệu của dự án sử dụng **SQLite3** (`data/leads.db`) — giải pháp zero-configuration, không yêu cầu cài đặt database server phức tạp. Hệ thống tự động kiểm tra và khởi tạo tất cả các bảng (tables) cùng chỉ mục (indexes) ngay lần đầu ứng dụng chạy.

---

## Cấu trúc Chi tiết các Bảng Dữ liệu

### 1. Bảng `leads` — Dữ liệu SĐT & Thông tin Khách hàng

Lưu trữ danh sách số điện thoại đã thu thập và chuẩn hóa.

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
    collector_user      TEXT,
    collected_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

#### Mô tả các Cột trong bảng `leads`:

| Tên Cột | Kiểu Dữ Liệu | Ràng Buộc | Mô Tả Chi Tiết |
|---------|--------------|-----------|----------------|
| `id` | INTEGER | PRIMARY KEY | ID tự động tăng |
| `name` | TEXT | Nullable | Tên doanh nghiệp / Fanpage / Người đăng bài |
| `phone_raw` | TEXT | NOT NULL | Chuỗi SĐT thô ban đầu trích xuất được |
| `phone_normalized` | TEXT | UNIQUE NOT NULL | SĐT đã chuẩn hóa 10 chữ số (Khóa loại trùng) |
| `source` | TEXT | NOT NULL | Mã nhận diện nguồn dữ liệu |
| `source_url` | TEXT | Nullable | Đường dẫn URL bài viết / trang chứa SĐT |
| `content` | TEXT | Nullable | Đoạn văn bản ngữ cảnh xung quanh SĐT |
| `address` | TEXT | Nullable | Địa chỉ (trích xuất từ Google Maps) |
| `website` | TEXT | Nullable | Trang web chính thức |
| `carrier` | TEXT | Nullable | Nhà mạng (Viettel, Mobifone, Vinaphone, ...) |
| `status` | TEXT | DEFAULT 'new' | Trạng thái lead (`new`, `contacted`, `qualified`, `rejected`) |
| `notes` | TEXT | Nullable | Ghi chú người dùng |
| `collector_user` | TEXT | Nullable | Tên hoặc ID tài khoản kích hoạt job thu thập |
| `collected_at` | DATETIME | CURRENT_TIMESTAMP | Thời điểm thu thập ban đầu |
| `updated_at` | DATETIME | CURRENT_TIMESTAMP | Thời điểm cập nhật dữ liệu gần nhất |

---

### 2. Bảng `collection_jobs` — Tiến độ & Lịch sử Thu thập

Lưu vết tất cả các phiên chạy scraper (Maps & Facebook).

```sql
CREATE TABLE IF NOT EXISTS collection_jobs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source          TEXT NOT NULL,
    query           TEXT,
    status          TEXT DEFAULT 'running',
    total_found     INTEGER DEFAULT 0,
    new_leads       INTEGER DEFAULT 0,
    duplicates      INTEGER DEFAULT 0,
    collector_user  TEXT,
    started_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    finished_at     DATETIME,
    error_message   TEXT
);
```

#### Mô tả các Cột trong bảng `collection_jobs`:

| Tên Cột | Kiểu Dữ Liệu | Mô Tả |
|---------|--------------|-------|
| `id` | INTEGER | ID công việc |
| `source` | TEXT | Nguồn chạy (`google_maps`, `facebook`) |
| `query` | TEXT | Từ khóa, địa bàn hoặc URL mục tiêu |
| `status` | TEXT | Trạng thái (`running`, `done`, `failed`) |
| `total_found` | INTEGER | Tổng số SĐT tìm thấy |
| `new_leads` | INTEGER | Số SĐT mới thêm vào DB |
| `duplicates` | INTEGER | Số SĐT trùng đã bỏ qua |
| `collector_user` | TEXT | Tên người dùng kích hoạt job |
| `started_at` | DATETIME | Thời điểm bắt đầu |
| `finished_at` | DATETIME | Thời điểm hoàn thành |
| `error_message` | TEXT | Thông báo lỗi nếu thất bại |

---

### 3. Bảng `users` — Tài khoản Người dùng Web UI

Lưu trữ thông tin tài khoản đăng nhập Web UI Dashboard.

```sql
CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name       TEXT NOT NULL,
    email           TEXT UNIQUE NOT NULL,
    password_hash   TEXT,
    auth_provider   TEXT DEFAULT 'email',
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_login      DATETIME
);
```

---

### 4. Bảng `oauth_identities` — Liên kết OAuth Provider

Lưu trữ liên kết danh tính Google / Facebook OAuth.

```sql
CREATE TABLE IF NOT EXISTS oauth_identities (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             INTEGER NOT NULL,
    provider            TEXT NOT NULL,
    provider_subject    TEXT NOT NULL,
    provider_email      TEXT NOT NULL,
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_login          DATETIME,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(provider, provider_subject)
);
```

---

## Danh mục Giá trị chuẩn

### Danh sách Nguồn dữ liệu (`source`)
- `google_maps_details` / `google_maps`: Thu thập từ Google Maps.
- `fb_playwright_about`: Trang Facebook — Phần Giới thiệu (About).
- `fb_playwright_post`: Trang Facebook — Bài viết công khai.
- `fb_playwright_comment`: Trang Facebook — Bình luận bài viết.
- `fb_group_post`: Facebook Group — Bài viết trong nhóm.
- `fb_group_comment`: Facebook Group — Bình luận trong nhóm.
- `fb_search_post`: Facebook Search — Bài viết tìm theo từ khóa.
- `fb_search_comment`: Facebook Search — Bình luận tìm theo từ khóa.
- `fb_graph_post`: Facebook Graph API — Bài viết.
- `fb_graph_comment`: Facebook Graph API — Bình luận.

### Danh sách Trạng thái Lead (`status`)
- `new`: Lead mới thu thập, chưa xử lý.
- `contacted`: Đã liên hệ (gọi điện/nhắn tin).
- `qualified`: Khách hàng tiềm năng đã xác nhận nhu cầu.
- `rejected`: Đã loại bỏ (sai số, không nghe máy, từ chối).

---

## Indexes & Tối ưu hóa Truy vấn

Tự động đánh chỉ mục trên các cột thường xuyên lọc và tìm kiếm:

```sql
CREATE INDEX IF NOT EXISTS idx_leads_source ON leads(source);
CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
CREATE INDEX IF NOT EXISTS idx_leads_collected_at ON leads(collected_at);
CREATE INDEX IF NOT EXISTS idx_leads_carrier ON leads(carrier);
```

---

## Python API & Truy vấn mẫu

### Tìm kiếm Fuzzy Search với Python API

```python
from storage.database import LeadDatabase

db = LeadDatabase()

# Tra cứu danh sách leads với bộ lọc
leads = db.search_leads(
    query="ha noi",           # Khớp "Hà Nội", "Hanoi", "ha noi"
    source="fb_group_post",   # Lọc theo nguồn
    carrier="Viettel",        # Lọc theo nhà mạng
    status="new",             # Lọc trạng thái
    match_type="fuzzy",       # Chế độ fuzzy match không dấu
    limit=50
)
```
