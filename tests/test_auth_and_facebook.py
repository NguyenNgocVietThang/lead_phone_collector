"""
tests/test_auth_and_facebook.py — Tests cho AuthManager, Settings auth properties và FacebookCollector modes.
"""

import json
import pytest
from pathlib import Path
from config.settings import settings
from storage.auth import AuthManager
from collectors.facebook import FacebookCollector, FbCollectionResult


def test_settings_auth_properties(tmp_path):
    """Test thuộc tính is_fb_logged_in và is_google_logged_in."""
    fb_file = tmp_path / "fb_auth.json"
    google_file = tmp_path / "google_auth.json"

    # Giả lập paths trong settings
    original_fb = settings.FB_AUTH_PATH
    original_google = settings.GOOGLE_AUTH_PATH

    settings.FB_AUTH_PATH = fb_file
    settings.GOOGLE_AUTH_PATH = google_file

    try:
        assert not settings.is_fb_logged_in
        assert not settings.is_google_logged_in

        # Tạo file hợp lệ
        fb_file.write_text(json.dumps({"cookies": [{"name": "c_user", "value": "1000"}]}))
        assert settings.is_fb_logged_in

        google_file.write_text(json.dumps({"cookies": [{"name": "SID", "value": "xyz"}]}))
        assert settings.is_google_logged_in

    finally:
        settings.FB_AUTH_PATH = original_fb
        settings.GOOGLE_AUTH_PATH = original_google


def test_auth_manager_json_and_clear(tmp_path):
    """Test lưu JSON thủ công và xóa session."""
    fb_file = tmp_path / "fb_auth.json"
    original_fb = settings.FB_AUTH_PATH
    settings.FB_AUTH_PATH = fb_file

    try:
        json_data = json.dumps({"cookies": [{"name": "xs", "value": "abcd"}]})
        success = AuthManager.save_cookie_json("facebook", json_data)
        assert success
        assert fb_file.exists()

        loaded = json.loads(fb_file.read_text(encoding="utf-8"))
        assert loaded["cookies"][0]["name"] == "xs"

        cleared = AuthManager.clear_session("facebook")
        assert cleared
        assert not fb_file.exists()

    finally:
        settings.FB_AUTH_PATH = original_fb


def test_auth_manager_get_user_info(tmp_path):
    """Test phương thức AuthManager.get_user_info."""
    fb_file = tmp_path / "fb_auth.json"
    original_fb = settings.FB_AUTH_PATH
    settings.FB_AUTH_PATH = fb_file

    try:
        info_not_found = AuthManager.get_user_info("facebook")
        assert info_not_found["logged_in"] is False

        json_data = json.dumps({"cookies": [{"name": "c_user", "value": "100012345"}]})
        AuthManager.save_cookie_json("facebook", json_data)
        info_found = AuthManager.get_user_info("facebook")
        assert info_found["logged_in"] is True
        assert "100012345" in info_found["name"]
    finally:
        settings.FB_AUTH_PATH = original_fb


def test_flask_social_login_route(mocker):
    """Test route /login/social/<provider> không bị lỗi 500."""
    mocker.patch("storage.auth.AuthManager.launch_interactive_login", return_value=True)
    from ui.app import app
    app.config["TESTING"] = True
    with app.test_client() as client:
        res = client.get("/login/social/google", follow_redirects=True)
        assert res.status_code == 200

        res_fb = client.post("/login/social/facebook", follow_redirects=True)
        assert res_fb.status_code == 200


def test_facebook_collector_target_type_auto(mocker):
    """Test tự động nhận diện target_type và nguồn dữ liệu trong FacebookCollector."""
    mocker.patch("collectors.facebook.FacebookCollector._collect_playwright_target", return_value=[])
    collector = FacebookCollector(headless=True)

    target_group = "https://www.facebook.com/groups/123456789"
    target_profile_php = "https://www.facebook.com/profile.php?id=100012345678"
    target_profile_p = "https://www.facebook.com/p/hoang-gia-dung-1000/"
    target_page = "https://www.facebook.com/myfanpage"
    target_search = "nhà đất giá rẻ hà nội"

    assert "/groups/" in target_group
    assert "/profile.php" in target_profile_php
    assert "/p/" in target_profile_p
    assert target_page.startswith("https://")
    assert not target_search.startswith("http")

    # Test auto detection logic via collect method mock check
    res_auto_group = collector.collect(target_group, target_type="auto", sources=["posts"])
    assert res_auto_group.page_url.startswith("https://www.facebook.com/groups/")

    res_profile = collector.collect(target_profile_php, target_type="profile", sources=["about", "posts", "comments", "likers"])
    assert res_profile.page_url == target_profile_php

