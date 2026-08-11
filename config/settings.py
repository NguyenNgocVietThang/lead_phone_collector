"""
config/settings.py — Cấu hình tập trung cho toàn bộ ứng dụng.
Load biến từ file .env. Sử dụng: from config.settings import settings
"""

import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# Tải .env từ thư mục gốc project
BASE_DIR = Path(__file__).parent.parent
load_dotenv(BASE_DIR / ".env")


class Settings:
    """Singleton chứa toàn bộ cấu hình ứng dụng."""

    # ── Paths ──────────────────────────────────────────────────────────────
    BASE_DIR: Path = BASE_DIR
    DATA_DIR: Path = BASE_DIR / "data"
    EXPORT_DIR: Path = BASE_DIR / "data" / "exports"
    LOG_DIR: Path = BASE_DIR / "logs"

    # ── Database ───────────────────────────────────────────────────────────
    DATABASE_PATH: Path = BASE_DIR / os.getenv("DATABASE_PATH", "data/leads.db")

    # Múi giờ hiển thị/lưu thời gian nghiệp vụ. Việt Nam dùng UTC+7 quanh năm.
    APP_UTC_OFFSET_HOURS: float = float(os.getenv("APP_UTC_OFFSET_HOURS", "7"))

    # ── Google Sheets ──────────────────────────────────────────────────────
    GOOGLE_SHEETS_CREDENTIALS_FILE: str = os.getenv(
        "GOOGLE_SHEETS_CREDENTIALS_FILE", "config/google-service-account.json"
    )
    GOOGLE_SHEET_ID: str = os.getenv("GOOGLE_SHEET_ID", "")
    GOOGLE_SHEET_NAME: str = os.getenv("GOOGLE_SHEET_NAME", "Leads")

    # ── Auth Sessions ──────────────────────────────────────────────────────
    FB_AUTH_PATH: Path = BASE_DIR / "data" / "fb_auth.json"
    GOOGLE_AUTH_PATH: Path = BASE_DIR / "data" / "google_auth.json"

    @property
    def is_fb_logged_in(self) -> bool:
        """True nếu file phiên đăng nhập Facebook tồn tại."""
        return self.FB_AUTH_PATH.exists() and self.FB_AUTH_PATH.stat().st_size > 10

    @property
    def is_google_logged_in(self) -> bool:
        """True nếu file phiên đăng nhập Google tồn tại."""
        return self.GOOGLE_AUTH_PATH.exists() and self.GOOGLE_AUTH_PATH.stat().st_size > 10

    # ── Facebook ───────────────────────────────────────────────────────────
    FACEBOOK_ACCESS_TOKEN: str = os.getenv("FACEBOOK_ACCESS_TOKEN", "")
    FACEBOOK_APP_ID: str = os.getenv("FACEBOOK_APP_ID", "")
    FACEBOOK_APP_SECRET: str = os.getenv("FACEBOOK_APP_SECRET", "")

    # OAuth đăng nhập ứng dụng (độc lập với storage_state của collectors)
    APP_BASE_URL: str = os.getenv("APP_BASE_URL", "http://localhost:5000").rstrip("/")
    GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET: str = os.getenv("GOOGLE_CLIENT_SECRET", "")

    @property
    def facebook_graph_enabled(self) -> bool:
        """True nếu có đủ thông tin để dùng Facebook Graph API."""
        return bool(self.FACEBOOK_ACCESS_TOKEN)

    # ── Playwright Browser ──────────────────────────────────────────────────
    PLAYWRIGHT_HEADLESS: bool = os.getenv("PLAYWRIGHT_HEADLESS", os.getenv("SELENIUM_HEADLESS", "true")).lower() == "true"
    PLAYWRIGHT_DELAY_MIN: float = float(os.getenv("PLAYWRIGHT_DELAY_MIN", os.getenv("SELENIUM_DELAY_MIN", "1.5")))
    PLAYWRIGHT_DELAY_MAX: float = float(os.getenv("PLAYWRIGHT_DELAY_MAX", os.getenv("SELENIUM_DELAY_MAX", "3.5")))

    # Compatibility properties for legacy Selenium references
    @property
    def SELENIUM_HEADLESS(self) -> bool:
        return self.PLAYWRIGHT_HEADLESS

    @property
    def SELENIUM_DELAY_MIN(self) -> float:
        return self.PLAYWRIGHT_DELAY_MIN

    @property
    def SELENIUM_DELAY_MAX(self) -> float:
        return self.PLAYWRIGHT_DELAY_MAX

    # ── Flask ──────────────────────────────────────────────────────────────
    FLASK_SECRET_KEY: str = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-in-production")
    FLASK_PORT: int = int(os.getenv("FLASK_PORT", "5000"))
    FLASK_DEBUG: bool = os.getenv("FLASK_DEBUG", "false").lower() == "true"

    # ── Logging ────────────────────────────────────────────────────────────
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE: Path = BASE_DIR / os.getenv("LOG_FILE", "logs/collector.log")

    def setup_directories(self):
        """Tạo các thư mục cần thiết nếu chưa tồn tại."""
        for d in [self.DATA_DIR, self.EXPORT_DIR, self.LOG_DIR]:
            d.mkdir(parents=True, exist_ok=True)

    def setup_logging(self):
        """Cấu hình logging với colorlog."""
        self.setup_directories()
        level = getattr(logging, self.LOG_LEVEL.upper(), logging.INFO)

        handlers = [
            logging.FileHandler(self.LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(),
        ]

        try:
            import colorlog
            formatter = colorlog.ColoredFormatter(
                "%(log_color)s%(asctime)s [%(levelname)s]%(reset)s %(name)s — %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            handlers[1].setFormatter(formatter)
        except ImportError:
            formatter = logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s — %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            for h in handlers:
                h.setFormatter(formatter)

        logging.basicConfig(level=level, handlers=handlers)


# Singleton instance
settings = Settings()
