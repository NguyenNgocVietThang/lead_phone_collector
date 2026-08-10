"""Kiểm thử hồi quy cho các job Maps và luồng quét Facebook."""

from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

from collectors.facebook import (
    FacebookCollector,
    FbCollectionResult,
    FbPhoneResult,
    SRC_PLAYWRIGHT_POST,
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
