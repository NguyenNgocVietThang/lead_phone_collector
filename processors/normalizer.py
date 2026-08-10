"""
processors/normalizer.py — Chuẩn hóa và validate số điện thoại Việt Nam.

Chuyển mọi định dạng SĐT về dạng chuẩn: 0XXXXXXXXX (10 chữ số).
Xác định nhà mạng và kiểm tra tính hợp lệ.
"""

import re
import logging
from dataclasses import dataclass
from typing import Optional, List, Set

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Mapping đầu số → nhà mạng
# ---------------------------------------------------------------------------

_CARRIER_MAP: dict[str, str] = {
    # Viettel
    "032": "Viettel", "033": "Viettel", "034": "Viettel", "035": "Viettel",
    "036": "Viettel", "037": "Viettel", "038": "Viettel", "039": "Viettel",
    "086": "Viettel", "096": "Viettel", "097": "Viettel", "098": "Viettel",

    # Mobifone
    "070": "Mobifone", "076": "Mobifone", "077": "Mobifone",
    "078": "Mobifone", "079": "Mobifone",
    "089": "Mobifone", "090": "Mobifone", "093": "Mobifone",

    # Vinaphone
    "081": "Vinaphone", "082": "Vinaphone", "083": "Vinaphone",
    "084": "Vinaphone", "085": "Vinaphone",
    "091": "Vinaphone", "094": "Vinaphone",

    # Vietnamobile
    "052": "Vietnamobile", "056": "Vietnamobile", "058": "Vietnamobile",
    "092": "Vietnamobile",

    # Gmobile
    "059": "Gmobile", "099": "Gmobile",

    # Reddi (Indochina Telecom)
    "055": "Reddi",

    # ITelecom
    "087": "ITelecom",
}

# Tập tất cả đầu số hợp lệ
_VALID_PREFIXES: Set[str] = set(_CARRIER_MAP.keys())


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------

@dataclass
class NormalizedPhone:
    """Kết quả chuẩn hóa một SĐT."""
    raw: str                            # Chuỗi gốc
    normalized: Optional[str]          # SĐT chuẩn hóa (0XXXXXXXXX) hoặc None
    is_valid: bool                     # Hợp lệ theo đầu số VN
    carrier: Optional[str]             # Nhà mạng
    digits_only: str                   # Chỉ chữ số (trước khi chuẩn hóa prefix)

    @property
    def display(self) -> str:
        """Format hiển thị: 0XX XXXX XXXX."""
        if not self.normalized:
            return self.raw
        n = self.normalized
        return f"{n[:4]} {n[4:7]} {n[7:]}"


# ---------------------------------------------------------------------------
# PhoneNormalizer
# ---------------------------------------------------------------------------

