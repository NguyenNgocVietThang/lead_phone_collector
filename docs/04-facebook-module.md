# 04 — Module Facebook

## Tổng quan

Module `collectors/facebook.py` sử dụng **Playwright Chromium** kết hợp cơ chế **Auth Session Cookies** để tự động quét và bóc tách số điện thoại khách hàng tiềm năng từ các kênh công khai và bán công khai trên Facebook.

---

## Các chế độ thu thập (Collector Modes)

1. **Chế độ Fanpage (`--mode page`)**:
   - Thu thập SĐT từ phần "Giới thiệu / About" của Trang.
   - Thu thập SĐT từ danh sách các bài viết mới nhất trên Fanpage.
   - Thu thập SĐT từ các bình luận (Comments) bên dưới bài viết.

2. **Chế độ Facebook Groups (`--mode group`)**:
   - Quét các bài đăng mới nhất và bình luận trong các Nhóm Facebook công khai hoặc Nhóm riêng tư mà tài khoản đã tham gia.
   - Yêu cầu phải nạp Session Cookies đã đăng nhập.

3. **Chế độ Tìm kiếm từ khóa bài viết (`--mode search`)**:
   - Tìm kiếm các bài viết công khai trên Facebook theo từ khóa (Ví dụ: `"cần tìm mua nhà"`, `"tư vấn thiết kế"`, `"cần thuê mặt bằng"`).
   - Quét nội dung bài đăng và tất cả bình luận để lấy SĐT.

4. **Facebook Graph API (`fb_graph`)**:
   - Tự động kích hoạt nếu người dùng cấu hình `FACEBOOK_ACCESS_TOKEN` trong `.env` để thu thập dữ liệu nhanh chóng qua API chính thức cho Fanpage sở hữu.

---

## Session & Cookie Manager (`storage/auth.py`)

Đối với **Facebook Groups** và **Facebook Search**, Facebook bắt buộc yêu cầu phiên làm việc đã đăng nhập tài khoản. 

Hệ thống cung cấp quy trình lưu Cookie độc lập:

```bash
# Khởi động trình duyệt đăng nhập tương tác
python main.py login --service facebook
```

- Trình duyệt Chromium mở ra để người dùng đăng nhập tài khoản Facebook cá nhân/phụ.
- Thao tác thành công sẽ ghi nhận Session Cookies vào file: `data/cookies/fb_cookies.json`.
- Các lượt cào sau sẽ tự động đọc file này để truy cập Facebook dưới danh nghĩa tài khoản đã đăng nhập mà không cần login lại.

---

## Cách sử dụng

### 1. Sử dụng qua CLI (Command Line)

```bash
# 1. Thu thập từ Fanpage công khai
python main.py facebook --mode page --target "https://facebook.com/tenpage" --max-posts 30

# 2. Thu thập từ Facebook Group
python main.py facebook --mode group --target "https://facebook.com/groups/12345678" --max-posts 50

# 3. Thu thập từ Tìm kiếm từ khóa bài viết
python main.py facebook --mode search --target "cần tìm mua đất gia lâm" --max-posts 40

# 4. Tự động nhận diện chế độ theo URL / Từ khóa (--mode auto)
python main.py facebook --target "https://facebook.com/groups/12345678"
```

### 2. Sử dụng qua Python API

```python
from collectors.facebook import FacebookCollector

def on_progress(msg: str):
    print(f"Status: {msg}")

with FacebookCollector(headless=True, progress_callback=on_progress) as collector:
    # Thu thập từ Group
    result = collector.collect(
        target="https://facebook.com/groups/12345678",
        target_type="group",
        max_posts=30
    )

print(f"Tổng SĐT tìm thấy: {result.total_found}")

for r in result.results:
    print(f"Tên: {r.page_name} | SĐT: {r.phone_normalized} | Nguồn: {r.source} | URL: {r.source_url}")
```

---

## Phân loại Nguồn dữ liệu (`source`) trong Database

Mỗi SĐT thu thập từ Facebook sẽ được gán nhãn `source` cụ thể để dễ dàng quản lý và lọc báo cáo:

| Giá trị `source` | Ý nghĩa Nguồn Thu Thập |
|------------------|------------------------|
| `fb_playwright_about` | Lấy từ phần "Giới thiệu / About" của Fanpage |
| `fb_playwright_post` | Lấy từ nội dung bài viết trên Fanpage |
| `fb_playwright_comment` | Lấy từ bình luận bên dưới bài viết Fanpage |
| `fb_group_post` | Lấy từ bài viết trong Facebook Group |
| `fb_group_comment` | Lấy từ bình luận trong bài viết Facebook Group |
| `fb_search_post` | Lấy từ bài viết trong kết quả Tìm kiếm Facebook |
| `fb_search_comment` | Lấy từ bình luận trong kết quả Tìm kiếm Facebook |
| `fb_graph_post` | Lấy từ bài viết qua Facebook Graph API |
| `fb_graph_comment` | Lấy từ bình luận qua Facebook Graph API |

---

## Cấu trúc Dữ liệu Trả về (`FbPhoneResult`)

```json
{
  "page_name": "Bất Động Sản Hà Nội",
  "phone_raw": "0981 234 567",
  "phone_normalized": "0981234567",
  "carrier": "Viettel",
  "source": "fb_group_post",
  "source_url": "https://facebook.com/groups/12345678/posts/9999",
  "content": "Chính chủ cần bán gấp nhà 3 tầng tại Cầu Giấy, SĐT liên hệ: 0981 234 567..."
}
```

---

## Anti-block & Khuyên dùng AN TOÀN

1. **Số lượng bài viết hợp lý**: Khuyên dùng `--max-posts 30-50` cho mỗi lượt chạy. Không cào liên tục số lượng bài quá lớn trong thời gian ngắn.
2. **Sử dụng tài khoản phụ (Clone)**: Nên dùng tài khoản Facebook phụ để thực hiện `python main.py login`.
3. **Giả lập hành vi người dùng**: Hệ thống tự động cuộn trang ngẫu nhiên, dừng nghỉ giữa các bài viết và mở rộng bình luận giống hành vi người dùng thật.
4. **Cảnh báo hết hạn Session**: Khi cookie bị đứt hoặc hết hạn, log hệ thống sẽ thông báo người dùng thực hiện lại câu lệnh `python main.py login --service facebook`.
