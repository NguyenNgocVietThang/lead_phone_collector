# 03 — Module Google Maps

## Tổng quan

Module `collectors/google_maps.py` chịu trách nhiệm tự động thu thập thông tin doanh nghiệp, cửa hàng, địa điểm dịch vụ và trích xuất số điện thoại từ **Google Maps** bằng giải pháp tự động hóa trình duyệt **Playwright Chromium**.

Hệ thống hỗ trợ tìm kiếm linh hoạt theo từ khóa và địa bàn, tự động cuộn trang kết quả (Lazy Load Feed), click truy cập từng địa điểm để bóc tách thông tin liên hệ chi tiết và lưu trực tiếp vào cơ sở dữ liệu.

---

## Luồng hoạt động kỹ thuật

```text
                  Input: Từ khóa (keyword) + Khu vực (area)
                                   │
                                   ▼
          Khởi tạo Playwright Chromium Browser & New Context
                                   │
                                   ▼
         Truy cập Google Maps → Gửi câu truy vấn: "keyword + area"
                                   │
                                   ▼
   Tự động cuộn danh sách kết quả (Lazy Load Feed Container: div[role="feed"])
                                   │
                                   ▼
           Lặp qua từng Card Địa điểm → Click xem chi tiết
                                   │
                                   ▼
 Bóc tách dữ liệu: Tên, SĐT thô, Địa chỉ, Website, Rating, Reviews, URL Maps
                                   │
                                   ▼
 Trích xuất SĐT (Phone Extractor) → Chuẩn hóa & Nhận diện nhà mạng (Normalizer)
                                   │
                                   ▼
  Lưu vào Database (SQLite Dedup) → Tự động đẩy sang Google Sheets (Auto-Sync)
```

---

## Cách sử dụng

### 1. Sử dụng qua CLI (Command Line)

```bash
# Thu thập mặc định ở chế độ ẩn (Headless)
python main.py maps --keyword "quán cà phê" --area "Hà Nội"

# Giới hạn số lượng & Hiển thị cửa sổ trình duyệt trực quan
python main.py maps --keyword "nhà hàng" --area "Đà Nẵng" --limit 50 --show-browser

# Thu thập và tự động xuất dữ liệu ra file Excel khi hoàn thành
python main.py maps --keyword "khách sạn" --area "Nha Trang" --limit 30 --export excel
```

### 2. Sử dụng qua Python API

```python
from collectors.google_maps import GoogleMapsCollector

def on_progress(current, total):
    print(f"Tiến độ: {current}/{total}")

# Khởi tạo collector
with GoogleMapsCollector(headless=True, progress_callback=on_progress) as collector:
    result = collector.search(
        keyword="spa thẩm mỹ",
        area="TP Hồ Chí Minh",
        limit=50
    )

print(f"Đã tìm thấy {result.total_with_phone} SĐT từ tổng số {result.total_scraped} địa điểm.")

for biz in result.businesses:
    if biz.phone_normalized:
        print(f"Tên: {biz.name} | SĐT: {biz.phone_normalized} | Mạng: {biz.carrier} | ĐC: {biz.address}")
```

---

## Các trường dữ liệu trích xuất

| Trường Dữ Liệu | Kiểu Dữ Liệu | Mô Tả | Mẫu Giá Trị |
|----------------|--------------|-------|-------------|
| `name` | `str` | Tên thương hiệu / địa điểm doanh nghiệp | `"Cà Phê Trung Nguyên Legend"` |
| `phone_raw` | `str` | Chuỗi số điện thoại thô trích xuất được | `"028 3822 1234"` |
| `phone_normalized` | `str` | SĐT chuẩn hóa 10 chữ số (đầu `0`) | `"02838221234"` |
| `carrier` | `str` | Nhà mạng viễn thông phát hiện | `"VNPT / Cố định"` |
| `address` | `str` | Địa chỉ đầy đủ | `"123 Nguyễn Huệ, Bến Nghé, Quận 1, Hồ Chí Minh"` |
| `website` | `str` | Trang web chính thức của địa điểm | `"https://trungnguyenlegend.com"` |
| `maps_url` | `str` | URL trực tiếp tới địa điểm trên Google Maps | `"https://www.google.com/maps/place/..."` |
| `rating` | `str` | Điểm đánh giá trung bình (1.0 - 5.0) | `"4.6"` |
| `reviews_count` | `int` | Tổng số lượt đánh giá | `450` |
| `source` | `str` | Nguồn dữ liệu | `"google_maps_details"` |

---

## Anti-block & Tối ưu hóa Scraping

1. **Randomized Human Delays**: Tự động chèn khoảng trễ ngẫu nhiên giữa các thao tác cuộn chuột và click card (`PLAYWRIGHT_DELAY_MIN` đến `PLAYWRIGHT_DELAY_MAX`).
2. **Lazy Load Feed Handling**: Cuộn cuộn container `div[role="feed"]` linh hoạt, tự động phát hiện khi kết quả hết hoặc không còn bản ghi mới.
3. **Multi-Selector Fallbacks**: Hệ thống áp dụng bộ selector dự phòng đa tầng (ARIA Labels, Text content, Class Names, SVG Icon parents) để chống chịu các đợt cập nhật giao diện của Google Maps.
4. **Isolated Browser Context**: Mỗi tác vụ chạy trên một Playwright Context sạch sẽ, không lưu trữ cache hay history dơ.

---

## Giới hạn kỹ thuật & Mẹo nâng cao

- **Giới hạn mặc định**: Google Maps chỉ hiển thị tối đa khoảng **120 - 150 địa điểm** cho một chuỗi từ khóa tìm kiếm trên một khu vực rộng.
- **Mẹo thu thập dữ liệu lớn (Max Yield)**:
  - Chia nhỏ khu vực địa lý: Thay vì tìm kiếm `"spa Hà Nội"`, hãy chia nhỏ theo từng quận/huyện hoặc tên đường (`"spa Quận Cầu Giấy"`, `"spa Đường Trần Duy Hưng"`).
  - Kết hợp từ khóa ngách: Dùng các từ khóa cụ thể hơn như `"spa chăm sóc da"`, `"tiệm gội đầu dưỡng sinh"`.
