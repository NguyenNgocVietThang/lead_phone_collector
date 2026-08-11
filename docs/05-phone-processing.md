# 05 — Xử lý số điện thoại & Engine Tìm kiếm

Tài liệu kỹ thuật chi tiết về hai module cốt lõi **Extractor** (`processors/extractor.py`) và **Normalizer** (`processors/normalizer.py`), cùng với thuật toán **Fuzzy Search không dấu** và **Cơ chế Loại bỏ Trùng lặp (Deduplication)**.

---

## 1. Module Extractor (`processors/extractor.py`)

### Các mẫu định dạng SĐT Việt Nam được hỗ trợ

Module Extractor quét văn bản thô dựa trên bộ quy tắc Regular Expressions (Regex) được thiết kế tối ưu riêng cho 10+ mẫu định dạng SĐT thường gặp tại Việt Nam:

| Định Dạng Phổ Biến | Mẫu Văn Bản Ví Dụ | Regex / Pattern Tương Ứng |
|--------------------|-------------------|---------------------------|
| **Viết liền** | `0981234567` | `0[3-9]\d{8}` |
| **Cách dấu cách** | `098 123 4567`, `0981 234 567` | `0[3-9]\d ?\d{3} ?\d{4}` |
| **Cách dấu chấm** | `098.123.4567`, `0981.234.567` | `0[3-9]\d[.\-]\d{3}[.\-]\d{4}` |
| **Cách dấu gạch ngang** | `098-123-4567` | `0[3-9]\d[-]\d{3}[-]\d{4}` |
| **Mã quốc gia Việt Nam** | `+84981234567`, `84981234567` | `(?:\+?84)[3-9]\d{8}` |
| **Mã quốc gia cách** | `+84 98 123 4567` | `\+84 ?[3-9]\d ?...` |
| **Bao trong ngoặc đơn** | `(098) 123-4567`, `(+84) 981234567` | `\(0[3-9]\d\) ?\d{3}...` |
| **Viết chấm kiểu cũ** | `0.981.234.567` | Variant dot regex pattern |

### Trích xuất Ngữ cảnh (Context Window)

Không chỉ trích xuất SĐT, module còn tự động cắt đoạn văn bản xung quanh SĐT (bán kính ±50 ký tự) để phục vụ làm dữ liệu ngữ cảnh (`content`) hiển thị trên báo cáo và Web UI:

```python
raw_text = "Cần bán gấp lô đất tại Gia Lâm. Giá 2 tỷ. Liên hệ chính chủ SĐT: 0981 234 567 (miễn trung gian)."

# Kết quả Extractor:
# phone_raw: "0981 234 567"
# context: "Cần bán gấp lô đất tại Gia Lâm. Giá 2 tỷ. Liên hệ chính chủ SĐT: 0981 234 567 (miễn trung gian)."
```

---

## 2. Module Normalizer (`processors/normalizer.py`)

### Quy trình chuẩn hóa SĐT

1. **Làm sạch ký tự**: Xóa toàn bộ ký tự không phải số ngoại trừ dấu `+` ở đầu.
2. **Chuyển đổi Mã quốc gia**: Biến đổi các tiền tố `+84` hoặc `84` ở đầu chuỗi thành `0`.
3. **Kiểm tra độ dài**: Xác minh chuỗi SĐT sau chuẩn hóa có độ dài chính xác **10 chữ số**.
4. **Xác minh đầu số**: Kiểm tra 3 chữ số đầu tiên có thuộc danh sách đầu số được cấp phép bởi Bộ Thông tin & Truyền thông Việt Nam hay không.
5. **Nhận diện nhà mạng**: Phân loại nhà mạng cung cấp dịch vụ tương ứng.

### Bảng nhận diện Nhà mạng (Carrier Detection)

| Đầu Số Thuộc Mạng | Nhà Mạng Viễn Thông |
|-------------------|---------------------|
| `032`, `033`, `034`, `035`, `036`, `037`, `038`, `039`, `086`, `096`, `097`, `098` | **Viettel** |
| `070`, `076`, `077`, `078`, `079`, `089`, `090`, `093` | **Mobifone** |
| `081`, `082`, `083`, `084`, `085`, `088`, `091`, `094` | **Vinaphone** |
| `056`, `058`, `092` | **Vietnamobile** |
| `059`, `099` | **Gmobile** |
| `055` | **Itelecom (Wintel)** |

### Đối tượng trả về `NormalizedPhone`

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

## 3. Fuzzy Search Engine & Loại bỏ dấu tiếng Việt (`storage/database.py`)

Hệ thống tích hợp thuật toán xử lý chuỗi tiếng Việt chuyên sâu giúp tìm kiếm nhanh chóng trên Database và Web UI.

### Thuật toán `remove_accents(input_str)`

Sử dụng chuẩn Unicode NFD kết hợp thay thế chữ cái đặc biệt `đ/Đ`:

```python
def remove_accents(input_str: Optional[str]) -> str:
    if not input_str:
        return ""
    s = str(input_str).replace("đ", "d").replace("Đ", "d")
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.lower()
    return re.sub(r"\s+", " ", s).strip()
```

Ví dụ chuyển đổi:
- `"Cà Phê Trung Nguyên Legend"` → `"ca phe trung nguyen legend"`
- `"Đà Nẵng"` → `"da nang"`

### Chế độ Tìm kiếm (`match_type`)

- **`match_type="exact"`**: Tìm kiếm chính xác tuyệt đối từng ký tự.
- **`match_type="fuzzy"`**:
  - Chuẩn hóa câu truy vấn của người dùng thành không dấu chữ thường.
  - Khớp linh hoạt một phần SĐT (Ví dụ: Nhập `9812` sẽ tìm ra các SĐT chứa `0981234567`).
  - Khớp từ khóa trên các trường địa chỉ (`address`), tên trang/doanh nghiệp (`name`) và ngữ cảnh (`content`).

---

## 4. Automatic Deduplication (Cơ chế Loại trùng tự động)

- Mỗi số điện thoại sau khi chuẩn hóa (`phone_normalized`) được thiết lập ràng buộc **`UNIQUE`** trong bảng `leads` của cơ sở dữ liệu SQLite.
- Thao tác ghi dữ liệu sử dụng câu lệnh `INSERT OR IGNORE`.
- Khi scraper quét trùng một SĐT từ nhiều bài viết hoặc nguồn khác nhau, hệ thống tự động **bỏ qua bản ghi trùng**, giúp tiết kiệm dung lượng lưu trữ và giữ nguyên thời điểm thu thập ban đầu.
