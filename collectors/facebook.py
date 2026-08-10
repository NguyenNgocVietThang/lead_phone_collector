"""
collectors/facebook.py — Thu thập SĐT từ Facebook public pages.

Hai chế độ:
  1. Graph API — dùng khi có Access Token (page do mình quản lý)
  2. Playwright public — duyệt bằng Playwright không cần đăng nhập (public pages)

Tuân thủ:
  - Không bypass CAPTCHA, login, hay cơ chế bảo vệ.
  - Chỉ đọc nội dung hiển thị công khai.
  - Không thu thập profile cá nhân yêu cầu đăng nhập.
"""

import logging
import random
import time
from dataclasses import dataclass, field
from typing import List, Optional, Callable, Any
from urllib.parse import urlparse
import requests

from processors.extractor import PhoneExtractor
from processors.normalizer import PhoneNormalizer
from config.settings import settings

logger = logging.getLogger(__name__)

# Source identifiers
SRC_GRAPH_POST = "fb_graph_post"
SRC_GRAPH_COMMENT = "fb_graph_comment"
SRC_PLAYWRIGHT_ABOUT = "fb_playwright_about"
SRC_PLAYWRIGHT_POST = "fb_playwright_post"
SRC_PLAYWRIGHT_COMMENT = "fb_playwright_comment"
SRC_PLAYWRIGHT_LIKER = "fb_playwright_liker"
SRC_GROUP_POST = "fb_group_post"
SRC_GROUP_COMMENT = "fb_group_comment"
SRC_GROUP_LIKER = "fb_group_liker"
SRC_SEARCH_POST = "fb_search_post"
SRC_SEARCH_COMMENT = "fb_search_comment"
SRC_SEARCH_LIKER = "fb_search_liker"
SRC_PROFILE_BIO = "fb_profile_bio"
SRC_PROFILE_POST = "fb_profile_post"
SRC_PROFILE_COMMENT = "fb_profile_comment"
SRC_PROFILE_LIKER = "fb_profile_liker"

# Backward compatibility aliases
SRC_SELENIUM_ABOUT = SRC_PLAYWRIGHT_ABOUT
SRC_SELENIUM_POST = SRC_PLAYWRIGHT_POST
SRC_SELENIUM_COMMENT = SRC_PLAYWRIGHT_COMMENT


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
# FacebookCollector — dùng Playwright
# ---------------------------------------------------------------------------

