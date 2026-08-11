"""
wsgi.py — WSGI entry point cho Gunicorn / Production server.
"""

from config.settings import settings
from ui.app import app

# Khởi tạo thư mục & logging
settings.setup_directories()
settings.setup_logging()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=settings.FLASK_PORT)
