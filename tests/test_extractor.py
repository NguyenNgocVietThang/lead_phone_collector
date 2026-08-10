"""
tests/test_extractor.py — Unit tests cho PhoneExtractor.
Chạy: pytest tests/test_extractor.py -v
"""

import pytest
from processors.extractor import PhoneExtractor, ExtractionResult


@pytest.fixture
def extractor():
    return PhoneExtractor()


class TestBasicFormats:
    """Kiểm tra nhận diện các định dạng SĐT cơ bản."""

    def test_plain_10_digits(self, extractor):
        result = extractor.extract("Gọi ngay: 0981234567")
        assert result.total_found == 1
        assert result.matches[0].raw == "0981234567"

    def test_space_separated(self, extractor):
        result = extractor.extract("SĐT: 098 123 4567")
        assert result.total_found == 1
        assert "098" in result.matches[0].raw

    def test_dot_separated(self, extractor):
        result = extractor.extract("098.123.4567")
        assert result.total_found == 1

    def test_dash_separated(self, extractor):
        result = extractor.extract("098-123-4567")
        assert result.total_found == 1

    def test_country_code_plus84(self, extractor):
        result = extractor.extract("+84981234567")
        assert result.total_found == 1

    def test_country_code_space(self, extractor):
        result = extractor.extract("+84 98 123 4567")
        assert result.total_found == 1

    def test_with_parentheses(self, extractor):
        result = extractor.extract("(098) 123-4567")
        assert result.total_found == 1

    def test_group_4_3_4(self, extractor):
        result = extractor.extract("0981 234 567")
        assert result.total_found == 1


class TestMultiplePhones:
    """Kiểm tra nhiều SĐT trong cùng đoạn text."""

    def test_two_phones(self, extractor):
        text = "Gọi 0981234567 hoặc 0912345678"
        result = extractor.extract(text)
        assert result.total_found == 2

    def test_three_phones(self, extractor):
        text = "LH: 0981234567, 0912345678 hoặc 0333444555"
        result = extractor.extract(text)
        assert result.total_found >= 2

    def test_phone_in_sentence(self, extractor):
        text = "Để đặt hàng, vui lòng gọi 0898765432 trong giờ hành chính."
        result = extractor.extract(text)
        assert result.total_found == 1


class TestInvalidNumbers:
    """Kiểm tra các số không phải SĐT VN."""

    def test_long_facebook_id_not_extracted_as_phone(self, extractor):
        # FB ID hoặc timestamp 13-15 chữ số không được bị trích xuất cắt vụn thành SĐT
        text = "Bài viết ID 1000343204188 hoặc 034320418899"
        result = extractor.extract(text)
        assert result.total_found == 0

    def test_phone_next_to_words(self, extractor):
        text = "SĐT0343204188 hoặc 0343204188LH"
        result = extractor.extract(text)
        assert result.total_found == 2

    def test_fb_url_normalization(self):
        from collectors.facebook import _normalize_fb_url
        assert _normalize_fb_url("/groups/123/posts/456") == "https://www.facebook.com/groups/123/posts/456"
        assert _normalize_fb_url("pfbid02xxx") == "https://www.facebook.com/pfbid02xxx"

    def test_random_digits_short(self, extractor):
        result = extractor.extract("Mã đơn: 12345")
        assert result.total_found == 0

    def test_invalid_prefix(self, extractor):
        # Đầu số 01x (đã hết dùng, một số trường hợp không hợp lệ)
        result = extractor.extract("Gọi: 0111111111")
        # Extractor có thể vẫn nhận diện, normalizer mới lọc
        # Test này chỉ kiểm tra extractor không crash
        assert isinstance(result, ExtractionResult)

    def test_empty_string(self, extractor):
        result = extractor.extract("")
        assert result.total_found == 0

    def test_none_input(self, extractor):
        result = extractor.extract(None)
        assert result.total_found == 0


class TestContext:
    """Kiểm tra trích xuất context xung quanh SĐT."""

    def test_context_contains_phone(self, extractor):
        text = "Liên hệ ngay: 0981234567 để nhận ưu đãi"
        result = extractor.extract(text)
        assert result.total_found == 1
        assert "0981234567" in result.matches[0].context

    def test_context_includes_surrounding_text(self, extractor):
        text = "Gọi ngay 0981234567 nhận ưu đãi"
        result = extractor.extract(text)
        context = result.matches[0].context
        # Context phải chứa text xung quanh, không chỉ số điện thoại
        assert len(context) > len("0981234567")

    def test_context_window_truncation(self, extractor):
        # Text rất dài
        prefix = "A" * 200
        text = f"{prefix} 0981234567 {'B' * 200}"
        result = extractor.extract(text)
        assert result.total_found == 1
        # Context phải bắt đầu bằng "..." vì bị cắt
        assert result.matches[0].context.startswith("...")


class TestHasPhone:
    """Kiểm tra method has_phone."""

    def test_has_phone_true(self, extractor):
        assert extractor.has_phone("Gọi 0981234567") is True

    def test_has_phone_false(self, extractor):
        assert extractor.has_phone("Không có số điện thoại") is False

    def test_has_phone_empty(self, extractor):
        assert extractor.has_phone("") is False


class TestRealWorldSamples:
    """Test với dữ liệu thực tế từ Facebook/Maps."""

    def test_facebook_post_style(self, extractor):
        text = """
        🎉 SALE 50% - Liên hệ đặt hàng:
        📞 0981.234.567
        📞 Zalo: 098 123 4567
        """
        result = extractor.extract(text)
        assert result.total_found >= 1

    def test_google_maps_style(self, extractor):
        text = "☎ +84 98 123 4567 | 🌐 website.com | 📍 123 Phố Huế, HN"
        result = extractor.extract(text)
        assert result.total_found == 1

    def test_mixed_content(self, extractor):
        text = "Email: info@company.com | Tel: 090 123 4567 | Hotline: 098 765 4321"
        result = extractor.extract(text)
        # Hai số di động đều hợp lệ
        assert result.total_found >= 2

    def test_facebook_comment_variants(self, extractor):
        text = """
        Thái Hằng: Có zl 0984937323
        Giadung: Sẵn sll giá tốt zalo 0343204188 kho phú lương.
        Nguyen Tmanh: Sẵn giao 0985377965
        Đặng Tùng Dương: ZI 0345277801
        Quốc Việt: ZI 0787066240 Sẵn kho hà đông
        Thư: liên hệ zl em ạ 0356259153
        San San Dương: liên hệ zl em nha 0966521738
        Người dùng O: o984.93.73.23 hoặc 0.9.8.4.9.3.7.3.2.3
        """
        result = extractor.extract(text)
        assert result.total_found >= 9

