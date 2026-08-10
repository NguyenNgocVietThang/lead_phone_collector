"""
collectors/facebook.py — Thu thập SĐT từ Facebook public pages.

Hai chế độ:
  1. Graph API — dùng khi có Access Token (page do mình quản lý)
  2. Selenium public — duyệt không cần đăng nhập (public pages)

Tuân thủ:
  - Không bypass CAPTCHA, login, hay cơ chế bảo vệ.
  - Chỉ đọc nội dung hiển thị công khai.
  - Không thu thập profile cá nhân yêu cầu đăng nhập.
"""

import logging
import random
import time
from dataclasses import dataclass, field
from typing import List, Optional, Callable
from urllib.parse import urlparse
import requests

from processors.extractor import PhoneExtractor
from processors.normalizer import PhoneNormalizer
from config.settings import settings

logger = logging.getLogger(__name__)

# Source identifiers
SRC_GRAPH_POST = "fb_graph_post"
SRC_GRAPH_COMMENT = "fb_graph_comment"
SRC_SELENIUM_ABOUT = "fb_selenium_about"
SRC_SELENIUM_POST = "fb_selenium_post"
SRC_SELENIUM_COMMENT = "fb_selenium_comment"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class FbPhoneResult:
    """Một kết quả SĐT tìm được từ Facebook."""
    phone_raw: str
    phone_normalized: str
    carrier: str
    is_valid: bool
    source: str                  # Source identifier
    source_url: str = ""
    content: str = ""            # Đoạn text chứa SĐT
    page_name: str = ""


@dataclass
class FbCollectionResult:
    """Kết quả một phiên thu thập từ Facebook."""
    page_url: str
    page_name: str = ""
    results: List[FbPhoneResult] = field(default_factory=list)
    total_found: int = 0
    errors: List[str] = field(default_factory=list)

    def __post_init__(self):
        self.total_found = len(self.results)


# ---------------------------------------------------------------------------
# FacebookCollector
# ---------------------------------------------------------------------------

