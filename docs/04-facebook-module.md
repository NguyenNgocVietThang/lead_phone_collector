# 04 — Module Facebook

## Tổng quan

Module `collectors/facebook.py` thu thập số điện thoại từ **dữ liệu Facebook công khai**. Hoạt động theo 2 chế độ tự động:

1. **Graph API** — dùng khi có `FACEBOOK_ACCESS_TOKEN` (page do mình quản lý)
2. **Selenium public** — dùng cho Facebook page công khai (không cần đăng nhập)

## ⚠️ Giới hạn và quy tắc

- **Không đăng nhập** vào Facebook (Selenium chạy không có session)
- **Không bypass CAPTCHA** hay bất kỳ cơ chế bảo vệ nào
- **Không thu thập** profile cá nhân hay dữ liệu yêu cầu đăng nhập
- Chỉ đọc nội dung hiển thị công khai cho mọi người (không đăng nhập)

## Chế độ 1 — Facebook Graph API

### Khi nào dùng

- Page do bạn sở hữu hoặc quản lý
- Bạn có `Page Access Token` hợp lệ

### Cấu hình

```env
FACEBOOK_ACCESS_TOKEN=EAABsbCS...
```

### Cách dùng

```python
from collectors.facebook import FacebookCollector

collector = FacebookCollector()
results = collector.collect_from_page(
    page_id="your_page_id_or_username",
    sources=["posts", "comments"]
)
```

### Dữ liệu lấy được

- Posts của page: trích xuất SĐT trong nội dung
- Comments của posts: trích xuất SĐT công khai
- About section: số điện thoại đã khai báo công khai

## Chế độ 2 — Selenium Public (không đăng nhập)

### Khi nào dùng

- Facebook page công khai bất kỳ
- Không cần/không có Access Token
- Nội dung hiển thị được khi mở URL không cần login

### Cách dùng

```bash
# Qua CLI
python main.py facebook --url "https://www.facebook.com/tenpage"

# Qua Python
collector = FacebookCollector()
results = collector.collect_public_page(
    page_url="https://www.facebook.com/tenpage",
    sources=["about", "posts", "comments"],
    max_posts=50
)
```

### Dữ liệu lấy được

| Nguồn | Nội dung thu thập |
|-------|-------------------|
| `about` | Số điện thoại trong phần "Giới thiệu" công khai |
| `posts` | Văn bản posts hiển thị khi chưa đăng nhập |
| `comments` | Comments hiển thị công khai trong posts |

## Dữ liệu đầu ra

```json
{
  "name": "Tên trang / Tên người đăng",
  "phone_raw": "0981 234 567",
  "source": "fb_selenium_post",
  "source_url": "https://facebook.com/post/123456",
  "content": "Liên hệ đặt hàng: 0981 234 567. Giao hàng toàn quốc."
}
```

### Giá trị `source`

| Giá trị | Mô tả |
|---------|-------|
| `fb_graph_post` | Graph API — từ post của page mình |
| `fb_graph_comment` | Graph API — từ comment |
| `fb_selenium_about` | Selenium — từ phần About công khai |
| `fb_selenium_post` | Selenium — từ nội dung post công khai |
| `fb_selenium_comment` | Selenium — từ comment công khai |

## Giới hạn kỹ thuật

- Selenium public chỉ thấy ~10-20 posts đầu tiên (Facebook lazy load)
- Số lượng comments hiển thị bị giới hạn (thường 5-10 mỗi post)
- Facebook có thể thay đổi HTML bất kỳ lúc nào → cần cập nhật selectors
