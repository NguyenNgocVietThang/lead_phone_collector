"""Kiểm thử hồi quy cho các job Maps và luồng quét Facebook."""

from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

from collectors.facebook import (
    FacebookCollector,
    FbCollectionResult,
    FbPhoneResult,
    SRC_PLAYWRIGHT_POST,
    SRC_PLAYWRIGHT_COMMENT,
    SRC_NAME_SEARCH_BIO,
    SRC_SEARCH_POST,
)
from collectors.google_maps import BusinessInfo, CollectionResult


def test_maps_background_job_accepts_and_saves_collector_user(monkeypatch):
    import collectors.google_maps as maps_module
    import storage.sheets as sheets_module
    import ui.app as web

    business = BusinessInfo(
        name="Cửa hàng A",
        phone_raw="0984 937 323",
        phone_normalized="0984937323",
        maps_url="https://www.google.com/maps/place/a",
        carrier="Viettel",
    )
    collection = CollectionResult(
        keyword="gia dụng",
        area="Hà Nội",
        businesses=[business],
        total_scraped=1,
        total_with_phone=1,
    )

    class FakeCollector:
        def __init__(self, **kwargs):
            self.progress_callback = kwargs.get("progress_callback")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def search(self, keyword, area, limit):
            assert (keyword, area, limit) == ("gia dụng", "Hà Nội", 10)
            return collection

    class FakeDatabase:
        def __init__(self):
            self.saved_leads = []
            self.finished = None
            self.failed = None

        def insert_leads_batch(self, leads):
            self.saved_leads = leads
            return {"inserted": 1, "duplicates": 0}

        def get_leads(self, **kwargs):
            return self.saved_leads

        def finish_job(self, job_id, **kwargs):
            self.finished = (job_id, kwargs)

        def fail_job(self, job_id, error):
            self.failed = (job_id, error)

    class FakeSheets:
        def sync_leads(self, leads):
            return {"synced": len(leads), "skipped": 0, "error": None}

    fake_db = FakeDatabase()
    monkeypatch.setattr(maps_module, "GoogleMapsCollector", FakeCollector)
    monkeypatch.setattr(sheets_module, "GoogleSheetsSync", FakeSheets)
    monkeypatch.setattr(web, "db", fake_db)
    monkeypatch.setattr(web.threading, "Timer", lambda *args, **kwargs: SimpleNamespace(start=lambda: None))

    try:
        web._run_maps_job(901, "gia dụng", "Hà Nội", 10, "Nguyễn An")
    finally:
        web._active_jobs.pop(901, None)

    assert fake_db.failed is None
    assert fake_db.finished == (
        901,
        {"total_found": 1, "new_leads": 1, "duplicates": 0},
    )
    assert fake_db.saved_leads[0].collector_user == "Nguyễn An"


def test_facebook_profile_about_url_preserves_profile_id():
    about_url = FacebookCollector._build_about_url(
        "https://web.facebook.com/profile.php?id=61577782154891"
    )
    parsed = urlparse(about_url)

    assert parsed.path == "/profile.php"
    assert parse_qs(parsed.query) == {"id": ["61577782154891"], "sk": ["about"]}


def test_facebook_post_url_filter_ignores_author_links():
    assert FacebookCollector._looks_like_post_url(
        "https://www.facebook.com/groups/123/posts/456"
    )
    assert FacebookCollector._looks_like_post_url(
        "https://www.facebook.com/share/p/AbCdEf"
    )
    assert not FacebookCollector._looks_like_post_url(
        "https://www.facebook.com/ten-tac-gia"
    )


def test_facebook_falls_back_to_browser_when_graph_returns_nothing(monkeypatch, mocker):
    from config.settings import settings

    collector = FacebookCollector(headless=True)
    fallback_result = FbPhoneResult(
        phone_raw="0984 937 323",
        phone_normalized="0984937323",
        carrier="Viettel",
        is_valid=True,
        source=SRC_PLAYWRIGHT_POST,
        source_url="https://www.facebook.com/example/posts/1",
    )
    monkeypatch.setattr(settings, "FACEBOOK_ACCESS_TOKEN", "expired-token")
    mocker.patch.object(collector, "_collect_graph_api", return_value=[])
    browser = mocker.patch.object(
        collector, "_collect_playwright_target", return_value=[fallback_result]
    )

    result = collector.collect(
        "https://www.facebook.com/example",
        target_type="page",
        sources=["posts"],
        max_posts=5,
    )

    browser.assert_called_once()
    assert result.results == [fallback_result]


