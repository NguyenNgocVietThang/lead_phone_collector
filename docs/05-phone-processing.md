# 05 — Xử lý số điện thoại & Engine Tìm kiếm

## 1. Module Extractor (`processors/extractor.py`)

### Các định dạng nhận diện

Hệ thống trích xuất SĐT tự động quét văn bản dựa trên bộ Regex tối ưu cho định dạng SĐT Việt Nam:

| Định dạng | Ví dụ | Regex / Mẫu tương ứng |
|-----------|-------|-----------------------|
| Liền | `0981234567` | `0[3-9]\d{8}` |
| Cách dấu cách | `098 123 4567` | `0[3-9]\d ?\d{3} ?\d{4}` |
| Cách dấu chấm | `098.123.4567` | `0[3-9]\d[.\-]\d{3}[.\-]\d{4}` |
| Cách dấu gạch | `098-123-4567` | `0[3-9]\d[-]\d{3}[-]\d{4}` |
| Mã quốc gia | `+84981234567` | `\+84[3-9]\d{8}` |
| Mã QG + cách | `+84 98 123 4567` | `\+84 ?[3-9]\d ?...` |
| Có ngoặc | `(098) 123-4567` | `\(0[3-9]\d\) ?\d{3}...` |
| Chữ số Việt đặc biệt | `0.981.234.567` | Variant dot pattern |

### Context Extraction (Ngữ cảnh SĐT)

Khi tìm thấy SĐT, module trích xuất đoạn văn bản xung quanh (context window: ±50 ký tự) để phục vụ việc hiển thị nguồn bài viết hoặc nội dung liên quan:

```python
text = "Liên hệ đặt hàng: 0981234567. Giao hàng toàn quốc, miễn phí ship."
# Kết quả context: "Liên hệ đặt hàng: 0981234567. Giao hàng toàn quốc..."
```

---

## 2. Module Normalizer (`processors/normalizer.py`)

### Quy tắc chuẩn hóa SĐT

1. Xóa tất cả ký tự không phải số (khoảng trắng, dấu chấm, dấu gạch ngang, ngoặc đơn).
2. Chuyển đổi mã quốc gia `+84` hoặc `84` ở đầu thành `0`.
3. Kiểm tra độ dài chuẩn (đúng 10 chữ số).
4. Kiểm tra đầu số mạng viễn thông Việt Nam hợp lệ.

### Kiểm tra đầu số & Nhà mạng (Carrier Detection)

| Đầu số | Nhà mạng tương ứng |
|--------|-------------------|
| 032, 033, 034, 035, 036, 037, 038, 039, 086, 096, 097, 098 | **Viettel** |
| 070, 076, 077, 078, 079, 089, 090, 093 | **Mobifone** |
| 081, 082, 083, 084, 085, 088, 091, 094 | **Vinaphone** |
| 056, 058, 092 | **Vietnamobile** |
| 059, 099 | **Gmobile** |
| 055 | **Itelecom (Wintel)** |

### Trả về đối tượng `NormalizedPhone`

```python
{
 "raw": "+84 (98) 123-4567",
 "normalized": "0981234567",
 "is_valid": True,
 "carrier": "Viettel",
 "confidence": 1.0
}
```

---

## 3. Fuzzy Search & Tìm kiếm không dấu Engine (`storage/database.py`)

Hệ thống hỗ trợ cơ chế tìm kiếm **Fuzzy Match** (Khớp một phần và loại bỏ dấu tiếng Việt) trên Web UI & Database query.

### Chức năng `remove_accents(text)`

Chuyển đổi văn bản có dấu sang không dấu, chuyển chữ thường và chuẩn hóa khoảng trắng:
- `"Cà phê Trung Nguyên"` → `"ca phe trung nguyen"`
- `"Đà Nẵng"` → `"da nang"`

### Chế độ tìm kiếm (`match_type`)

1. **`match_type="exact"`**: Tìm kiếm khớp chính xác chuỗi.
2. **`match_type="fuzzy"`**:
 - Loại bỏ toàn bộ dấu tiếng Việt từ câu truy vấn và từ dữ liệu trong database (`name`, `content`, `address`).
 - Tìm kiếm khớp một phần với SĐT (VD: gõ `9812` sẽ tìm thấy các lead có SĐT chứa `0981234567`).
 - Khớp từ khóa theo từng phần của địa chỉ, tên trang, hoặc đoạn văn bản chứa SĐT.

---

## 4. Deduplication (Loại trùng tự động)

- Mỗi SĐT sau khi chuẩn hóa (`phone_normalized`) được đánh chỉ mục `UNIQUE` trong cơ sở dữ liệu SQLite.
- Thao tác chèn dữ liệu sử dụng lệnh `INSERT OR IGNORE`.
- Khi thu thập trùng một SĐT từ nhiều bài viết hoặc nguồn khác nhau, hệ thống **bỏ qua bản ghi trùng** để bảo toàn thời gian và thông tin thu thập ban đầu.

