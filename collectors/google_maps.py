"""
collectors/google_maps.py — Thu thập thông tin doanh nghiệp từ Google Maps.

Dùng Selenium để tự động tìm kiếm doanh nghiệp, scroll kết quả và
trích xuất thông tin liên lạc (SĐT, địa chỉ, website, v.v.).
"""

import logging
import random
import time
from dataclasses import dataclass, field
from typing import List, Optional, Callable

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    StaleElementReferenceException,
)

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
# Google Maps CSS Selectors
# Lưu ý: Google Maps thay đổi class thường xuyên — cần update nếu bị lỗi
# ---------------------------------------------------------------------------

class _Selectors:
    # Ô input tìm kiếm
    SEARCH_BOX = "input#searchboxinput"
    # Nút tìm kiếm
    SEARCH_BUTTON = "button#searchbox-searchbutton"
    # Danh sách kết quả (scrollable panel)
    RESULTS_PANEL = 'div[role="feed"]'
    # Từng card kết quả
    RESULT_CARD = 'a[href*="/maps/place/"]'
    # Trong detail panel:
    PLACE_NAME = 'h1.DUwDvf'
    PLACE_PHONE = 'button[data-item-id^="phone"]'
    PLACE_ADDRESS = 'button[data-item-id="address"]'
    PLACE_WEBSITE = 'a[data-item-id="authority"]'
    PLACE_RATING = 'div.F7nice span[aria-hidden="true"]'
    PLACE_REVIEWS = 'div.F7nice span[aria-label*="đánh giá"]'
    PLACE_CATEGORY = 'button.DkEaL'


# ---------------------------------------------------------------------------
# GoogleMapsCollector
# ---------------------------------------------------------------------------