class FacebookCollector:
    """
    Thu thập SĐT từ Facebook page (public data only).

    Sử dụng:
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
        self.headless = headless if headless is not None else settings.PLAYWRIGHT_HEADLESS
        self.progress_callback = progress_callback
        self._playwright: Optional[Any] = None
        self._browser: Optional[Any] = None
        self._page: Optional[Any] = None
        self._extractor = PhoneExtractor()
        self._normalizer = PhoneNormalizer()

    def __enter__(self):
        self._ensure_browser()
        return self

    def __exit__(self, *args):
        self.close()

    # ── Public API ──────────────────────────────────────────────────────────

    def collect(
        self,
        target: str,
        target_type: str = "auto",
        sources: Optional[List[str]] = None,
        max_posts: int = 30,
    ) -> FbCollectionResult:
        """
        Thu thập SĐT từ Facebook Page, Profile cá nhân, Group, hoặc Từ khóa tìm kiếm.

        Args:
            target: URL Facebook Page/Profile/Group hoặc Từ khóa cần tìm kiếm.
            target_type: Loại mục tiêu: "page", "profile", "group", "search", hoặc "auto".
            sources: Danh sách nguồn cần thu thập: ["about", "posts", "comments", "likers"]
                     None = thu thập tất cả.
            max_posts: Số lượng posts tối đa cần duyệt.

        Returns:
            FbCollectionResult.
        """
        if sources is None:
            sources = ["about", "posts", "comments", "likers"]

        target = target.strip()

        # Tự động xác định target_type nếu là "auto"
        if target_type == "auto":
            if "/groups/" in target:
                target_type = "group"
            elif "/profile.php" in target or "/p/" in target or "facebook.com/people/" in target:
                target_type = "profile"
            elif target.startswith("http://") or target.startswith("https://") or "facebook.com" in target:
                target_type = "page"
            else:
                target_type = "search"

        if target_type in ["page", "profile", "group"]:
            target_url = self._normalize_url(target)
        else:
            target_url = target  # Keyword

        result = FbCollectionResult(page_url=target_url)

        logger.info("Bắt đầu thu thập Facebook [%s]: %s | Sources: %s", target_type, target_url, sources)

        # Chọn chế độ: Graph API (chỉ dùng cho Page) hoặc Playwright
        if target_type == "page" and settings.facebook_graph_enabled:
            logger.info("Dùng Graph API (có Access Token).")
            page_id = self._extract_page_id(target_url)
            graph_results = self._collect_graph_api(page_id, sources, max_posts)
            result.results.extend(graph_results)
        else:
            logger.info("Dùng Playwright (target_type=%s, logged_in=%s).", target_type, settings.is_fb_logged_in)
            playwright_results = self._collect_playwright_target(target_url, target_type, sources, max_posts, result)
            result.results.extend(playwright_results)

        result.total_found = len(result.results)
        logger.info("Hoàn thành Facebook [%s]: %d SĐT tìm được.", target_type, result.total_found)
        return result

    def close(self):
        """Đóng Playwright browser nếu đang mở."""
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
        logger.debug("Đã đóng Playwright browser Facebook.")

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
            page_info = requests.get(
                f"{base_url}/{page_id}",
                params={"fields": "name,phone", "access_token": token},
                timeout=10,
            ).json()
            page_name = page_info.get("name", "")

            if page_phone := page_info.get("phone"):
                r = self._process_phone(
                    page_phone, SRC_GRAPH_POST,
                    f"https://facebook.com/{page_id}",
                    f"Thông tin trang: {page_phone}",
                    page_name,
                )
                if r:
                    results.append(r)

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

    # ── Playwright Scraping (Page, Group, Search) ───────────────────────────

    def _collect_playwright_target(
        self,
        target: str,
        target_type: str,
        sources: List[str],
        max_posts: int,
        result: FbCollectionResult,
    ) -> List[FbPhoneResult]:
        """
        Thu thập bằng Playwright (hỗ trợ Page, Profile cá nhân, Group, và Keyword Search).
        """
        results: List[FbPhoneResult] = []

        try:
            self._ensure_browser()

            if target_type == "profile":
                if "about" in sources or "bio" in sources:
                    if self.progress_callback:
                        self.progress_callback("Đang đọc Bio & Giới thiệu Profile cá nhân...")
                    about_results = self._scrape_about(target, result, is_profile=True)
                    results.extend(about_results)

                if any(s in sources for s in ["posts", "comments", "likers"]):
                    if self.progress_callback:
                        self.progress_callback("Đang đọc bài viết & tương tác Profile cá nhân...")
                    post_results = self._scrape_feed_units(
                        target, sources, max_posts, result,
                        src_post=SRC_PROFILE_POST, src_comment=SRC_PROFILE_COMMENT, src_liker=SRC_PROFILE_LIKER
                    )
                    results.extend(post_results)

            elif target_type == "page":
                if "about" in sources:
                    if self.progress_callback:
                        self.progress_callback("Đang đọc phần Giới thiệu Page...")
                    about_results = self._scrape_about(target, result, is_profile=False)
                    results.extend(about_results)

                if any(s in sources for s in ["posts", "comments", "likers"]):
                    if self.progress_callback:
                        self.progress_callback("Đang đọc bài viết Page...")
                    post_results = self._scrape_feed_units(
                        target, sources, max_posts, result,
                        src_post=SRC_PLAYWRIGHT_POST, src_comment=SRC_PLAYWRIGHT_COMMENT, src_liker=SRC_PLAYWRIGHT_LIKER
                    )
                    results.extend(post_results)

            elif target_type == "group":
                if self.progress_callback:
                    self.progress_callback("Đang đọc bài viết trong Hội Nhóm...")
                group_results = self._scrape_feed_units(
                    target, sources, max_posts, result,
                    src_post=SRC_GROUP_POST, src_comment=SRC_GROUP_COMMENT, src_liker=SRC_GROUP_LIKER
                )
                results.extend(group_results)

            elif target_type == "search":
                import urllib.parse
                search_url = f"https://www.facebook.com/search/posts/?q={urllib.parse.quote(target)}"
                if self.progress_callback:
                    self.progress_callback(f"Đang tìm kiếm bài viết với từ khóa '{target}'...")
                search_results = self._scrape_feed_units(
                    search_url, sources, max_posts, result,
                    src_post=SRC_SEARCH_POST, src_comment=SRC_SEARCH_COMMENT, src_liker=SRC_SEARCH_LIKER
                )
                results.extend(search_results)

        except Exception as e:
            err_msg = f"Lỗi Playwright Facebook ({target_type}): {e}"
            logger.error(err_msg, exc_info=True)
            result.errors.append(err_msg)

        return results

    # Alias cho backward compatibility
    _collect_playwright = lambda self, page_url, sources, max_posts, result: self._collect_playwright_target(page_url, "page", sources, max_posts, result)
    _collect_selenium = _collect_playwright

    def _scrape_about(self, target_url: str, result: FbCollectionResult, is_profile: bool = False) -> List[FbPhoneResult]:
        """Scrape phần About/Giới thiệu và Bio phần đầu trang của page hoặc profile cá nhân."""
        results = []
        if not self._page:
            return results

        source_tag = SRC_PROFILE_BIO if is_profile else SRC_PLAYWRIGHT_ABOUT

        # 1. Thu thập từ trang chủ của Profile/Page (Bio header box)
        try:
            self._page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
            self._human_delay(3.0, 5.0)
            self._dismiss_popups()

            header_text = self._page.inner_text("body")
            page_name = self._get_page_name()
            if not result.page_name:
                result.page_name = page_name

            extraction = self._extractor.extract(header_text)
            for match in extraction.matches:
                r = self._process_phone(
                    match.raw, source_tag, target_url,
                    match.context, page_name,
                )
                if r:
                    results.append(r)
        except Exception as e:
            logger.warning("Lỗi scrape trang chủ Bio/Header: %s", e)

        # 2. Thu thập từ trang /about
        about_url = target_url.rstrip("/") + "/about"
        try:
            self._page.goto(about_url, wait_until="domcontentloaded", timeout=30000)
            self._human_delay(3.0, 5.0)
            self._dismiss_popups()

            body_text = self._page.inner_text("body")
            page_name = result.page_name or self._get_page_name()

            extraction = self._extractor.extract(body_text)
            for match in extraction.matches:
                r = self._process_phone(
                    match.raw, source_tag, about_url,
                    match.context, page_name,
                )
                if r:
                    results.append(r)

            logger.debug("About/Bio section: tìm %d SĐT", len(results))

        except Exception as e:
            logger.warning("Lỗi scrape About: %s", e)
            result.errors.append(f"Lỗi About: {e}")

        return results

    def _scrape_feed_units(
        self,
        url: str,
        sources: List[str],
        max_posts: int,
        result: FbCollectionResult,
        src_post: str = SRC_PLAYWRIGHT_POST,
        src_comment: str = SRC_PLAYWRIGHT_COMMENT,
        src_liker: str = SRC_PLAYWRIGHT_LIKER,
    ) -> List[FbPhoneResult]:
        """Scrape bài viết, bình luận & lượt thích từ Page, Profile, Group hoặc Kết quả Tìm kiếm."""
        results = []
        if not self._page:
            return results

        try:
            self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
            self._human_delay(3.0, 5.0)
            self._dismiss_popups()

            page_name = result.page_name or self._get_page_name()
            if not result.page_name:
                result.page_name = page_name

            posts_processed = 0
            last_height = 0
            empty_scroll_count = 0

            while posts_processed < max_posts:
                posts = self._page.query_selector_all('[data-pagelet^="FeedUnit"]')
                if not posts:
                    posts = self._page.query_selector_all("div[role='article']")
                if not posts:
                    posts = self._page.query_selector_all("div[role='feed'] > div")

                for post in posts[posts_processed:]:
                    if posts_processed >= max_posts:
                        break

                    try:
                        # Mở rộng văn bản bị rút gọn "Xem thêm"
                        try:
                            see_more = post.query_selector('div[role="button"]:has-text("Xem thêm"), div[role="button"]:has-text("See more")')
                            if see_more and see_more.is_visible():
                                see_more.click()
                                self._human_delay(0.3, 0.7)
                        except Exception:
                            pass

                        post_text = post.inner_text() or ""
                        if not post_text.strip():
                            posts_processed += 1
                            continue

                        post_url = self._get_post_url(post) or url

                        if "posts" in sources:
                            extraction = self._extractor.extract(post_text)
                            for match in extraction.matches:
                                r = self._process_phone(
                                    match.raw, src_post, post_url,
                                    match.context, page_name,
                                )
                                if r:
                                    results.append(r)

                        if "comments" in sources:
                            # Mở rộng bình luận "Xem thêm bình luận" nếu có
                            try:
                                more_comments = post.query_selector('div[role="button"]:has-text("Xem thêm bình luận"), div[role="button"]:has-text("Xem tất cả bình luận")')
                                if more_comments and more_comments.is_visible():
                                    more_comments.click()
                                    self._human_delay(0.5, 1.0)
                            except Exception:
                                pass

                            comment_els = post.query_selector_all(
                                'div[aria-label*="Bình luận"] span, ul li div[dir="auto"], div[role="article"] span'
                            )
                            for comment_el in comment_els[:20]:
                                comment_text = comment_el.inner_text() or ""
                                if not comment_text.strip():
                                    continue
                                extraction = self._extractor.extract(comment_text)
                                for match in extraction.matches:
                                    r = self._process_phone(
                                        match.raw, src_comment, post_url,
                                        match.context, page_name,
                                    )
                                    if r:
                                        results.append(r)

                        if "likers" in sources:
                            try:
                                reaction_btn = post.query_selector('[aria-label*="cảm xúc"], [aria-label*="reactions"], a[href*="reaction/profile"], [role="button"]:has-text("thích"), span:has-text("người khác")')
                                if reaction_btn and reaction_btn.is_visible():
                                    reaction_btn.click()
                                    self._human_delay(1.0, 2.0)
                                    dialog = self._page.query_selector('div[role="dialog"]')
                                    if dialog:
                                        dialog_text = dialog.inner_text() or ""
                                        extraction = self._extractor.extract(dialog_text)
                                        for match in extraction.matches:
                                            r = self._process_phone(
                                                match.raw, src_liker, post_url,
                                                match.context, page_name,
                                            )
                                            if r:
                                                results.append(r)
                                    self._dismiss_popups()
                            except Exception as e_likers:
                                logger.debug("Lỗi đọc danh sách lượt thích: %s", e_likers)

                        posts_processed += 1

                    except Exception as e:
                        logger.debug("Lỗi xử lý element bài viết: %s", e)
                        posts_processed += 1
                        continue

                new_height = self._page.evaluate("document.body.scrollHeight")
                if new_height == last_height:
                    empty_scroll_count += 1
                    if empty_scroll_count >= 3:
                        logger.info("Đã scroll hết kết quả Facebook.")
                        break
                else:
                    empty_scroll_count = 0

                last_height = new_height
                self._page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                self._human_delay(2.0, 4.0)
                self._dismiss_popups()

        except Exception as e:
            logger.warning("Lỗi scrape feed units: %s", e)
            result.errors.append(f"Lỗi Feed Units: {e}")

        return results

    # Alias cũ
    _scrape_posts = _scrape_feed_units

    def _dismiss_popups(self):
        """Đóng các dialog popup đăng nhập/thông báo của Facebook nếu có."""
        if not self._page:
            return
        try:
            close_btns = self._page.query_selector_all('[aria-label="Đóng"], [aria-label="Close"], div[role="dialog"] i')
            for btn in close_btns[:2]:
                if btn.is_visible():
                    btn.click()
                    self._human_delay(0.5, 1.0)
        except Exception:
            pass

    # ── Private helpers ────────────────────────────────────────────────────

    def _ensure_browser(self):
        """Khởi tạo Playwright browser (tự nạp session đăng nhập nếu có)."""
        if self._browser and self._page:
            return

        from playwright.sync_api import sync_playwright

        logger.info("Đang khởi động Playwright Chromium cho Facebook (headless=%s)...", self.headless)
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

        if settings.is_fb_logged_in:
            logger.info("Đã tìm thấy session đăng nhập Facebook: %s", settings.FB_AUTH_PATH)
            context_kwargs["storage_state"] = str(settings.FB_AUTH_PATH)
        else:
            logger.info("Chạy Facebook ở chế độ Ẩn danh (chưa đăng nhập).")

        context = self._browser.new_context(**context_kwargs)

        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
            Object.defineProperty(navigator, 'languages', { get: () => ['vi-VN', 'vi', 'en-US'] });
            window.chrome = { runtime: {} };
        """)

        self._page = context.new_page()
        logger.info("Đã khởi động Playwright Chromium cho Facebook thành công.")

    def _get_page_name(self) -> str:
        """Lấy tên page từ title hoặc h1."""
        if not self._page:
            return ""
        try:
            h1 = self._page.query_selector("h1")
            if h1:
                text = (h1.inner_text() or "").strip()
                if text:
                    return text
        except Exception:
            pass
        try:
            title = self._page.title()
            return title.replace("| Facebook", "").strip()
        except Exception:
            return ""

    def _get_post_url(self, post_element) -> Optional[str]:
        """Lấy URL của post từ element."""
        if not self._page:
            return None
        try:
            link = post_element.query_selector('a[href*="/posts/"], a[href*="story_fbid"]')
            if link:
                return link.get_attribute("href")
        except Exception:
            pass
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
        lo = lo if lo is not None else settings.PLAYWRIGHT_DELAY_MIN
        hi = hi if hi is not None else settings.PLAYWRIGHT_DELAY_MAX
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