class FacebookCollector:
    """
    Thu thập SĐT từ Facebook page (public data only).

    Sử dụng:
        # Chế độ tự động (Graph API nếu có token, else Selenium)
        collector = FacebookCollector()
        result = collector.collect(
            page_url="https://www.facebook.com/tenpage",
            sources=["about", "posts", "comments"],
        )

    Context manager:
        with FacebookCollector() as collector:
            result = collector.collect(...)
    """

    def __init__(
        self,
        headless: Optional[bool] = None,
        progress_callback: Optional[Callable[[str], None]] = None,
    ):
        self.headless = headless if headless is not None else settings.SELENIUM_HEADLESS
        self.progress_callback = progress_callback
        self._driver = None
        self._extractor = PhoneExtractor()
        self._normalizer = PhoneNormalizer()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    # ── Public API ──────────────────────────────────────────────────────────

    def collect(
        self,
        page_url: str,
        sources: Optional[List[str]] = None,
        max_posts: int = 30,
    ) -> FbCollectionResult:
        """
        Thu thập SĐT từ một Facebook page.

        Args:
            page_url: URL hoặc username của page (VD: "https://facebook.com/page")
            sources: Danh sách nguồn cần thu thập: ["about", "posts", "comments"]
                     None = thu thập tất cả.
            max_posts: Số lượng posts tối đa cần duyệt.

        Returns:
            FbCollectionResult.
        """
        if sources is None:
            sources = ["about", "posts", "comments"]

        page_url = self._normalize_url(page_url)
        result = FbCollectionResult(page_url=page_url)

        logger.info("Bắt đầu thu thập Facebook: %s | Sources: %s", page_url, sources)

        # Chọn chế độ
        if settings.facebook_graph_enabled:
            logger.info("Dùng Graph API (có Access Token).")
            page_id = self._extract_page_id(page_url)
            graph_results = self._collect_graph_api(page_id, sources, max_posts)
            result.results.extend(graph_results)
        else:
            logger.info("Dùng Selenium public (không có Access Token).")
            selenium_results = self._collect_selenium(page_url, sources, max_posts, result)
            result.results.extend(selenium_results)

        result.total_found = len(result.results)
        logger.info("Hoàn thành Facebook: %d SĐT tìm được.", result.total_found)
        return result

    def close(self):
        """Đóng WebDriver nếu đang mở."""
        if self._driver:
            try:
                self._driver.quit()
            except Exception:
                pass
            self._driver = None

    # ── Graph API ───────────────────────────────────────────────────────────

    def _collect_graph_api(
        self,
        page_id: str,
        sources: List[str],
        max_posts: int,
    ) -> List[FbPhoneResult]:
        """Thu thập qua Facebook Graph API."""
        results: List[FbPhoneResult] = []
        token = settings.FACEBOOK_ACCESS_TOKEN
        base_url = "https://graph.facebook.com/v18.0"

        try:
            # Lấy thông tin page
            page_info = requests.get(
                f"{base_url}/{page_id}",
                params={"fields": "name,phone", "access_token": token},
                timeout=10,
            ).json()
            page_name = page_info.get("name", "")

            # SĐT khai báo trên page
            if page_phone := page_info.get("phone"):
                r = self._process_phone(
                    page_phone, SRC_GRAPH_POST,
                    f"https://facebook.com/{page_id}",
                    f"Thông tin trang: {page_phone}",
                    page_name,
                )
                if r:
                    results.append(r)

            # Posts
            if "posts" in sources or "comments" in sources:
                posts_data = requests.get(
                    f"{base_url}/{page_id}/posts",
                    params={
                        "fields": "id,message,permalink_url",
                        "limit": max_posts,
                        "access_token": token,
                    },
                    timeout=10,
                ).json()

                for post in posts_data.get("data", []):
                    post_url = post.get("permalink_url", "")
                    message = post.get("message", "")

                    if "posts" in sources and message:
                        for match in self._extractor.extract(message).matches:
                            r = self._process_phone(
                                match.raw, SRC_GRAPH_POST, post_url,
                                match.context, page_name,
                            )
                            if r:
                                results.append(r)

                    if "comments" in sources:
                        comments = self._fetch_graph_comments(
                            post["id"], token, base_url, page_name, post_url
                        )
                        results.extend(comments)

                    self._human_delay()

        except Exception as e:
            logger.error("Lỗi Graph API: %s", e, exc_info=True)

        return results

    def _fetch_graph_comments(
        self, post_id: str, token: str, base_url: str, page_name: str, post_url: str
    ) -> List[FbPhoneResult]:
        """Lấy comments của một post qua Graph API."""
        import requests
        results = []
        try:
            data = requests.get(
                f"{base_url}/{post_id}/comments",
                params={
                    "fields": "message",
                    "limit": 50,
                    "access_token": token,
                },
                timeout=10,
            ).json()
            for comment in data.get("data", []):
                msg = comment.get("message", "")
                for match in self._extractor.extract(msg).matches:
                    r = self._process_phone(
                        match.raw, SRC_GRAPH_COMMENT, post_url,
                        match.context, page_name,
                    )
                    if r:
                        results.append(r)
        except Exception as e:
            logger.warning("Lỗi fetch comments: %s", e)
        return results

    # ── Selenium Public ─────────────────────────────────────────────────────

    def _collect_selenium(
        self,
        page_url: str,
        sources: List[str],
        max_posts: int,
        result: FbCollectionResult,
    ) -> List[FbPhoneResult]:
        """
        Thu thập bằng Selenium không đăng nhập.
        Chỉ đọc nội dung public hiển thị khi chưa login.
        """
        results: List[FbPhoneResult] = []

        try:
            self._ensure_driver()

            # Lấy About section
            if "about" in sources:
                if self.progress_callback:
                    self.progress_callback("Đang đọc phần Giới thiệu...")
                about_results = self._scrape_about(page_url, result)
                results.extend(about_results)

            # Lấy Posts & Comments
            if "posts" in sources or "comments" in sources:
                if self.progress_callback:
                    self.progress_callback("Đang đọc posts...")
                post_results = self._scrape_posts(
                    page_url, sources, max_posts, result
                )
                results.extend(post_results)

        except Exception as e:
            err_msg = f"Lỗi Selenium Facebook: {e}"
            logger.error(err_msg, exc_info=True)
            result.errors.append(err_msg)

        return results

    def _scrape_about(self, page_url: str, result: FbCollectionResult) -> List[FbPhoneResult]:
        """Scrape phần About/Giới thiệu công khai của page."""
        results = []
        if not self._driver:
            return results
        about_url = page_url.rstrip("/") + "/about"

        try:
            self._driver.get(about_url)
            self._human_delay(3.0, 5.0)

            # Lấy toàn bộ text của trang
            body_text = self._driver.find_element(
                "tag name", "body"
            ).text

            # Lấy tên page (thử nhiều cách)
            page_name = self._get_page_name()
            result.page_name = page_name

            # Trích xuất SĐT
            extraction = self._extractor.extract(body_text)
            for match in extraction.matches:
                r = self._process_phone(
                    match.raw, SRC_SELENIUM_ABOUT, about_url,
                    match.context, page_name,
                )
                if r:
                    results.append(r)

            logger.debug("About section: tìm %d SĐT", len(results))

        except Exception as e:
            logger.warning("Lỗi scrape About: %s", e)
            result.errors.append(f"Lỗi About: {e}")

        return results

    def _scrape_posts(
        self,
        page_url: str,
        sources: List[str],
        max_posts: int,
        result: FbCollectionResult,
    ) -> List[FbPhoneResult]:
        """Scrape posts công khai của page."""
        results = []
        if not self._driver:
            return results

        try:
            self._driver.get(page_url)
            self._human_delay(3.0, 5.0)

            page_name = result.page_name or self._get_page_name()
            posts_processed = 0
            last_height = 0

            while posts_processed < max_posts:
                # Tìm tất cả posts hiện tại trên màn hình
                posts = self._driver.find_elements(
                    "css selector", '[data-pagelet^="FeedUnit"]'
                )

                if not posts:
                    # Fallback selector
                    posts = self._driver.find_elements(
                        "css selector", "div[role='article']"
                    )

                for post in posts[posts_processed:]:
                    if posts_processed >= max_posts:
                        break

                    try:
                        post_text = post.text
                        post_url = self._get_post_url(post) or page_url

                        # SĐT trong post content
                        if "posts" in sources:
                            extraction = self._extractor.extract(post_text)
                            for match in extraction.matches:
                                r = self._process_phone(
                                    match.raw, SRC_SELENIUM_POST, post_url,
                                    match.context, page_name,
                                )
                                if r:
                                    results.append(r)

                        # SĐT trong comments (chỉ comments đã hiển thị sẵn)
                        if "comments" in sources:
                            comment_els = post.find_elements(
                                "css selector", 'div[aria-label*="Bình luận"] span, '
                                               'ul li div[dir="auto"]'
                            )
                            for comment_el in comment_els[:20]:  # Tối đa 20 comment
                                comment_text = comment_el.text
                                if not comment_text:
                                    continue
                                extraction = self._extractor.extract(comment_text)
                                for match in extraction.matches:
                                    r = self._process_phone(
                                        match.raw, SRC_SELENIUM_COMMENT, post_url,
                                        match.context, page_name,
                                    )
                                    if r:
                                        results.append(r)

                        posts_processed += 1

                    except Exception as e:
                        logger.debug("Lỗi xử lý post: %s", e)
                        posts_processed += 1
                        continue

                # Scroll xuống để load thêm posts
                new_height = self._driver.execute_script(
                    "return document.body.scrollHeight"
                )
                if new_height == last_height:
                    logger.info("Đã scroll đến cuối trang Facebook.")
                    break
                last_height = new_height
                self._driver.execute_script(
                    "window.scrollTo(0, document.body.scrollHeight);"
                )
                self._human_delay(2.0, 4.0)

        except Exception as e:
            logger.warning("Lỗi scrape Posts: %s", e)
            result.errors.append(f"Lỗi Posts: {e}")

        return results

    # ── Private helpers ────────────────────────────────────────────────────

    def _ensure_driver(self):
        """Khởi tạo WebDriver."""
        if self._driver:
            return

        try:
            import undetected_chromedriver as uc
            options = uc.ChromeOptions()
            if self.headless:
                options.add_argument("--headless=new")
            options.add_argument("--no-sandbox")
            options.add_argument("--lang=vi-VN")
            options.add_argument("--window-size=1366,768")
            # Không đăng nhập — chạy profile trắng
            self._driver = uc.Chrome(options=options)
        except ImportError:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
            from webdriver_manager.chrome import ChromeDriverManager

            options = Options()
            if self.headless:
                options.add_argument("--headless=new")
            options.add_argument("--no-sandbox")
            options.add_argument("--lang=vi-VN")
            service = Service(ChromeDriverManager().install())
            self._driver = webdriver.Chrome(service=service, options=options)

    def _get_page_name(self) -> str:
        """Lấy tên page từ title hoặc h1."""
        if not self._driver:
            return ""
        try:
            # Thử lấy từ h1
            h1 = self._driver.find_element("css selector", "h1")
            return h1.text.strip()
        except Exception:
            pass
        try:
            title = self._driver.title
            return title.replace("| Facebook", "").strip()
        except Exception:
            return ""

    def _get_post_url(self, post_element) -> Optional[str]:
        """Lấy URL của post từ element."""
        if not self._driver:
            return None
        try:
            link = post_element.find_element(
                "css selector", 'a[href*="/posts/"], a[href*="story_fbid"]'
            )
            return link.get_attribute("href")
        except Exception:
            return None

    def _process_phone(
        self,
        raw: str,
        source: str,
        source_url: str,
        context: str,
        page_name: str,
    ) -> Optional[FbPhoneResult]:
        """Chuẩn hóa và kiểm tra SĐT, trả về FbPhoneResult hoặc None."""
        norm = self._normalizer.normalize(raw)
        if not norm.normalized:
            return None
        return FbPhoneResult(
            phone_raw=raw,
            phone_normalized=norm.normalized,
            carrier=norm.carrier or "",
            is_valid=norm.is_valid,
            source=source,
            source_url=source_url,
            content=context[:300],
            page_name=page_name,
        )

    def _human_delay(self, lo: Optional[float] = None, hi: Optional[float] = None):
        """Nghỉ ngẫu nhiên."""
        lo = lo if lo is not None else settings.SELENIUM_DELAY_MIN
        hi = hi if hi is not None else settings.SELENIUM_DELAY_MAX
        time.sleep(random.uniform(lo, hi))

    @staticmethod
    def _normalize_url(url: str) -> str:
        """Đảm bảo URL có scheme https://."""
        if not url.startswith("http"):
            url = "https://www.facebook.com/" + url.lstrip("/")
        return url

    @staticmethod
    def _extract_page_id(url: str) -> str:
        """Lấy page ID/username từ URL."""
        parsed = urlparse(url)
        path = parsed.path.strip("/")
        return path.split("/")[0] if path else url
