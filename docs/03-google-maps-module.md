# 03 — Module Google Maps

## Tổng quan

Module `collectors/google_maps.py` dựa trên **Playwright Chromium** để tự động điều khiển trình duyệt, duyệt qua các trang kết quả Google Maps theo từ khóa và khu vực (hoặc tọa độ), rồi trích xuất đầy đủ thông tin doanh nghiệp & số điện thoại.

## Cơ chế hoạt động

```
Input: keyword + area
 │
 ▼
Mở Google Maps → Gửi query ("keyword + area") → Chờ trang hiển thị
 │
 ▼
Cuộn danh sách kết quả (Lazy Load scroll container: div[role="feed"])
 │
 ▼
Click lần lượt vào từng Business Card
 │
 ▼
Trích xuất chi tiết: Name, Phone (raw), Address, Website, Rating, Reviews, Maps URL
 │
 ▼
Trích xuất SĐT (Phone Extractor) → Chuẩn hóa & Nhận diện nhà mạng (Normalizer)
 │
 ▼
Lưu vào SQLite DB (Deduplication) → Auto-sync Google Sheets
```

## Cách dùng

### Qua CLI

```bash
# Thu thập mặc định (Headless)
python main.py maps --keyword "quán cà phê" --area "Hà Nội"

# Thu thập kèm giới hạn & Hiển thị trình duyệt trực quan
python main.py maps --keyword "nhà hàng" --area "Đà Nẵng" --limit 50 --show-browser

# Thu thập và tự động xuất file Excel khi hoàn thành
python main.py maps --keyword "khách sạn" --area "Nha Trang" --limit 30 --export excel
```

### Qua Python API

```python
from collectors.google_maps import GoogleMapsCollector

def on_progress(current, total):
 print(f"Progress: {current}/{total}")

with GoogleMapsCollector(headless=True, progress_callback=on_progress) as collector:
 result = collector.search(
 keyword="spa",
 area="TP Hồ Chí Minh",
 limit=50
 )

print(f"Tìm được {result.total_with_phone} SĐT từ {result.total_scraped} địa điểm.")
for biz in result.businesses:
 print(biz.name, biz.phone_normalized, biz.carrier)
```

## Dữ liệu thu thập

| Trường | Kiểu dữ liệu | Mô tả | Ví dụ |
|--------|--------------|-------|-------|
| `name` | `str` | Tên doanh nghiệp / địa điểm | "Cà phê Trung Nguyên" |
| `phone_raw` | `str` | SĐT thô chưa xử lý | "028 3822 1234" |
| `phone_normalized`| `str` | SĐT đã chuẩn hóa 10 chữ số | "02838221234" |
| `carrier` | `str` | Nhà mạng phát hiện | "Viettel", "VNPT / Cố định" |
| `address` | `str` | Địa chỉ đầy đủ | "25 Lê Thánh Tôn, Bến Nghé, Quận 1, HCM" |
| `website` | `str` | URL Website chính thức | "https://trungnguyen.com.vn" |
| `maps_url` | `str` | Đường dẫn Google Maps của địa điểm | "https://www.google.com/maps/place/..." |
| `rating` | `str` | Điểm đánh giá sao (1.0 - 5.0) | "4.5" |
| `reviews_count` | `int` | Số lượng đánh giá người dùng | 250 |

## Anti-block & Tối ưu hóa Scraping

- **Random Delay**: Delay ngẫu nhiên giữa các thao tác click/scroll (cấu hình trong `.env`).
- **Scroll Container Smart Wait**: Tự động phát hiện khi hết danh sách hoặc chạm đáy Google Maps list (`div[role="feed"]`).
- **Element Selector Fallbacks**: Sử dụng bộ selector đa tầng linh hoạt (ARIA labels, text patterns, SVG icons) để chịu đựng sự thay đổi giao diện từ Google Maps.
- **Context Isolation**: Chạy trên Browser Context sạch sẽ của Playwright.

## Giới hạn kỹ thuật

- Google Maps mặc định chỉ hiển thị tối đa **~120 kết quả** trên một lượt tìm kiếm.
- **Mẹo lấy nhiều dữ liệu hơn**: Chia nhỏ khu vực tìm kiếm (Ví dụ: thay vì cào `"quận 1 HCM"`, cào theo từng phường/đường như `"Lê Lợi Quận 1"`, `"Bến Thành Quận 1"`).

## Lưu ý pháp lý

- Chỉ thu thập thông tin doanh nghiệp hiển thị **công khai** trên Google Maps.
- Tuân thủ [Google Maps Terms of Service](https://cloud.google.com/maps-platform/terms).