def test_facebook_virtualized_feed_does_not_skip_replaced_nodes(mocker):
    collector = FacebookCollector(headless=True)
    page = mocker.MagicMock()
    collector._page = page

    first = mocker.MagicMock()
    first.url = "https://www.facebook.com/example/posts/1"
    first.inner_text.return_value = "Bài một liên hệ 0984937323"
    first.query_selector_all.return_value = []

    second = mocker.MagicMock()
    second.url = "https://www.facebook.com/example/posts/2"
    second.inner_text.return_value = "Bài hai liên hệ 0343204188"
    second.query_selector_all.return_value = []

    mocker.patch.object(collector, "_find_feed_units", side_effect=[[first], [second]])
    mocker.patch.object(collector, "_get_post_url", side_effect=lambda post: post.url)
    mocker.patch.object(collector, "_get_page_name", return_value="Trang thử nghiệm")
    mocker.patch.object(collector, "_dismiss_popups")
    mocker.patch.object(collector, "_human_delay")

    result = FbCollectionResult(page_url="https://www.facebook.com/example")
    phones = collector._scrape_feed_units(
        result.page_url,
        ["posts"],
        2,
        result,
    )

    assert [phone.phone_normalized for phone in phones] == ["0984937323", "0343204188"]


def test_get_post_url_recognizes_week_and_year_relative_labels(mocker):
    """Bài viết cũ hiển thị mốc thời gian 'X tuần'/'X năm' vẫn phải lấy được link cụ thể."""
    collector = FacebookCollector(headless=True)
    collector._page = mocker.MagicMock()

    link = mocker.MagicMock()
    link.get_attribute.return_value = "/groups/123/posts/456"

    def query_selector_all(selector):
        if selector == 'a[aria-label*="tuần"][href]':
            return [link]
        return []

    post = mocker.MagicMock()
    post.query_selector_all.side_effect = query_selector_all

    url = collector._get_post_url(post)
    assert url == "https://www.facebook.com/groups/123/posts/456"


def test_get_post_url_falls_back_to_any_post_like_link(mocker):
    """Khi không selector cụ thể nào khớp, phải quét toàn bộ link trong bài viết
    thay vì trả về None (khiến kết quả rơi về URL chung của trang/nhóm/tìm kiếm)."""
    collector = FacebookCollector(headless=True)
    collector._page = mocker.MagicMock()

    author_link = mocker.MagicMock()
    author_link.get_attribute.return_value = "/mot-tac-gia"
    post_link = mocker.MagicMock()
    post_link.get_attribute.return_value = "/posts/789"

    post = mocker.MagicMock()

    def query_selector_all(selector):
        if selector == "a[href]":
            return [author_link, post_link]
        return []

    post.query_selector_all.side_effect = query_selector_all

    url = collector._get_post_url(post)
    assert url == "https://www.facebook.com/posts/789"


def test_scrape_feed_units_does_not_mislabel_comment_phone_as_post(mocker):
    """SĐT chỉ xuất hiện trong bình luận (nhưng lồng trong text tổng của bài viết)
    phải được gắn nguồn 'comment', không bị gắn nhầm thành 'post'."""
    collector = FacebookCollector(headless=True)
    page = mocker.MagicMock()
    collector._page = page
    page.query_selector.return_value = None  # không có dialog bình luận nào mở

    post = mocker.MagicMock()
    post.url = "https://www.facebook.com/example/posts/1"
    # inner_text() của Facebook thường lồng cả preview bình luận vào bài viết.
    post.inner_text.return_value = "Bài viết không có SĐT. Bình luận: liên hệ 0984937323 nhé"

    comment_el = mocker.MagicMock()
    comment_el.inner_text.return_value = "liên hệ 0984937323 nhé"

    def post_query_selector_all(selector):
        if 'role="article"' in selector or "ul li" in selector:
            return [comment_el]
        return []

    post.query_selector_all.side_effect = post_query_selector_all

    mocker.patch.object(collector, "_find_feed_units", side_effect=[[post]])
    mocker.patch.object(collector, "_get_post_url", return_value=post.url)
    mocker.patch.object(collector, "_get_page_name", return_value="Trang thử nghiệm")
    mocker.patch.object(collector, "_dismiss_popups")
    mocker.patch.object(collector, "_human_delay")
    mocker.patch.object(collector, "_expand_comment_threads")

    result = FbCollectionResult(page_url=post.url)
    phones = collector._scrape_feed_units(result.page_url, ["posts", "comments"], 1, result)

    assert len(phones) == 1
    assert phones[0].phone_normalized == "0984937323"
    assert phones[0].source == SRC_PLAYWRIGHT_COMMENT


def test_looks_like_profile_url_filters_non_profile_links():
    assert FacebookCollector._looks_like_profile_url("https://www.facebook.com/nguyenvana")
    assert FacebookCollector._looks_like_profile_url("https://www.facebook.com/profile.php?id=100012345")
    assert FacebookCollector._looks_like_profile_url(
        "https://www.facebook.com/people/Nguyen-Van-A/pfbid02abc/"
    )
    assert not FacebookCollector._looks_like_profile_url("https://www.facebook.com/search/people/?q=a")
    assert not FacebookCollector._looks_like_profile_url("https://www.facebook.com/groups/12345")
    assert not FacebookCollector._looks_like_profile_url("https://www.facebook.com/nguyenvana/posts/123")
    assert not FacebookCollector._looks_like_profile_url("https://www.facebook.com/help/somepage")


