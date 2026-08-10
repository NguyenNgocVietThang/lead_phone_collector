# 03 — Module Google Maps

## Tổng quan

Module `collectors/google_maps.py` dùng **Selenium** để tự động duyệt Google Maps, tìm kiếm doanh nghiệp theo từ khóa và khu vực, rồi trích xuất thông tin liên lạc.

## Cơ chế hoạt động

```
Input: keyword + area
       │
       ▼
Mở Google Maps → Nhập query → Đợi kết quả
       │
       ▼
Scroll danh sách kết quả (lazy load)
       │
       ▼
Click từng business card
       │
       ▼
Lấy: name, phone, address, website, maps_url, rating
       │
       ▼
Phone Extractor → Normalizer → DB
```

## Cách dùng

### Qua CLI

```bash
# Cơ bản
python main.py maps --keyword "quán cà phê" --area "Hà Nội"

# Với giới hạn số lượng
python main.py maps --keyword "nhà hàng" --area "Đà Nẵng" --limit 100

# Kết quả tự động lưu DB + sync Sheets
```

### Qua Python API

```python
from collectors.google_maps import GoogleMapsCollector

collector = GoogleMapsCollector()
results = collector.search(
    keyword="spa",
    area="TP Hồ Chí Minh",
    limit=50
)
# results: List[dict] với các key: name, phone, address, website, maps_url
```

## Dữ liệu thu thập

| Trường | Mô tả | Ví dụ |
|--------|-------|-------|
| `name` | Tên doanh nghiệp | "Cà phê Trung Nguyên" |
| `phone` | Số điện thoại (raw) | "028 3822 1234" |
| `address` | Địa chỉ đầy đủ | "25 Lê Thánh Tôn, Q1, HCM" |
| `website` | Website (nếu có) | "trungnguyen.com.vn" |
| `maps_url` | Link Google Maps | "https://maps.google.com/..." |
| `rating` | Đánh giá (nếu có) | "4.3" |
| `reviews_count` | Số đánh giá | "128" |

## Anti-block measures

- **Random delay** giữa các request (cấu hình qua `.env`)
- **undetected-chromedriver** để tránh bot detection
- **Human-like scroll** trong danh sách kết quả
- **User-Agent rotation** (tùy chọn)

## Giới hạn

- Google Maps thường hiển thị tối đa **~120 kết quả** cho một query
- Để có nhiều hơn: chia nhỏ khu vực (VD: "quận 1", "quận 2" thay vì "HCM")
- Không phải doanh nghiệp nào cũng có số điện thoại trên Maps

## Lưu ý pháp lý

- Chỉ thu thập dữ liệu **công khai** mà Google Maps hiển thị cho mọi người
- Không thu thập dữ liệu cá nhân, chỉ thông tin doanh nghiệp
- Tuân thủ [Google Maps Terms of Service](https://cloud.google.com/maps-platform/terms)
