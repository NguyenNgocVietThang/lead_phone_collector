# 04 — Module Facebook

## Tổng quan

Module `collectors/facebook.py` sử dụng **Playwright** (kết hợp với cơ chế **Auth Session Cookies**) để tự động thu thập số điện thoại từ các nguồn Facebook bao gồm:

1. **Fanpages công khai** — Thu thập SĐT từ phần About (Giới thiệu), Bài viết (Posts) và Bình luận (Comments).
2. **Facebook Groups** — Thu thập SĐT từ bài viết và bình luận trong các nhóm công khai hoặc nhóm đã tham gia.
3. **Facebook Search (Từ khóa)** — Tìm kiếm từ khóa bài viết trên Facebook để quét SĐT trực tiếp từ kết quả tìm kiếm.
4. **Graph API** — Dùng khi có `FACEBOOK_ACCESS_TOKEN` cho Fanpage chính chủ.

---

## Phiên đăng nhập & Session Cookies (`storage/auth.py`)

Đối với **Facebook Groups** hoặc **Tìm kiếm từ khóa**, Facebook yêu cầu phiên làm việc đã đăng nhập:

```bash
# Thực hiện đăng nhập tương tác một lần duy nhất
python main.py login --service facebook
```

- Hệ thống mở cửa sổ Chromium để người dùng đăng nhập tài khoản Facebook.
- Session Cookies tự động được lưu vào `data/cookies/fb_cookies.json`.
- Các lượt cào sau sẽ tự động nạp Cookies này để truy cập Facebook dưới dạng tài khoản đã đăng nhập.

---

## Các chế độ hoạt động

### 1. Chế độ Fanpage (`--mode page`)

Thu thập dữ liệu từ một Fanpage cụ thể (không yêu cầu đăng nhập đối với page công khai).

```bash
# CLI
python main.py facebook --mode page --target "https://facebook.com/tenpage" --max-posts 30
```

### 2. Chế độ Facebook Group (`--mode group`)

Thu thập các bài đăng mới nhất và comment trong Facebook Group.

```bash
# CLI
python main.py facebook --mode group --target "https://facebook.com/groups/12345678" --max-posts 50
```

### 3. Chế độ Tìm kiếm từ khóa (`--mode search`)

Tìm kiếm bài viết trên Facebook theo từ khóa (Ví dụ: `"cần tìm mua đất"`, `"tư vấn thiết kế"`) và trích xuất SĐT từ nội dung bài viết và comment.

```bash
# CLI
python main.py facebook --mode search --target "cần thuê nhà hà nội" --max-posts 40
```

---

## Cách dùng qua Python API

```python
from collectors.facebook import FacebookCollector

def on_progress(msg):
 print(f"Status: {msg}")

with FacebookCollector(headless=True, progress_callback=on_progress) as collector:
 # 1. Thu thập từ Page
 res_page = collector.collect(
 target="https://facebook.com/tenpage",
 target_type="page",
 sources=["about", "posts", "comments"],
 max_posts=30
 )

 # 2. Thu thập từ Group
 res_group = collector.collect(
 target="https://facebook.com/groups/12345678",
 target_type="group",
 max_posts=50
 )

 # 3. Thu thập theo từ khóa tìm kiếm
 res_search = collector.collect(
 target="cần mua đất gia lâm",
 target_type="search",
 max_posts=40
 )
```

---

## Giá trị `source` trong Database

Mỗi SĐT tìm được sẽ được gắn nhãn `source` chính xác để dễ dàng truy xuất và lọc:

| Giá trị `source` | Ý nghĩa |
|------------------|---------|
| `fb_playwright_about` | Lấy từ phần "Giới thiệu / About" của Fanpage |
| `fb_playwright_post` | Lấy từ nội dung bài viết trên Fanpage |
| `fb_playwright_comment` | Lấy từ bình luận bài viết trên Fanpage |
| `fb_group_post` | Lấy từ bài viết trong Facebook Group |
| `fb_group_comment` | Lấy từ bình luận trong Facebook Group |
| `fb_search_post` | Lấy từ bài viết trong kết quả Tìm kiếm Facebook |
| `fb_search_comment` | Lấy từ bình luận trong kết quả Tìm kiếm Facebook |
| `fb_graph_post` | Lấy qua Facebook Graph API (Post) |
| `fb_graph_comment` | Lấy qua Facebook Graph API (Comment) |

---

## Dữ liệu trả về (`FbPhoneResult`)

```json
{
 "page_name": "Bất Động Sản Hà Nội",
 "phone_raw": "0981 234 567",
 "phone_normalized": "0981234567",
 "carrier": "Viettel",
 "source": "fb_group_post",
 "source_url": "https://facebook.com/groups/12345678/posts/9999",
 "content": "Chính chủ cần bán gấp nhà 3 tầng, SĐT liên hệ: 0981 234 567..."
}
```

---

## Lưu ý kỹ thuật & Anti-block

- **Delay ngẫu nhiên**: Tự động giả lập độ trễ giữa các lần cuộn trang và đọc comment (`PLAYWRIGHT_DELAY_MIN` & `PLAYWRIGHT_DELAY_MAX`).
- **Tự động khôi phục session**: Nếu cookie hết hạn hoặc bị từ chối, hệ thống cảnh báo người dùng chạy lại command `python main.py login`.
- **Giới hạn số lượng**: Khuyên dùng `--max-posts 30-50` mỗi lượt chạy để đảm bảo an toàn cho tài khoản.

