# 05 — Xử lý số điện thoại

## Module Extractor (`processors/extractor.py`)

### Các định dạng nhận diện

| Định dạng | Ví dụ | Regex tương ứng |
|-----------|-------|-----------------|
| Liền | `0981234567` | `0[3-9]\d{8}` |
| Cách dấu cách | `098 123 4567` | `0[3-9]\d ?\d{3} ?\d{4}` |
| Cách dấu chấm | `098.123.4567` | `0[3-9]\d[.\-]\d{3}[.\-]\d{4}` |
| Cách dấu gạch | `098-123-4567` | `0[3-9]\d[-]\d{3}[-]\d{4}` |
| Mã quốc gia | `+84981234567` | `\+84[3-9]\d{8}` |
| Mã QG + cách | `+84 98 123 4567` | `\+84 ?[3-9]\d ?...` |
| Có ngoặc | `(098) 123-4567` | `\(0[3-9]\d\) ?\d{3}...` |
| Chữ số Việt đặc biệt | `0.981.234.567` | Variant dot pattern |

### Context Extraction

Khi tìm thấy SĐT, module cũng trích xuất đoạn văn bản xung quanh (context window: ±50 ký tự):

```python
# Ví dụ
text = "Liên hệ đặt hàng: 0981234567. Giao hàng toàn quốc, miễn phí ship."
# Kết quả context: "Liên hệ đặt hàng: 0981234567. Giao hàng toàn q"
```

---

## Module Normalizer (`processors/normalizer.py`)

### Quy tắc chuẩn hóa

1. Xóa tất cả ký tự không phải số: `0 981-234.567` → `0981234567`
2. Chuyển `+84` → `0`: `+84981234567` → `0981234567`
3. Chuyển `84` đầu → `0`: `84981234567` → `0981234567`
4. Đảm bảo đúng 10 chữ số

### Kiểm tra đầu số hợp lệ

| Đầu số | Nhà mạng |
|--------|----------|
| 032–039 | Viettel |
| 086, 096, 097, 098 | Viettel |
| 070, 076, 077, 078, 079 | Mobifone |
| 089, 090, 093 | Mobifone |
| 081, 082, 083, 084, 085 | Vinaphone |
| 091, 094 | Vinaphone |
| 056, 058, 092 | Vietnamobile |
| 055, 059 | Gmobile |
| 058 | Reddi |

### Kết quả trả về

```python
{
    "raw": "098 123 4567",
    "normalized": "0981234567",
    "is_valid": True,
    "carrier": "Viettel",
    "confidence": 1.0   # 0.0-1.0
}
```

### Ví dụ thực tế

```python
from processors.normalizer import PhoneNormalizer

normalizer = PhoneNormalizer()

# Test các định dạng
print(normalizer.normalize("+84981234567"))
# → {"normalized": "0981234567", "is_valid": True, "carrier": "Viettel"}

print(normalizer.normalize("098.123.4567"))
# → {"normalized": "0981234567", "is_valid": True, "carrier": "Viettel"}

print(normalizer.normalize("12345678"))
# → {"normalized": None, "is_valid": False, "carrier": None}
```

---

## Deduplication

- Dựa trên trường `phone_normalized` (UNIQUE trong SQLite)
- Khi insert, nếu trùng → bỏ qua (INSERT OR IGNORE)
- Không xóa bản ghi cũ → bảo toàn dữ liệu nguồn đầu tiên tìm được