class PhoneNormalizer:
    """
    Chuẩn hóa số điện thoại Việt Nam về dạng 0XXXXXXXXX.

    Sử dụng:
        normalizer = PhoneNormalizer()
        result = normalizer.normalize("098 123 4567")
        print(result.normalized)  # "0981234567"
        print(result.carrier)     # "Viettel"
    """

    def normalize(self, raw: str) -> NormalizedPhone:
        """
        Chuẩn hóa một SĐT.

        Args:
            raw: Chuỗi SĐT bất kỳ định dạng.

        Returns:
            NormalizedPhone với các thông tin đã xử lý.
        """
        if not raw or not isinstance(raw, str):
            return NormalizedPhone(raw=str(raw), normalized=None, is_valid=False,
                                   carrier=None, digits_only="")

        # Bước 1: Thay thế 'o' / 'O' ở đầu bằng '0' nếu là số điện thoại dạng chữ
        raw_clean = re.sub(r"^[oO](?=[3-9]|[\s.\-/_])", "0", raw.strip(), flags=re.IGNORECASE)
        digits = re.sub(r"\D", "", raw_clean)

        if not digits:
            return NormalizedPhone(raw=raw, normalized=None, is_valid=False,
                                   carrier=None, digits_only=digits)

        # Bước 2: Chuẩn hóa prefix quốc gia → 0
        normalized = self._normalize_prefix(digits)

        if normalized is None:
            logger.debug("Không thể chuẩn hóa: %s (digits: %s)", raw, digits)
            return NormalizedPhone(raw=raw, normalized=None, is_valid=False,
                                   carrier=None, digits_only=digits)

        # Bước 3: Phải đúng 10 chữ số
        if len(normalized) != 10:
            logger.debug("Sai độ dài (sau normalize: %s): %s", normalized, raw)
            return NormalizedPhone(raw=raw, normalized=None, is_valid=False,
                                   carrier=None, digits_only=digits)

        # Bước 4: Kiểm tra đầu số hợp lệ
        prefix = normalized[:3]
        carrier = _CARRIER_MAP.get(prefix)
        is_valid = prefix in _VALID_PREFIXES

        if not is_valid:
            logger.debug("Đầu số không hợp lệ (%s): %s", prefix, raw)

        return NormalizedPhone(
            raw=raw,
            normalized=normalized,
            is_valid=is_valid,
            carrier=carrier,
            digits_only=digits,
        )

    def normalize_many(self, raws: List[str]) -> List[NormalizedPhone]:
        """Chuẩn hóa danh sách SĐT."""
        return [self.normalize(r) for r in raws]

    def deduplicate(self, phones: List[NormalizedPhone]) -> List[NormalizedPhone]:
        """
        Loại trùng từ danh sách NormalizedPhone đã xử lý.
        Giữ lại lần xuất hiện đầu tiên.
        """
        seen: Set[str] = set()
        result: List[NormalizedPhone] = []
        for p in phones:
            key = p.normalized or p.raw
            if key not in seen:
                seen.add(key)
                result.append(p)
        return result

    # ── Private helpers ────────────────────────────────────────────────────

    def _normalize_prefix(self, digits: str) -> Optional[str]:
        """
        Chuyển prefix về 0.

        Xử lý các trường hợp:
          - 10 chữ số bắt đầu bằng 0  → giữ nguyên
          - 11 chữ số bắt đầu bằng 84 → thay bằng 0
          - 12 chữ số bắt đầu bằng 084 hoặc 084 → xử lý
          - Hỗ trợ số 11 chữ số cũ (trước 2018) → ánh xạ về 10 số
        """
        length = len(digits)

        # Đã đúng 10 chữ số bắt đầu bằng 0
        if length == 10 and digits.startswith("0"):
            return digits

        # 11 chữ số bắt đầu bằng 84 (mã VN không dấu +)
        if length == 11 and digits.startswith("84"):
            return "0" + digits[2:]

        # 12 chữ số bắt đầu bằng 084
        if length == 12 and digits.startswith("084"):
            return "0" + digits[3:]

        # Số 11 chữ số dạng cũ (0162... → 036...)
        if length == 11 and digits.startswith("0"):
            mapped = self._map_old_11_digit(digits)
            if mapped:
                return mapped

        # 9 chữ số (bỏ số 0 đầu) → thêm 0
        if length == 9 and digits[0] in "3456789":
            return "0" + digits

        return None

    @staticmethod
    def _map_old_11_digit(digits: str) -> Optional[str]:
        """
        Ánh xạ số 11 chữ số (định dạng cũ trước 2018) sang 10 chữ số.
        Tham khảo Thông tư 11/2018/TT-BTTTT.
        """
        _OLD_PREFIX_MAP = {
            "0120": "070", "0121": "079", "0122": "077", "0126": "076",
            "0128": "078",  # Mobifone
            "0123": "083", "0124": "084", "0125": "085", "0127": "081",
            "0129": "082",  # Vinaphone
            "0162": "032", "0163": "033", "0164": "034", "0165": "035",
            "0166": "036", "0167": "037", "0168": "038", "0169": "039",  # Viettel
            "0186": "056", "0188": "058",  # Vietnamobile
            "0199": "059",  # Gmobile
        }
        prefix4 = digits[:4]
        if prefix4 in _OLD_PREFIX_MAP:
            return _OLD_PREFIX_MAP[prefix4] + digits[4:]
        return None


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------

def normalize_phone(raw: str) -> NormalizedPhone:
    """Shortcut: chuẩn hóa một SĐT mà không cần khởi tạo class."""
    return PhoneNormalizer().normalize(raw)
