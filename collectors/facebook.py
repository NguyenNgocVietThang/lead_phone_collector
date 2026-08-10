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

import hashlib
import logging
import random
import time
from dataclasses import dataclass, field
from typing import List, Optional, Callable, Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
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

ALLOWED_SOURCES = {"about", "bio", "posts", "comments", "likers"}
DEFAULT_SOURCES = ["about", "posts", "comments", "likers"]
FEED_SELECTORS = (
    '[data-pagelet^="FeedUnit"]',
    'div[data-pagelet="GroupFeed"] > div',
    'div[role="feed"] > div',
)

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
            sources = DEFAULT_SOURCES.copy()
        else:
            # Giữ đúng thứ tự người dùng chọn, bỏ giá trị lạ và giá trị trùng.
            sources = list(dict.fromkeys(s for s in sources if s in ALLOWED_SOURCES))
        max_posts = max(1, min(int(max_posts), 200))

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
            # Token hết hạn/quyền thiếu thường chỉ trả JSON lỗi và danh sách rỗng.
            # Tự chuyển sang trình duyệt để một cấu hình Graph lỗi không làm mất cả job.
            if not graph_results:
                logger.warning("Graph API không trả dữ liệu, chuyển sang Playwright.")
                if self.progress_callback:
                    self.progress_callback("Graph API không có dữ liệu, đang chuyển sang quét trình duyệt...")
                result.results.extend(
                    self._collect_playwright_target(target_url, target_type, sources, max_posts, result)
                )
        else:
            logger.info("Dùng Playwright (target_type=%s, logged_in=%s).", target_type, settings.is_fb_logged_in)
            playwright_results = self._collect_playwright_target(target_url, target_type, sources, max_posts, result)
            result.results.extend(playwright_results)

        # Loại bỏ các SĐT bị trùng lặp trong cùng phiên thu thập
        seen_keys = set()
        unique_results = []
        for r in result.results:
            key = (r.phone_normalized, r.source_url)
            if key not in seen_keys:
                seen_keys.add(key)
                unique_results.append(r)

        result.results = unique_results
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
        about_url = self._build_about_url(target_url)
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

    @staticmethod
    def _build_about_url(target_url: str) -> str:
        """Tạo URL About đúng cho cả username URL và ``profile.php?id=...``."""
        parsed = urlparse(target_url)
        if parsed.path.rstrip("/").endswith("/profile.php"):
            query = dict(parse_qsl(parsed.query, keep_blank_values=True))
            query["sk"] = "about"
            return urlunparse(parsed._replace(query=urlencode(query), fragment=""))

        about_path = parsed.path.rstrip("/") + "/about"
        return urlunparse(parsed._replace(path=about_path, query="", fragment=""))

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
        results: List[FbPhoneResult] = []
        if not self._page:
            return results

        try:
            self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
            try:
                self._page.wait_for_selector(
                    ', '.join(FEED_SELECTORS) + ', div[role="article"]',
                    timeout=8000,
                )
            except Exception:
                logger.debug("Facebook chưa render feed selector sau 8 giây; dùng fallback body.")
            self._human_delay(1.0, 2.0)
            self._dismiss_popups()

            page_name = result.page_name or self._get_page_name()
            if not result.page_name:
                result.page_name = page_name

            posts_processed = 0
            seen_posts = set()
            idle_scrolls = 0
            body_fallback_scanned = False
            max_scrolls = max(8, min(max_posts * 2, 80))

            for _ in range(max_scrolls):
                posts = self._find_feed_units()
                new_this_scroll = 0

                # Facebook ảo hóa DOM khi cuộn, vì vậy không thể cắt mảng bằng
                # posts_processed. Dùng fingerprint để không bỏ sót node mới.
                for post in posts:
                    if posts_processed >= max_posts:
                        break

                    try:
                        initial_text = (post.inner_text() or "").strip()
                        specific_post_url = self._get_post_url(post)
                        fingerprint = self._post_fingerprint(specific_post_url, initial_text)
                        if not fingerprint or fingerprint in seen_posts:
                            continue
                        seen_posts.add(fingerprint)

                        # 1. Mở rộng tất cả văn bản bị rút gọn "Xem thêm" / "See more"
                        try:
                            see_mores = post.query_selector_all(
                                'div[role="button"]:has-text("Xem thêm"), div[role="button"]:has-text("See more"), '
                                'span:has-text("Xem thêm"), span:has-text("See more")'
                            )
                            for sm in see_mores[:3]:
                                if sm.is_visible():
                                    sm.click()
                                    self._human_delay(0.2, 0.4)
                        except Exception:
                            pass

                        post_url = specific_post_url or url

                        # 2. Mở rộng các nhánh bình luận có thể nhìn thấy.
                        if "comments" in sources:
                            self._expand_comment_threads(post)

                            # Một số nút mở bài viết trong dialog thay vì bung inline.
                            dialog = self._page.query_selector('div[role="dialog"]')
                            if dialog:
                                try:
                                    dialog_text = dialog.inner_text() or ""
                                    self._append_phone_matches(
                                        results, dialog_text, src_comment, post_url, page_name
                                    )
                                except Exception as e_dlg:
                                    logger.debug("Lỗi đọc dialog bình luận: %s", e_dlg)
                                finally:
                                    try:
                                        self._page.keyboard.press("Escape")
                                    except Exception:
                                        pass

                        post_text = post.inner_text() or ""
                        if not post_text.strip():
                            posts_processed += 1
                            new_this_scroll += 1
                            continue

                        # Chỉ extract toàn khối một lần. Khi chỉ chọn Comments, khối
                        # được gắn nguồn comment; các comment cụ thể vẫn được quét dưới đây.
                        if "posts" in sources:
                            self._append_phone_matches(
                                results, post_text, src_post, post_url, page_name
                            )
                        elif "comments" in sources:
                            self._append_phone_matches(
                                results, post_text, src_comment, post_url, page_name
                            )

                        if "comments" in sources:
                            # Quét chi tiết từng thẻ comment cụ thể
                            comment_els = post.query_selector_all(
                                'div[role="article"], div[aria-label*="Bình luận"], div[aria-label*="Comment"], '
                                'div[aria-label*="bình luận"], div[aria-label*="comment"], ul li'
                            )
                            for comment_el in comment_els[:100]:
                                try:
                                    c_text = comment_el.inner_text() or ""
                                    if not c_text.strip():
                                        continue
                                    self._append_phone_matches(
                                        results, c_text, src_comment, post_url, page_name
                                    )
                                except Exception:
                                    pass

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
                        new_this_scroll += 1
                        if self.progress_callback:
                            self.progress_callback(
                                f"Đã quét {posts_processed}/{max_posts} bài viết, tìm thấy {len(results)} kết quả..."
                            )

                    except Exception as e:
                        logger.debug("Lỗi xử lý element bài viết: %s", e)
                        posts_processed += 1
                        new_this_scroll += 1
                        continue

                # Profile/page có giao diện mới đôi khi không còn role=feed/article.
                # Quét body một lần làm fallback để vẫn bắt nội dung đang hiển thị.
                if not posts and not body_fallback_scanned:
                    body_fallback_scanned = True
                    body_text = self._page.inner_text("body") or ""
                    fallback_source = src_post if "posts" in sources else src_comment
                    if "posts" in sources or "comments" in sources:
                        self._append_phone_matches(
                            results, body_text, fallback_source, url, page_name
                        )

                if posts_processed >= max_posts:
                    break

                idle_scrolls = idle_scrolls + 1 if new_this_scroll == 0 else 0
                if idle_scrolls >= 4:
                    logger.info("Không có bài viết mới sau 4 lần cuộn, dừng quét Facebook.")
                    break

                # Đưa node cuối vào viewport rồi cuộn thêm để kích hoạt lazy-load.
                try:
                    if posts:
                        posts[-1].scroll_into_view_if_needed(timeout=3000)
                    self._page.mouse.wheel(0, 1200)
                except Exception:
                    self._page.evaluate("window.scrollBy(0, 1200)")
                self._human_delay(0.8, 1.5)
                self._dismiss_popups()

        except Exception as e:
            logger.warning("Lỗi scrape feed units: %s", e)
            result.errors.append(f"Lỗi Feed Units: {e}")

        return results

    def _find_feed_units(self) -> List[Any]:
        """Tìm các bài viết top-level trên nhiều biến thể DOM Facebook."""
        if not self._page:
            return []

        for selector in FEED_SELECTORS:
            posts = self._page.query_selector_all(selector)
            if posts:
                return posts

        articles = self._page.query_selector_all('div[role="article"]')
        top_level = []
        for article in articles:
            try:
                is_nested = article.evaluate(
                    'el => !!el.parentElement.closest(\'div[role="article"]\')'
                )
                if not is_nested:
                    top_level.append(article)
            except Exception:
                top_level.append(article)
        if top_level:
            return top_level
        return self._page.query_selector_all("div.userContentWrapper, div[aria-describedby]")

    @staticmethod
    def _post_fingerprint(post_url: Optional[str], text: str) -> str:
        """Khóa ổn định để nhận biết bài đã xử lý trong DOM bị ảo hóa."""
        if post_url:
            return f"url:{_normalize_fb_url(post_url)}"
        compact = " ".join((text or "").split())
        if not compact:
            return ""
        sample = compact[:1000] + compact[-300:]
        return "text:" + hashlib.sha1(sample.encode("utf-8")).hexdigest()

    def _append_phone_matches(
        self,
        destination: List[FbPhoneResult],
        text: str,
        source: str,
        source_url: str,
        page_name: str,
    ) -> None:
        """Extract và thêm các SĐT hợp lệ từ một khối text."""
        for match in self._extractor.extract(text or "").matches:
            phone = self._process_phone(
                match.raw, source, source_url, match.context, page_name
            )
            if phone:
                destination.append(phone)

    def _expand_comment_threads(self, post: Any, max_clicks: int = 5) -> None:
        """Mở comment/reply theo selector hẹp để tránh duyệt hàng trăm span mỗi bài."""
        expand_terms = (
            "xem thêm bình luận", "xem tất cả bình luận", "xem các bình luận",
            "xem bình luận trước", "view more comments", "view all comments",
            "view previous comments", "phản hồi", "replies",
        )
        excluded_terms = (
            "viết bình luận", "write a comment", "thích", "like",
            "chia sẻ", "share", "gửi", "send",
        )

        for _ in range(max_clicks):
            clicked = False
            buttons = post.query_selector_all('div[role="button"], span[role="button"]')
            for button in buttons[:80]:
                try:
                    label = " ".join((button.inner_text() or "").lower().split())
                    if not label or len(label) > 80:
                        continue
                    if any(term in label for term in excluded_terms):
                        continue
                    if any(term in label for term in expand_terms) and button.is_visible():
                        button.click()
                        self._human_delay(0.35, 0.7)
                        clicked = True
                        break
                except Exception:
                    continue
            if not clicked:
                break

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

        # Ảnh/video/font không tham gia trích xuất văn bản nhưng chiếm phần lớn
        # băng thông và thời gian render trên feed Facebook.
        context.route(
            "**/*",
            lambda route: route.abort()
            if route.request.resource_type in {"image", "media", "font"}
            else route.continue_(),
        )

        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
            Object.defineProperty(navigator, 'languages', { get: () => ['vi-VN', 'vi', 'en-US'] });
            window.chrome = { runtime: {} };
        """)

        page = context.new_page()
        page.set_default_timeout(10000)
        self._page = page
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
        """Lấy URL của post từ element (hỗ trợ pfbid, permalink, story_fbid, posts, timestamp links)."""
        if not self._page or not post_element:
            return None
        selectors = [
            'a[href*="pfbid"]',
            'a[href*="/posts/"]',
            'a[href*="/permalink"]',
            'a[href*="story_fbid"]',
            'a[href*="/share/p/"]',
            'a[href*="/photos/"]',
            'a[href*="/photo.php"]',
            'a[href*="/videos/"]',
            'a[href*="/watch/"]',
            'a[href*="/reel/"]',
            'h2 a[href]', 'h3 a[href]', 'h4 a[href]',
            'span > a[role="link"][href]',
            'a[aria-label*="giờ"][href]', 'a[aria-label*="phút"][href]',
            'a[aria-label*="tháng"][href]', 'a[aria-label*="ngày"][href]',
            'a[aria-label*="hrs"][href]', 'a[aria-label*="min"][href]',
        ]
        try:
            for sel in selectors:
                links = post_element.query_selector_all(sel)
                for link in links:
                    href = link.get_attribute("href")
                    if href:
                        full_url = _normalize_fb_url(href)
                        if self._looks_like_post_url(full_url):
                            return full_url
        except Exception:
            pass
        return None

    @staticmethod
    def _looks_like_post_url(url: str) -> bool:
        """Loại link tác giả/menu khỏi URL nguồn của bài viết."""
        lowered = (url or "").lower()
        return any(marker in lowered for marker in (
            "/posts/", "/permalink/", "story_fbid=", "pfbid", "/share/p/",
            "/photos/", "/photo.php", "/videos/", "/watch/", "/reel/",
        ))

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
            source_url=_normalize_fb_url(source_url),
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
        return _normalize_fb_url(url)

    @staticmethod
    def _extract_page_id(url: str) -> str:
        """Lấy page ID/username từ URL."""
        parsed = urlparse(url)
        path = parsed.path.strip("/")
        return path.split("/")[0] if path else url


def _normalize_fb_url(href: str) -> str:
    """Chuẩn hóa URL Facebook về dạng đầy đủ https://www.facebook.com/..."""
    if not href:
        return ""
    href = href.strip()
    if href.startswith("//"):
        href = "https:" + href
    elif href.startswith("/"):
        href = "https://www.facebook.com" + href
    elif not href.startswith("http"):
        href = "https://www.facebook.com/" + href.lstrip("/")

    # Loại bỏ tham số tracking thừa nếu có, bảo toàn tham số nhận diện quan trọng
    try:
        from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
        parsed = urlparse(href)
        if "facebook.com" in parsed.netloc:
            query = parse_qs(parsed.query)
            for tracking_key in ["__cft__", "__tn__", "ch", "ref", "notif_id", "notif_t"]:
                query.pop(tracking_key, None)
            new_query = urlencode(query, doseq=True)
            href = urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))
    except Exception:
        pass
    return href
