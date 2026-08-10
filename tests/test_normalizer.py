"""
tests/test_normalizer.py — Unit tests cho PhoneNormalizer.
Chạy: pytest tests/test_normalizer.py -v
"""

import pytest
from processors.normalizer import PhoneNormalizer, normalize_phone


@pytest.fixture
def normalizer():
    return PhoneNormalizer()


class TestBasicNormalization:
    """Kiểm tra chuẩn hóa các định dạng phổ biến."""

    def test_plain_10_digits(self, normalizer):
        result = normalizer.normalize("0981234567")
        assert result.normalized == "0981234567"
        assert result.is_valid is True

    def test_space_separated(self, normalizer):
        result = normalizer.normalize("098 123 4567")
        assert result.normalized == "0981234567"

    def test_dot_separated(self, normalizer):
        result = normalizer.normalize("098.123.4567")
        assert result.normalized == "0981234567"

    def test_dash_separated(self, normalizer):
        result = normalizer.normalize("098-123-4567")
        assert result.normalized == "0981234567"

    def test_country_code_plus84(self, normalizer):
        result = normalizer.normalize("+84981234567")
        assert result.normalized == "0981234567"

    def test_country_code_84_no_plus(self, normalizer):
        result = normalizer.normalize("84981234567")
        assert result.normalized == "0981234567"

    def test_country_code_with_spaces(self, normalizer):
        result = normalizer.normalize("+84 98 123 4567")
        assert result.normalized == "0981234567"

    def test_parentheses_format(self, normalizer):
        result = normalizer.normalize("(098) 123-4567")
        assert result.normalized == "0981234567"

    def test_9_digit_no_leading_zero(self, normalizer):
        result = normalizer.normalize("981234567")
        assert result.normalized == "0981234567"


class TestCarrierDetection:
    """Kiểm tra nhận diện nhà mạng."""

    def test_viettel_032(self, normalizer):
        result = normalizer.normalize("0321234567")
        assert result.carrier == "Viettel"

    def test_viettel_098(self, normalizer):
        result = normalizer.normalize("0981234567")
        assert result.carrier == "Viettel"

    def test_mobifone_090(self, normalizer):
        result = normalizer.normalize("0901234567")
        assert result.carrier == "Mobifone"

    def test_mobifone_079(self, normalizer):
        result = normalizer.normalize("0791234567")
        assert result.carrier == "Mobifone"

    def test_vinaphone_091(self, normalizer):
        result = normalizer.normalize("0911234567")
        assert result.carrier == "Vinaphone"

    def test_vinaphone_081(self, normalizer):
        result = normalizer.normalize("0811234567")
        assert result.carrier == "Vinaphone"

    def test_vietnamobile_056(self, normalizer):
        result = normalizer.normalize("0561234567")
        assert result.carrier == "Vietnamobile"

    def test_gmobile_059(self, normalizer):
        result = normalizer.normalize("0591234567")
        assert result.carrier == "Gmobile"


class TestOldNumberMapping:
    """Kiểm tra ánh xạ số 11 chữ số cũ sang 10 chữ số mới."""

    def test_old_viettel_0162(self, normalizer):
        result = normalizer.normalize("01621234567")
        assert result.normalized == "0321234567"
        assert result.carrier == "Viettel"

    def test_old_mobifone_0120(self, normalizer):
        result = normalizer.normalize("01201234567")
        assert result.normalized == "0701234567"
        assert result.carrier == "Mobifone"

    def test_old_vinaphone_0123(self, normalizer):
        result = normalizer.normalize("01231234567")
        assert result.normalized == "0831234567"
        assert result.carrier == "Vinaphone"


class TestValidation:
    """Kiểm tra logic validate."""

    def test_valid_phone(self, normalizer):
        result = normalizer.normalize("0981234567")
        assert result.is_valid is True

    def test_invalid_prefix(self, normalizer):
        result = normalizer.normalize("0201234567")  # 020 không hợp lệ
        assert result.is_valid is False

    def test_too_short(self, normalizer):
        result = normalizer.normalize("09812345")
        assert result.normalized is None
        assert result.is_valid is False

    def test_too_long(self, normalizer):
        result = normalizer.normalize("09812345678901")
        assert result.normalized is None
        assert result.is_valid is False

    def test_empty_string(self, normalizer):
        result = normalizer.normalize("")
        assert result.is_valid is False
        assert result.normalized is None

    def test_no_digits(self, normalizer):
        result = normalizer.normalize("abc xyz")
        assert result.is_valid is False


class TestDeduplication:
    """Kiểm tra loại số trùng."""

    def test_dedup_same_phone_different_format(self, normalizer):
        phones = [
            normalizer.normalize("0981234567"),
            normalizer.normalize("098 123 4567"),
            normalizer.normalize("+84981234567"),
        ]
        deduped = normalizer.deduplicate(phones)
        assert len(deduped) == 1

    def test_dedup_keeps_different_phones(self, normalizer):
        phones = [
            normalizer.normalize("0981234567"),
            normalizer.normalize("0912345678"),
        ]
        deduped = normalizer.deduplicate(phones)
        assert len(deduped) == 2

    def test_dedup_preserves_first(self, normalizer):
        phones = [
            normalizer.normalize("098 123 4567"),   # Lần đầu
            normalizer.normalize("0981234567"),      # Lần 2 — trùng
        ]
        deduped = normalizer.deduplicate(phones)
        assert len(deduped) == 1
        assert deduped[0].raw == "098 123 4567"  # Giữ lần đầu


class TestDisplayFormat:
    """Kiểm tra định dạng hiển thị."""

    def test_display_format(self, normalizer):
        result = normalizer.normalize("0981234567")
        assert result.display == "0981 234 567"


class TestConvenienceFunction:
    """Kiểm tra hàm normalize_phone."""

    def test_normalize_phone_shortcut(self):
        result = normalize_phone("0981234567")
        assert result.normalized == "0981234567"
        assert result.carrier == "Viettel"