def test_find_profile_links_filters_and_dedupes(mocker):
    collector = FacebookCollector(headless=True)
    page = mocker.MagicMock()
    collector._page = page

    hrefs = [
        "/nguyenvana?fref=search",
        "/nguyenvana",  # trùng với link trên sau khi bỏ query
        "/groups/12345",  # bị loại
        "/profile.php?id=100099",
        "/tranthib",
        "/help/contact",  # bị loại
    ]
    anchors = []
    for href in hrefs:
        a = mocker.MagicMock()
        a.get_attribute.return_value = href
        anchors.append(a)
    page.query_selector_all.return_value = anchors

    links = collector._find_profile_links(max_count=10)

    assert links == [
        "https://www.facebook.com/nguyenvana?fref=search",
        "https://www.facebook.com/profile.php?id=100099",
        "https://www.facebook.com/tranthib",
    ]


def test_collect_name_search_scans_each_matched_profile(mocker):
    """Chế độ 'Tìm theo tên' phải quét lần lượt từng hồ sơ khớp và không rò rỉ
    page_name giữa các hồ sơ khác nhau."""
    collector = FacebookCollector(headless=True)
    collector._page = mocker.MagicMock()
    mocker.patch.object(collector, "_dismiss_popups")
    mocker.patch.object(collector, "_human_delay")
    mocker.patch.object(
        collector,
        "_find_profile_links",
        return_value=[
            "https://www.facebook.com/nguyenvana",
            "https://www.facebook.com/tranthib",
        ],
    )

    def fake_scrape_about(url, profile_result, is_profile=False, source_tag_override=None):
        profile_result.page_name = "Nguyễn Văn A" if "nguyenvana" in url else "Trần Thị B"
        return [FbPhoneResult(
            phone_raw="0984937323", phone_normalized="0984937323", carrier="Viettel",
            is_valid=True, source=source_tag_override, source_url=url,
            page_name=profile_result.page_name,
        )]

    mocker.patch.object(collector, "_scrape_about", side_effect=fake_scrape_about)
    mocker.patch.object(collector, "_scrape_feed_units", return_value=[])

    result = FbCollectionResult(page_url="Nguyễn Văn A")
    phones = collector._collect_name_search("Nguyễn Văn A", ["about", "posts"], 10, 2, result)

    assert len(phones) == 2
    assert {p.page_name for p in phones} == {"Nguyễn Văn A", "Trần Thị B"}
    assert all(p.source == SRC_NAME_SEARCH_BIO for p in phones)
    assert result.page_name == "Tìm theo tên: Nguyễn Văn A"


def test_collect_name_search_also_searches_posts_by_keyword(mocker):
    """'Tìm theo Tên' phải gộp cả bước tìm bài viết theo từ khóa (fb_search_post)
    lẫn bước quét hồ sơ khớp tên, không chỉ riêng lẻ như trước."""
    collector = FacebookCollector(headless=True)
    collector._page = mocker.MagicMock()
    mocker.patch.object(collector, "_dismiss_popups")
    mocker.patch.object(collector, "_human_delay")
    mocker.patch.object(collector, "_find_profile_links", return_value=[])

    def fake_scrape_feed_units(url, sources, max_posts, result, src_post=None, src_comment=None, src_liker=None):
        if "search/posts" in url:
            return [FbPhoneResult(
                phone_raw="0984937323", phone_normalized="0984937323", carrier="Viettel",
                is_valid=True, source=src_post, source_url=url, page_name=result.page_name,
            )]
        return []

    mocker.patch.object(collector, "_scrape_feed_units", side_effect=fake_scrape_feed_units)

    result = FbCollectionResult(page_url="sang nhượng spa quận 1")
    phones = collector._collect_name_search("sang nhượng spa quận 1", ["posts"], 10, 3, result)

    assert len(phones) == 1
    assert phones[0].source == SRC_SEARCH_POST


def test_normalize_search_query_collapses_whitespace():
    assert FacebookCollector._normalize_search_query("  Nguyễn   Văn A  ") == "Nguyễn Văn A"


def test_collect_maps_link_target_type_to_auto(mocker):
    """target_type='link' (lựa chọn UI) phải được ánh xạ sang tự nhận diện URL."""
    collector = FacebookCollector(headless=True)
    mocker.patch.object(collector, "_ensure_browser")
    playwright = mocker.patch.object(collector, "_collect_playwright_target", return_value=[])

    collector.collect("https://www.facebook.com/groups/12345", target_type="link", sources=["posts"])

    called_args = playwright.call_args.args
    assert called_args[1] == "group"


def test_collect_dispatches_name_search_target_type(mocker):
    """target_type='name_search' phải được collect() định tuyến tới _collect_name_search."""
    collector = FacebookCollector(headless=True)
    mocker.patch.object(collector, "_ensure_browser")
    name_search = mocker.patch.object(collector, "_collect_name_search", return_value=[])

    result = collector.collect("Nguyễn Văn A", target_type="name_search", sources=["about"], max_profiles=3)

    assert result.page_url == "Nguyễn Văn A"
    name_search.assert_called_once()
    called_args = name_search.call_args.args
    assert called_args[0] == "Nguyễn Văn A"
    assert called_args[3] == 3  # max_profiles