class GoogleMapsCollector:
    """
    Thu thập thông tin doanh nghiệp từ Google Maps bằng Selenium.

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

    GOOGLE_MAPS_URL = "https://www.google.com/maps"

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
        self.headless = headless if headless is not None else settings.SELENIUM_HEADLESS
        self.progress_callback = progress_callback
        self._driver = None
        self._extractor = PhoneExtractor()
        self._normalizer = PhoneNormalizer()

    def __enter__(self):
        self._ensure_driver()
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
        query = f"{keyword} {area}".strip()
        logger.info("Bắt đầu tìm kiếm Google Maps: '%s' (limit=%d)", query, limit)

        result = CollectionResult(keyword=keyword, area=area)

        try:
            self._ensure_driver()
            self._navigate_and_search(query)
            place_urls = self._collect_place_urls(limit)
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
                        logger.debug("[%d/%d] %s — %s", i + 1, len(place_urls),
                                     biz.name, biz.phone_normalized or "không có SĐT")
                except Exception as e:
                    err_msg = f"Lỗi khi scrape {url}: {e}"
                    logger.warning(err_msg)
                    result.errors.append(err_msg)

                self._human_delay()

        except Exception as e:
            logger.error("Lỗi nghiêm trọng khi tìm kiếm Maps: %s", e, exc_info=True)
            result.errors.append(str(e))

        logger.info(
            "Hoàn thành Maps. Tổng: %d, Có SĐT: %d, Lỗi: %d",
            result.total_scraped, result.total_with_phone, len(result.errors),
        )
        return result

    def close(self):
        """Đóng WebDriver."""
        if self._driver:
            try:
                self._driver.quit()
            except Exception:
                pass
            self._driver = None
            logger.debug("Đã đóng WebDriver.")

    # ── Private — Driver management ─────────────────────────────────────────

    def _ensure_driver(self):
        """Khởi tạo WebDriver nếu chưa có."""
        if self._driver:
            return

        try:
            import undetected_chromedriver as uc
            options = uc.ChromeOptions()
            if self.headless:
                options.add_argument("--headless=new")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--lang=vi-VN")
            options.add_argument("--window-size=1366,768")
            self._driver = uc.Chrome(options=options)
            logger.info("Đã khởi động undetected-chromedriver.")
        except ImportError:
            logger.warning("undetected_chromedriver không có, dùng selenium thông thường.")
            self._driver = self._fallback_driver()

    def _fallback_driver(self):
        """Fallback: dùng selenium + webdriver-manager."""
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager
        from selenium.webdriver.chrome.options import Options

        options = Options()
        if self.headless:
            options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--lang=vi-VN")
        options.add_argument("--window-size=1366,768")
        service = Service(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=options)

    # ── Private — Navigation ────────────────────────────────────────────────

    def _navigate_and_search(self, query: str):
        """Mở Google Maps và thực hiện tìm kiếm."""
        if not self._driver:
            return
        self._driver.get(self.GOOGLE_MAPS_URL)
        self._wait_for(By.CSS_SELECTOR, _Selectors.SEARCH_BOX, timeout=15)

        search_box = self._driver.find_element(By.CSS_SELECTOR, _Selectors.SEARCH_BOX)
        search_box.clear()
        search_box.send_keys(query)

        self._human_delay(0.5, 1.0)
        search_btn = self._driver.find_element(By.CSS_SELECTOR, _Selectors.SEARCH_BUTTON)
        search_btn.click()

        # Đợi danh sách kết quả xuất hiện
        try:
            self._wait_for(By.CSS_SELECTOR, _Selectors.RESULTS_PANEL, timeout=15)
        except TimeoutException:
            logger.warning("Không thấy panel kết quả, thử tiếp tục...")

        self._human_delay(2.0, 3.0)

    def _collect_place_urls(self, limit: int) -> List[str]:
        """
        Scroll danh sách kết quả và thu thập URL của từng địa điểm.
        """
        urls: List[str] = []
        if not self._driver:
            return urls
        seen: set = set()
        max_scroll_attempts = 20
        scroll_attempts = 0

        try:
            panel = self._driver.find_element(By.CSS_SELECTOR, _Selectors.RESULTS_PANEL)
        except NoSuchElementException:
            logger.error("Không tìm thấy panel kết quả.")
            return urls

        while len(urls) < limit and scroll_attempts < max_scroll_attempts:
            # Lấy tất cả cards hiện tại
            cards = self._driver.find_elements(By.CSS_SELECTOR, _Selectors.RESULT_CARD)
            for card in cards:
                href = card.get_attribute("href") or ""
                if href and href not in seen and "/maps/place/" in href:
                    seen.add(href)
                    urls.append(href)
                    if len(urls) >= limit:
                        break

            if len(urls) >= limit:
                break

            # Scroll xuống để load thêm
            self._driver.execute_script(
                "arguments[0].scrollTop += arguments[0].clientHeight * 0.8;", panel
            )
            self._human_delay(1.5, 2.5)
            scroll_attempts += 1

            # Kiểm tra đã đến cuối chưa
            new_cards = self._driver.find_elements(By.CSS_SELECTOR, _Selectors.RESULT_CARD)
            if len(new_cards) <= len(cards):
                logger.info("Đã scroll đến cuối danh sách.")
                break

        logger.info("Thu thập được %d URL địa điểm.", len(urls))
        return urls[:limit]

    def _scrape_place_detail(self, url: str) -> Optional[BusinessInfo]:
        """Mở trang chi tiết và trích xuất thông tin."""
        if not self._driver:
            return None
        self._driver.get(url)
        self._wait_for(By.CSS_SELECTOR, _Selectors.PLACE_NAME, timeout=10)
        self._human_delay(1.0, 2.0)

        biz = BusinessInfo(maps_url=url)

        # Tên
        biz.name = self._safe_text(_Selectors.PLACE_NAME)

        # SĐT
        phone_raw = self._safe_phone()
        if phone_raw:
            biz.phone_raw = phone_raw
            norm = self._normalizer.normalize(phone_raw)
            biz.phone_normalized = norm.normalized or ""
            biz.carrier = norm.carrier or ""
            biz.is_valid_phone = norm.is_valid
        else:
            # Thử tìm SĐT trong toàn bộ text của trang
            page_text = self._driver.find_element(By.TAG_NAME, "body").text
            extraction = self._extractor.extract(page_text)
            if extraction.matches:
                biz.phone_raw = extraction.matches[0].raw
                norm = self._normalizer.normalize(biz.phone_raw)
                biz.phone_normalized = norm.normalized or ""
                biz.carrier = norm.carrier or ""
                biz.is_valid_phone = norm.is_valid

        # Địa chỉ
        biz.address = self._safe_text_by_attr("button[data-item-id='address'] .fontBodyMedium")
        if not biz.address:
            biz.address = self._safe_text(_Selectors.PLACE_ADDRESS)

        # Website
        try:
            website_el = self._driver.find_element(By.CSS_SELECTOR, _Selectors.PLACE_WEBSITE)
            biz.website = website_el.get_attribute("href") or ""
        except NoSuchElementException:
            pass

        # Rating
        biz.rating = self._safe_text(_Selectors.PLACE_RATING)

        # Category
        biz.category = self._safe_text(_Selectors.PLACE_CATEGORY)

        return biz if biz.name else None

    # ── Private — Helpers ───────────────────────────────────────────────────

    def _safe_text(self, css_selector: str) -> str:
        """Lấy text của element, trả về "" nếu không tìm thấy."""
        if not self._driver:
            return ""
        try:
            el = self._driver.find_element(By.CSS_SELECTOR, css_selector)
            return el.text.strip()
        except (NoSuchElementException, StaleElementReferenceException):
            return ""

    def _safe_text_by_attr(self, css_selector: str) -> str:
        """Lấy text từ selector, fallback về ""."""
        if not self._driver:
            return ""
        try:
            el = self._driver.find_element(By.CSS_SELECTOR, css_selector)
            return el.text.strip()
        except Exception:
            return ""

    def _safe_phone(self) -> str:
        """Lấy số điện thoại từ button phone element."""
        if not self._driver:
            return ""
        try:
            el = self._driver.find_element(By.CSS_SELECTOR, _Selectors.PLACE_PHONE)
            # aria-label thường chứa SĐT
            aria = el.get_attribute("aria-label") or ""
            text = el.text.strip()
            return text or aria
        except NoSuchElementException:
            return ""

    def _wait_for(self, by, selector: str, timeout: int = 10):
        """Đợi element xuất hiện."""
        if not self._driver:
            return
        WebDriverWait(self._driver, timeout).until(
            EC.presence_of_element_located((by, selector))
        )

    def _human_delay(
        self,
        min_sec: Optional[float] = None,
        max_sec: Optional[float] = None,
    ):
        """Nghỉ ngẫu nhiên để giả lập hành vi con người."""
        lo = min_sec if min_sec is not None else settings.SELENIUM_DELAY_MIN
        hi = max_sec if max_sec is not None else settings.SELENIUM_DELAY_MAX
        time.sleep(random.uniform(lo, hi))
