"""
storage/auth.py — Quản lý phiên đăng nhập tương tác & lưu cookie storage_state cho Facebook và Google.
"""

import json
import logging
import time
from pathlib import Path
from typing import Optional
from config.settings import settings

logger = logging.getLogger(__name__)


class AuthManager:
    """Quản lý đăng nhập tương tác và lưu phiên Playwright storage_state."""

    @staticmethod
    def get_auth_path(service: str) -> Path:
        service = service.lower().strip()
        if service == "facebook":
            return settings.FB_AUTH_PATH
        elif service == "google":
            return settings.GOOGLE_AUTH_PATH
        else:
            raise ValueError(f"Dịch vụ không hỗ trợ: {service}")

    @classmethod
    def is_logged_in(cls, service: str) -> bool:
        path = cls.get_auth_path(service)
        return path.exists() and path.stat().st_size > 10

    @classmethod
    def get_user_info(cls, service: str) -> dict:
        """Lấy thông tin người dùng từ file auth session đã lưu (nếu có)."""
        service = service.lower().strip()
        try:
            path = cls.get_auth_path(service)
            if path.exists() and path.stat().st_size > 10:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                cookies = data.get("cookies", []) if isinstance(data, dict) else []
                user_id = None
                if service == "facebook":
                    for c in cookies:
                        if c.get("name") == "c_user":
                            user_id = c.get("value")
                            break
                    name = f"FB User ({user_id})" if user_id else "Tài khoản Facebook"
                elif service == "google":
                    name = "Tài khoản Google"
                else:
                    name = f"Tài khoản {service.title()}"
                return {"logged_in": True, "name": name, "user_id": user_id}
        except Exception as e:
            logger.error("Lỗi khi đọc thông tin user %s: %s", service, e)

        return {"logged_in": False, "name": f"Tài khoản {service.title()}"}

    @classmethod
    def clear_session(cls, service: str) -> bool:
        """Xóa file phiên đăng nhập."""
        try:
            path = cls.get_auth_path(service)
            if path.exists():
                path.unlink()
                logger.info("Đã xóa phiên đăng nhập: %s", service)
                return True
        except Exception as e:
            logger.error("Lỗi khi xóa phiên đăng nhập %s: %s", service, e)
        return False

    @classmethod
    def save_cookie_json(cls, service: str, json_str: str) -> bool:
        """Lưu trực tiếp mảng cookies/storage_state định dạng JSON."""
        try:
            path = cls.get_auth_path(service)
            path.parent.mkdir(parents=True, exist_ok=True)
            data = json.loads(json_str)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info("Đã lưu thủ công session JSON cho %s", service)
            return True
        except Exception as e:
            logger.error("Lỗi khi lưu JSON session %s: %s", service, e)
            return False

    @classmethod
    def launch_interactive_login(
        cls,
        service: str,
        timeout_seconds: int = 180,
    ) -> bool:
        """
        Khởi chạy trình duyệt có giao diện (headless=False) để người dùng tự đăng nhập.
        Tự động lưu storage_state khi phát hiện đã đăng nhập thành công hoặc đóng trình duyệt.
        """
        from playwright.sync_api import sync_playwright

        auth_path = cls.get_auth_path(service)
        auth_path.parent.mkdir(parents=True, exist_ok=True)

        login_urls = {
            "facebook": "https://www.facebook.com/login",
            "google": "https://accounts.google.com/",
        }

        url = login_urls.get(service.lower(), "https://www.facebook.com/login")
        logger.info("Khởi động đăng nhập tương tác [%s]: %s", service, url)

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=False,
                    args=[
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-blink-features=AutomationControlled",
                        "--start-maximized",
                    ],
                )

                # Dùng existing auth_state nếu có để nối tiếp session
                initial_state = str(auth_path) if auth_path.exists() else None

                context_kwargs = {
                    "viewport": {"width": 1280, "height": 800},
                    "locale": "vi-VN",
                    "user_agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/125.0.0.0 Safari/537.36"
                    ),
                }
                if initial_state:
                    context_kwargs["storage_state"] = initial_state

                context = browser.new_context(**context_kwargs)
                context.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                """)

                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded")

                start_time = time.time()
                print(f"\n🔑 Đã mở trình duyệt đăng nhập {service.upper()}.")
                print("Vui lòng hoàn tất đăng nhập trên cửa sổ trình duyệt...")

                # Vòng lặp chờ người dùng thao tác đăng nhập hoặc đóng trình duyệt
                while time.time() - start_time < timeout_seconds:
                    if page.is_closed():
                        logger.info("Người dùng đã đóng cửa sổ trình duyệt.")
                        break

                    current_url = page.url
                    # Kiểm tra dấu hiệu đã đăng nhập thành công
                    if service == "facebook":
                        # Sau đăng nhập, URL thường về feed, homepage, hoặc chứa 'facebook.com/' mà không có 'login'
                        if "facebook.com" in current_url and not any(k in current_url for k in ["login", "checkpoint", "two_step"]):
                            logger.info("Phát hiện đăng nhập Facebook thành công: %s", current_url)
                            time.sleep(3)  # Chờ cookie ghi nhận hoàn tất
                            break
                    elif service == "google":
                        if any(k in current_url for k in ["myaccount.google.com", "google.com/search", "maps.google.com"]) or ("accounts.google.com" in current_url and "signin" not in current_url and "v3" not in current_url):
                            logger.info("Phát hiện đăng nhập Google thành công: %s", current_url)
                            time.sleep(3)
                            break

                    time.sleep(2)

                # Lưu phiên storage state
                try:
                    context.storage_state(path=str(auth_path))
                    logger.info("Đã lưu storage_state vào %s", auth_path)
                    print(f"✅ Đã lưu thành công phiên đăng nhập {service.upper()}!")
                    browser.close()
                    return True
                except Exception as save_err:
                    logger.warning("Không thể lưu storage_state: %s", save_err)
                    browser.close()
                    return False

        except Exception as e:
            logger.error("Lỗi khi đăng nhập tương tác [%s]: %s", service, e, exc_info=True)
            return False
