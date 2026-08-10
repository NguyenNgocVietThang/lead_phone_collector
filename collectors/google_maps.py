"""
collectors/google_maps.py — Thu thập thông tin doanh nghiệp từ Google Maps.

Dùng Playwright (stealth) để tự động tìm kiếm doanh nghiệp, scroll kết quả và
trích xuất thông tin liên lạc (SĐT, địa chỉ, website, v.v.).
"""

import logging
import random
import re
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import List, Optional, Callable, Any

from config.settings import settings
from processors.extractor import PhoneExtractor
from processors.normalizer import PhoneNormalizer

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class BusinessInfo:
    """Thông tin một doanh nghiệp từ Google Maps."""
    name: str = ""
    phone_raw: str = ""
    address: str = ""
    website: str = ""
    maps_url: str = ""
    rating: str = ""
    reviews_count: str = ""
    category: str = ""

    # Từ processors
    phone_normalized: str = ""
    carrier: str = ""
    is_valid_phone: bool = False
    source: str = "google_maps_details"


@dataclass
class CollectionResult:
    """Kết quả một phiên thu thập từ Google Maps."""
    keyword: str
    area: str
    businesses: List[BusinessInfo] = field(default_factory=list)
    total_scraped: int = 0
    total_with_phone: int = 0
    errors: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# GoogleMapsCollector — dùng Playwright
# ---------------------------------------------------------------------------

