"""Kiểm thử đăng ký, đăng nhập OAuth/email và đăng xuất của Web UI."""

import hashlib

import pytest

from storage.database import LeadDatabase


@pytest.fixture
def auth_web(tmp_path, monkeypatch):
    import ui.app as web

    test_db = LeadDatabase(tmp_path / "web-auth.db")
    monkeypatch.setattr(web, "db", test_db)
    web.app.config.update(TESTING=True, SECRET_KEY="test-secret")
    return web, test_db


def _set_csrf(client, token="csrf-test-token"):
    with client.session_transaction() as state:
        state["csrf_token"] = token
    return token


def test_register_is_public_and_uses_modern_hash(auth_web):
    web, database = auth_web
    with web.app.test_client() as client:
        assert client.get("/register").status_code == 200
        token = _set_csrf(client)
        response = client.post(
            "/register",
            data={
                "csrf_token": token,
                "full_name": "Nguyễn Văn A",
                "email": "USER@example.com",
                "password": "secret1",
                "confirm_password": "secret1",
            },
        )

        assert response.status_code == 302
        user = database.get_user_by_email("user@example.com")
        assert user and not (len(user["password_hash"]) == 64 and user["password_hash"].isalnum())
        with client.session_transaction() as state:
            assert state["user_id"] == user["id"]


@pytest.mark.parametrize(
    "payload,message",
    [
        ({"full_name": "", "email": "a@example.com", "password": "secret1", "confirm_password": "secret1"}, "đầy đủ"),
        ({"full_name": "A", "email": "invalid", "password": "secret1", "confirm_password": "secret1"}, "không hợp lệ"),
        ({"full_name": "A", "email": "a@example.com", "password": "123", "confirm_password": "123"}, "ít nhất 6"),
        ({"full_name": "A", "email": "a@example.com", "password": "secret1", "confirm_password": "secret2"}, "không khớp"),
    ],
)
def test_register_validation(auth_web, payload, message):
    web, _ = auth_web
    with web.app.test_client() as client:
        payload["csrf_token"] = _set_csrf(client)
        response = client.post("/register", data=payload)
        assert response.status_code == 200
        assert message in response.get_data(as_text=True)


def test_email_login_and_legacy_hash_upgrade(auth_web):
    web, database = auth_web
    legacy_hash = hashlib.sha256(b"secret1").hexdigest()
    user_id = database.create_user("Legacy", "legacy@example.com", legacy_hash)

    with web.app.test_client() as client:
        token = _set_csrf(client)
        response = client.post(
            "/login?next=/leads",
            data={"csrf_token": token, "user_identity": "legacy@example.com", "password": "secret1"},
        )
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/leads")
        assert database.get_user_by_id(user_id)["password_hash"] != legacy_hash


def test_name_only_login_is_rejected(auth_web):
    web, _ = auth_web
    with web.app.test_client() as client:
        token = _set_csrf(client)
        response = client.post(
            "/login",
            data={"csrf_token": token, "user_identity": "Tên bất kỳ", "password": ""},
        )
        assert response.status_code == 200
        with client.session_transaction() as state:
            assert "user_id" not in state


class FakeOAuthClient:
    def __init__(self, token=None, facebook_profile=None):
        self.token = token or {}
        self.facebook_profile = facebook_profile or {}
        self.redirect_uri = None

    def authorize_redirect(self, redirect_uri):
        from flask import redirect

        self.redirect_uri = redirect_uri
        return redirect("https://provider.example/authorize")

    def authorize_access_token(self):
        return self.token

    def userinfo(self, token=None):
        return self.token.get("userinfo", {})

    def get(self, path, token=None):
        profile = self.facebook_profile

        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return profile

        return Response()


def test_oauth_start_uses_configured_callback_and_blocks_external_next(auth_web, monkeypatch):
    web, _ = auth_web
    fake = FakeOAuthClient()
    monkeypatch.setattr(web.settings, "GOOGLE_CLIENT_ID", "client")
    monkeypatch.setattr(web.settings, "GOOGLE_CLIENT_SECRET", "secret")
    monkeypatch.setattr(web.settings, "APP_BASE_URL", "https://app.example.com")
    monkeypatch.setattr(web.oauth, "create_client", lambda provider: fake)

    with web.app.test_client() as client:
        response = client.get("/auth/google?next=https://evil.example/steal")
        assert response.status_code == 302
        assert fake.redirect_uri == "https://app.example.com/auth/google/callback"
        with client.session_transaction() as state:
            assert state["oauth_next"] == "/"


