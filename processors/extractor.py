"""
processors/extractor.py — Trích xuất số điện thoại từ văn bản.

Module này nhận diện tất cả định dạng SĐT Việt Nam phổ biến bằng regex
và trả về danh sách các SĐT tìm thấy cùng với context (đoạn văn xung quanh).
"""

import re
import logging
from dataclasses import dataclass, field
from typing import List

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regex patterns nhận diện SĐT Việt Nam
# ---------------------------------------------------------------------------

# Ký tự phân cách hợp lệ giữa các nhóm số (cách, chấm, gạch ngang, gạch chéo, gạch dưới)
_SEP = r"[\s.\-/_]*"
_SEP1 = r"[\s.\-/_]?"

# Pattern đầu số VN hợp lệ (03x, 05x, 07x, 08x, 09x) và dạng viết thay 0 bằng o/O, cho phép phân cách giữa các chữ số đầu
_VN_PREFIX_10 = r"[0oO]" + _SEP1 + r"[3-9]" + _SEP1 + r"\d"
_VN_PREFIX_OLD_11 = r"[0oO]" + _SEP1 + r"1" + _SEP1 + r"[2689]" + _SEP1 + r"\d"

# ---------------------------------------------------------------------------
# Tập hợp pattern — hỗ trợ mọi kiểu gõ (chấm, cách, 2-2-2, từng số, o/O...)
# Đã bổ sung boundary (?<!\d) và (?!\d) để không cắt vụn chữ số từ ID / chuỗi số dài
# ---------------------------------------------------------------------------
_PATTERNS: List[str] = [
    # --- Mã quốc gia +84 hoặc 84 ---
    rf"(?<!\d)\+84{_SEP1}[3-9]{_SEP1}\d{_SEP}(?:\d{_SEP}){{7}}(?!\d)",   # +84 98 123 4567 / +84.98.123.4567
    rf"(?<!\d)84{_SEP1}[3-9]{_SEP1}\d{_SEP}(?:\d{_SEP}){{7}}(?!\d)",      # 84981234567 / 84.98.123.4567

    # --- Có ngoặc (098) / (o98) ---
    rf"(?<!\d)\({_VN_PREFIX_10}\){_SEP}(?:\d{_SEP}){{7}}(?!\d)",         # (098) 123-4567 / (o98) 123 4567

    # --- Số 11 chữ số cũ (012x, 016x, 018x, 019x) ---
    rf"(?<!\d){_VN_PREFIX_OLD_11}{_SEP}(?:\d{_SEP}){{7}}(?!\d)",

    # --- Định dạng 10 chữ số chuẩn & biến thể (098 123 4567, 0984.93.73.23, o984937323, 0.9.8.4...) ---
    rf"(?<!\d){_VN_PREFIX_10}{_SEP}(?:\d{_SEP}){{7}}(?!\d)",
]

# Compile tất cả patterns, kết hợp bằng OR
_COMPILED_PATTERN = re.compile(
    "|".join(f"(?:{p})" for p in _PATTERNS),
    re.UNICODE | re.IGNORECASE,
)

# Window trích xuất context (số ký tự về mỗi phía)
_CONTEXT_WINDOW = 60


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class PhoneMatch:
    """Kết quả một lần nhận diện SĐT."""
    raw: str                            # Chuỗi SĐT gốc (chưa xử lý)
    context: str                        # Đoạn text xung quanh SĐT
    position: int                       # Vị trí bắt đầu trong text gốc
    source_text_preview: str = ""       # Preview 100 ký tự đầu của text gốc


@dataclass
class ExtractionResult:
    """Kết quả trích xuất từ một đoạn văn bản."""
    matches: List[PhoneMatch] = field(default_factory=list)
    total_found: int = 0

    def __post_init__(self):
        self.total_found = len(self.matches)


# ---------------------------------------------------------------------------
# PhoneExtractor
# ---------------------------------------------------------------------------

class PhoneExtractor:
    """
    Trích xuất số điện thoại Việt Nam từ văn bản thuần.

    Sử dụng:
        extractor = PhoneExtractor()
        result = extractor.extract("Liên hệ: 098 123 4567 hoặc +84981234567")
        for match in result.matches:
            print(match.raw, match.context)
    """

    def __init__(self, context_window: int = _CONTEXT_WINDOW):
        self.context_window = context_window
        self._pattern = _COMPILED_PATTERN

    def extract(self, text: str) -> ExtractionResult:
        """
        Trích xuất tất cả SĐT từ `text`.

        Args:
            text: Văn bản cần xử lý.

        Returns:
            ExtractionResult chứa danh sách PhoneMatch.
        """
        if not text or not isinstance(text, str):
            return ExtractionResult()

        # Làm sạch: chuẩn hóa khoảng trắng thừa
        cleaned = " ".join(text.split())

        matches: List[PhoneMatch] = []
        seen_positions: set = set()

        for m in self._pattern.finditer(cleaned):
            raw = m.group(0).strip()
            start = m.start()
            end = m.end()

            # Tránh nhận diện cùng vị trí 2 lần (do OR pattern)
            if start in seen_positions:
                continue

            # Đảm bảo không nằm sát chữ số ở 2 đầu (loại bỏ trường hợp cắt lẻ từ ID)
            if start > 0 and cleaned[start - 1].isdigit():
                continue
            if end < len(cleaned) and cleaned[end].isdigit():
                continue

            seen_positions.add(start)

            # Lọc sơ bộ: phải có từ 9 đến 12 chữ số liên tiếp sau khi loại sep
            digits_only = re.sub(r"\D", "", raw)
            if len(digits_only) < 9 or len(digits_only) > 12:
                continue

            context = self._extract_context(cleaned, start, end)
            preview = cleaned[:100]
            matches.append(PhoneMatch(
                raw=raw,
                context=context,
                position=start,
                source_text_preview=preview,
            ))

            logger.debug("Tìm thấy SĐT: %s tại vị trí %d", raw, start)

        result = ExtractionResult(matches=matches)
        if result.total_found > 0:
            logger.info("Trích xuất %d SĐT từ văn bản.", result.total_found)

        return result

    def extract_all(self, texts: List[str]) -> ExtractionResult:
        """
        Trích xuất từ nhiều đoạn văn bản, gộp kết quả lại.

        Args:
            texts: Danh sách văn bản.

        Returns:
            ExtractionResult tổng hợp.
        """
        all_matches: List[PhoneMatch] = []
        for text in texts:
            result = self.extract(text)
            all_matches.extend(result.matches)
        return ExtractionResult(matches=all_matches)

    def has_phone(self, text: str) -> bool:
        """Kiểm tra nhanh xem text có chứa SĐT không."""
        if not text:
            return False
        return bool(self._pattern.search(text))

    # ── Private helpers ────────────────────────────────────────────────────

    def _extract_context(self, text: str, start: int, end: int) -> str:
        """Lấy đoạn văn bản xung quanh SĐT."""
        ctx_start = max(0, start - self.context_window)
        ctx_end = min(len(text), end + self.context_window)
        context = text[ctx_start:ctx_end].strip()

        # Thêm "..." nếu cắt bớt
        if ctx_start > 0:
            context = "..." + context
        if ctx_end < len(text):
            context = context + "..."

        return context