class GoogleMapsCollector:
    """
    Thu thập thông tin doanh nghiệp từ Google Maps bằng Playwright (stealth).

    Sử dụng:
        collector = GoogleMapsCollector()
        result = collector.search("nhà hàng", "Hà Nội", limit=50)
        for biz in result.businesses:
            print(biz.name, biz.phone_normalized)
        collector.close()

    Hoặc dùng context manager:
        with GoogleMapsCollector() as collector:
            result = collector.search("spa", "HCM")
    """

    def __init__(
        self,
        headless: Optional[bool] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ):
        """
        Args:
            headless: True để ẩn browser. None = đọc từ settings.
            progress_callback: Hàm callback(current, total) để báo tiến độ.
        """
        self.headless = headless if headless is not None else settings.PLAYWRIGHT_HEADLESS
        self.progress_callback = progress_callback
        self._extractor = PhoneExtractor()
        self._normalizer = PhoneNormalizer()

        # Playwright objects — khởi tạo lazy
        self._playwright: Optional[Any] = None
        self._browser: Optional[Any] = None
        self._page: Optional[Any] = None

    def __enter__(self):
        self._ensure_browser()
        return self

    def __exit__(self, *args):
        self.close()

    # ── Public API ──────────────────────────────────────────────────────────

    def search(
        self,
        keyword: str,
        area: str = "",
        limit: int = 50,
    ) -> CollectionResult:
        """
        Tìm kiếm doanh nghiệp và thu thập thông tin.

        Args:
            keyword: Từ khóa tìm kiếm (VD: "quán cà phê").
            area: Khu vực (VD: "Hà Nội"). Để trống nếu đã có trong keyword.
            limit: Số lượng kết quả tối đa cần thu thập.

        Returns:
            CollectionResult chứa danh sách BusinessInfo.
        """
        query = re.sub(r"\s+", " ", f"{keyword or ''} {area or ''}").strip()
        logger.info("Bắt đầu tìm kiếm Google Maps: '%s' (limit=%d)", query, limit)

        result = CollectionResult(keyword=keyword, area=area)

        try:
            self._ensure_browser()
            place_urls = self._navigate_and_collect_urls(query, limit)
            logger.info("Tìm thấy %d địa điểm, bắt đầu lấy chi tiết...", len(place_urls))

            for i, url in enumerate(place_urls):
                if self.progress_callback:
                    self.progress_callback(i + 1, len(place_urls))

                try:
                    biz = self._scrape_place_detail(url)
                    if biz:
                        result.businesses.append(biz)
                        result.total_scraped += 1
                        if biz.phone_normalized:
                            result.total_with_phone += 1
                        logger.info(
                            "[%d/%d] %s — SĐT: %s",
                            i + 1, len(place_urls),
                            biz.name, biz.phone_normalized or "không có",
                        )
                except Exception as e:
                    err_msg = f"Lỗi khi scrape {url}: {e}"
                    logger.warning(err_msg)
                    result.errors.append(err_msg)

                self._human_delay(0.5, 1.0)

        except Exception as e:
            logger.error("Lỗi nghiêm trọng khi tìm kiếm Maps: %s", e, exc_info=True)
            result.errors.append(str(e))

        logger.info(
            "Hoàn thành Maps. Tổng: %d, Có SĐT: %d, Lỗi: %d",
            result.total_scraped, result.total_with_phone, len(result.errors),
        )
        return result

    def close(self):
        """Đóng Playwright browser."""
        try:
            if self._page:
                self._page.close()
        except Exception:
            pass
        try:
            if self._browser:
                self._browser.close()
        except Exception:
            pass
        try:
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass
        self._page = None
        self._browser = None
        self._playwright = None
        logger.debug("Đã đóng Playwright browser.")

    # ── Private — Browser management ────────────────────────────────────────

    def _ensure_browser(self):
        """Khởi tạo Playwright browser nếu chưa có."""
        if self._browser and self._page:
            return

        from playwright.sync_api import sync_playwright

        logger.info("Đang khởi động Playwright Chromium (headless=%s)...", self.headless)
        self._playwright = sync_playwright().start()

        self._browser = self._playwright.chromium.launch(
            headless=self.headless,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--lang=vi-VN,vi",
            ],
        )

        if not self._browser:
            raise RuntimeError("Không thể khởi tạo Chromium browser.")

        context_kwargs = {
            "viewport": {"width": 1366, "height": 768},
            "locale": "vi-VN",
            "timezone_id": "Asia/Ho_Chi_Minh",
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
        }

        if settings.is_google_logged_in:
            logger.info("Đã tìm thấy session đăng nhập Google: %s", settings.GOOGLE_AUTH_PATH)
            context_kwargs["storage_state"] = str(settings.GOOGLE_AUTH_PATH)
        else:
            logger.info("Chạy Google Maps ở chế độ Ẩn danh (chưa đăng nhập).")

        context = self._browser.new_context(**context_kwargs)

        # Stealth: ẩn navigator.webdriver
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
            Object.defineProperty(navigator, 'languages', { get: () => ['vi-VN', 'vi', 'en-US'] });
            window.chrome = { runtime: {} };
        """)

        # Cố dùng playwright-stealth nếu có
        try:
            from playwright_stealth import stealth_sync  # type: ignore
            self._stealth_fn = stealth_sync
        except (ImportError, AttributeError):
            self._stealth_fn = None

        self._page = context.new_page()

        if self._stealth_fn:
            try:
                self._stealth_fn(self._page)
            except Exception:
                pass

        logger.info("Đã khởi động Playwright Chromium thành công.")

    # ── Private — Navigation & scraping ─────────────────────────────────────

    def _navigate_and_collect_urls(self, query: str, limit: int) -> List[str]:
        """Mở Google Maps, tìm kiếm và thu thập URL các địa điểm."""
        page = self._page
        if not page:
            return []

        encoded = urllib.parse.quote(query)
        search_url = f"https://www.google.com/maps/search/{encoded}?hl=vi"
        logger.info("Mở URL: %s", search_url)

        page.goto(search_url, wait_until="domcontentloaded", timeout=30000)

        # Đóng cookie consent nếu có
        self._dismiss_cookie_consent()

        # Chờ kết quả xuất hiện
        try:
            page.wait_for_selector(
                'div[role="feed"], a[href*="/maps/place/"]',
                timeout=15000,
            )
        except Exception:
            logger.warning("Không thấy feed kết quả sau 15s, thử tiếp tục...")

        self._human_delay(2.0, 3.0)

        # Trường hợp redirect thẳng về 1 địa điểm
        current_url = page.url or ""
        if "/maps/place/" in current_url:
            logger.info("Redirect về 1 địa điểm: %s", current_url)
            return [current_url]

        return self._scroll_and_collect_urls(limit)

    def _scroll_and_collect_urls(self, limit: int) -> List[str]:
        """Scroll feed kết quả và thu thập URLs."""
        page = self._page
        if not page:
            return []

        urls: List[str] = []
        seen: set = set()
        max_scroll = 30
        no_new_count = 0

        for attempt in range(max_scroll):
            # Lấy tất cả links địa điểm hiện tại
            links = page.query_selector_all('a[href*="/maps/place/"], div[role="article"] a, a.hfA8qe')
            prev_count = len(urls)

            for link in links:
                href = link.get_attribute("href") or ""
                if "/maps/place/" in href and href not in seen:
                    seen.add(href)
                    urls.append(href)
                    if len(urls) >= limit:
                        break

            if len(urls) >= limit:
                logger.info("Đã đủ %d URL.", limit)
                break

            # Scroll bằng mouse wheel hoặc Javascript trên container
            try:
                feed = page.query_selector('div[role="feed"], div.m6QEdf[aria-label*="Kết quả"], div.m6QEdf')
                if feed:
                    feed.evaluate("el => el.scrollTop += el.clientHeight * 1.5")
                else:
                    page.mouse.wheel(0, 1000)
            except Exception:
                page.mouse.wheel(0, 1000)

            self._human_delay(2.0, 3.0)

            new_count = len(urls) - prev_count
            if new_count == 0:
                no_new_count += 1
                if no_new_count >= 5:
                    logger.info("Không có kết quả mới sau 5 lần scroll, dừng.")
                    break
            else:
                no_new_count = 0

            # Kiểm tra cuối trang
            try:
                end_el = page.query_selector('span.HlvSq')  # "Bạn đã đến cuối danh sách"
                if end_el:
                    logger.info("Đã đến cuối danh sách kết quả.")
                    break
            except Exception:
                pass

        logger.info("Thu thập được %d URL địa điểm.", len(urls))
        return urls[:limit]

    def _scrape_place_detail(self, url: str) -> Optional[BusinessInfo]:
        """Mở trang chi tiết địa điểm và trích xuất thông tin."""
        page = self._page
        if not page:
            return None

        page.goto(url, wait_until="domcontentloaded", timeout=20000)

        # Chờ tên địa điểm
        try:
            page.wait_for_selector('h1', timeout=10000)
        except Exception:
            logger.warning("Không thấy h1 cho URL: %s", url)

        self._human_delay(1.0, 2.0)

        biz = BusinessInfo(maps_url=url)

        # Tên
        biz.name = self._get_text('h1.DUwDvf') or self._get_text('h1')

        # SĐT — thử nhiều selector
        biz.phone_raw = self._get_phone()

        if biz.phone_raw:
            biz.source = "google_maps_details"
            norm = self._normalizer.normalize(biz.phone_raw)
            biz.phone_normalized = norm.normalized or ""
            biz.carrier = norm.carrier or ""
            biz.is_valid_phone = norm.is_valid
        else:
            # Fallback: tìm SĐT trong phần Đánh giá/Bình luận hoặc toàn bộ text trang
            try:
                review_els = page.query_selector_all('div[data-review-id], div.My5W2, span.wiW1d, div.jJ794e')
                reviews_text = " ".join([(el.inner_text() or "").strip() for el in review_els if el.inner_text()])
                if reviews_text:
                    extraction = self._extractor.extract(reviews_text)
                    if extraction.matches:
                        biz.phone_raw = extraction.matches[0].raw
                        biz.source = "google_maps_comment"
                        norm = self._normalizer.normalize(biz.phone_raw)
                        biz.phone_normalized = norm.normalized or ""
                        biz.carrier = norm.carrier or ""
                        biz.is_valid_phone = norm.is_valid

                if not biz.phone_raw:
                    page_text = page.inner_text("body")
                    extraction = self._extractor.extract(page_text)
                    if extraction.matches:
                        biz.phone_raw = extraction.matches[0].raw
                        biz.source = "google_maps_comment"
                        norm = self._normalizer.normalize(biz.phone_raw)
                        biz.phone_normalized = norm.normalized or ""
                        biz.carrier = norm.carrier or ""
                        biz.is_valid_phone = norm.is_valid
            except Exception:
                pass

        # Địa chỉ
        biz.address = self._get_address()

        # Website
        try:
            el = page.query_selector('a[data-item-id="authority"], a[aria-label*="website"], a[aria-label*="Trang web"]')
            if el:
                biz.website = el.get_attribute("href") or ""
        except Exception:
            pass

        # Rating
        biz.rating = self._get_text('div.F7nice span[aria-hidden="true"]') or self._get_text('span.ceNzKf')

        # Category
        biz.category = self._get_text('button.DkEaL') or self._get_text('span.mgr77e')

        return biz if biz.name else None

    # ── Private — Helpers ───────────────────────────────────────────────────

    def _get_text(self, selector: str) -> str:
        """Lấy text của element, trả về '' nếu không tìm thấy."""
        page = self._page
        if not page:
            return ""
        try:
            el = page.query_selector(selector)
            if el:
                return (el.inner_text() or "").strip()
        except Exception:
            pass
        return ""

    def _get_phone(self) -> str:
        """Thử nhiều cách lấy SĐT từ trang chi tiết."""
        page = self._page
        if not page:
            return ""

        # 1. Button có data-item-id bắt đầu bằng "phone"
        try:
            els = page.query_selector_all('button[data-item-id^="phone"]')
            for el in els:
                aria = el.get_attribute("aria-label") or ""
                text = (el.inner_text() or "").strip()
                val = text or aria
                if val:
                    val = val.replace("Điện thoại: ", "").replace("Phone: ", "").strip()
                    if val:
                        return val
        except Exception:
            pass

        # 2. Aria-label chứa "Điện thoại" hoặc "Phone"
        try:
            for kw in ["Điện thoại", "Phone", "phone"]:
                el = page.query_selector(f'button[aria-label*="{kw}"]')
                if el:
                    aria = el.get_attribute("aria-label") or ""
                    if ":" in aria:
                        return aria.split(":", 1)[1].strip()
                    text = (el.inner_text() or "").strip()
                    if text:
                        return text
        except Exception:
            pass

        # 3. Tìm trong text của các span/div có pattern SĐT Việt Nam
        try:
            import re
            spans = page.query_selector_all('[data-item-id^="phone"] *')
            for span in spans:
                t = (span.inner_text() or "").strip()
                if re.match(r'^(0[3-9]\d{8}|\+84[3-9]\d{8}|\(0\d{1,2}\)\s?\d{6,8})$', t):
                    return t
        except Exception:
            pass

        return ""

    def _get_address(self) -> str:
        """Lấy địa chỉ từ trang chi tiết."""
        page = self._page
        if not page:
            return ""

        try:
            el = page.query_selector("button[data-item-id='address']")
            if el:
                child = el.query_selector(".fontBodyMedium")
                if child:
                    return (child.inner_text() or "").strip()
                return (el.inner_text() or "").strip()
        except Exception:
            pass

        try:
            for kw in ["Địa chỉ", "Address"]:
                el = page.query_selector(f'button[aria-label*="{kw}"]')
                if el:
                    aria = el.get_attribute("aria-label") or ""
                    if ":" in aria:
                        return aria.split(":", 1)[1].strip()
                    return (el.inner_text() or "").strip()
        except Exception:
            pass

        return ""

    def _dismiss_cookie_consent(self):
        """Đóng popup cookie consent của Google nếu xuất hiện."""
        page = self._page
        if not page:
            return
        try:
            for selector in [
                'button[aria-label*="Chấp nhận"]',
                'button[aria-label*="Accept"]',
                'button[id="L2AGLb"]',
                'form[action*="consent"] button',
            ]:
                btn = page.query_selector(selector)
                if btn:
                    btn.click()
                    logger.debug("Đã đóng cookie consent.")
                    self._human_delay(0.5, 1.0)
                    return
        except Exception:
            pass

    def _human_delay(
        self,
        min_sec: Optional[float] = None,
        max_sec: Optional[float] = None,
    ):
        """Nghỉ ngẫu nhiên để giả lập hành vi con người."""
        lo = min_sec if min_sec is not None else settings.PLAYWRIGHT_DELAY_MIN
        hi = max_sec if max_sec is not None else settings.PLAYWRIGHT_DELAY_MAX
        time.sleep(random.uniform(lo, hi))