def test_google_oauth_creates_session(auth_web, monkeypatch):
    web, database = auth_web
    fake = FakeOAuthClient(token={"userinfo": {
        "sub": "google-1", "email": "google@example.com", "email_verified": True, "name": "Google User"
    }})
    monkeypatch.setattr(web.oauth, "create_client", lambda provider: fake)

    with web.app.test_client() as client:
        with client.session_transaction() as state:
            state["oauth_next"] = "/leads"
        response = client.get("/auth/google/callback")
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/leads")
        user = database.get_user_by_email("google@example.com")
        with client.session_transaction() as state:
            assert state["user_id"] == user["id"]
            assert state["auth_provider"] == "google"


def test_facebook_oauth_links_existing_email(auth_web, monkeypatch):
    web, database = auth_web
    existing_id = database.create_user("Existing", "same@example.com", "hash")
    fake = FakeOAuthClient(token={"access_token": "temporary"}, facebook_profile={
        "id": "facebook-1", "email": "same@example.com", "name": "Facebook User"
    })
    monkeypatch.setattr(web.oauth, "create_client", lambda provider: fake)

    with web.app.test_client() as client:
        response = client.get("/auth/facebook/callback")
        assert response.status_code == 302
        with client.session_transaction() as state:
            assert state["user_id"] == existing_id
        assert database.get_oauth_identity("facebook", "facebook-1")["user_id"] == existing_id


@pytest.mark.parametrize(
    "profile",
    [
        {"sub": "google-2", "email": "unverified@example.com", "email_verified": False, "name": "No Verify"},
        {"sub": "google-3", "email_verified": True, "name": "No Email"},
    ],
)
def test_google_oauth_rejects_unverified_or_missing_email(auth_web, monkeypatch, profile):
    web, _ = auth_web
    monkeypatch.setattr(web.oauth, "create_client", lambda provider: FakeOAuthClient(token={"userinfo": profile}))

    with web.app.test_client() as client:
        response = client.get("/auth/google/callback")
        assert response.status_code == 302
        with client.session_transaction() as state:
            assert "user_id" not in state


def test_logout_clears_app_session_but_keeps_collector_files(auth_web, tmp_path, monkeypatch):
    web, database = auth_web
    user_id = database.create_user("User", "user@example.com", "hash")
    fb_state = tmp_path / "fb_auth.json"
    google_state = tmp_path / "google_auth.json"
    fb_state.write_text("{\"cookies\": [1]}", encoding="utf-8")
    google_state.write_text("{\"cookies\": [1]}", encoding="utf-8")
    monkeypatch.setattr(web.settings, "FB_AUTH_PATH", fb_state)
    monkeypatch.setattr(web.settings, "GOOGLE_AUTH_PATH", google_state)

    with web.app.test_client() as client:
        token = _set_csrf(client)
        with client.session_transaction() as state:
            state["user_id"] = user_id
            state["user_identity"] = "User"
        response = client.post("/logout", data={"csrf_token": token})
        assert response.status_code == 302
        assert fb_state.exists() and google_state.exists()
        assert client.get("/leads").status_code == 302
        with client.session_transaction() as state:
            assert "user_id" not in state


def test_auth_forms_require_csrf(auth_web):
    web, _ = auth_web
    with web.app.test_client() as client:
        assert client.post("/login", data={"user_identity": "a@example.com", "password": "x"}).status_code == 400
        assert client.post("/register", data={}).status_code == 400
        assert client.post("/logout", data={}).status_code == 400


def test_invalid_provider_and_page_cache_headers(auth_web):
    web, _ = auth_web
    with web.app.test_client() as client:
        assert client.get("/auth/unknown").status_code == 404
        response = client.get("/login")
        assert response.headers["Cache-Control"] == "no-store, max-age=0"
