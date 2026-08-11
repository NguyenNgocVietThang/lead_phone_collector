# Base image chính thức hỗ trợ Python & Playwright Chromium trên Ubuntu Jammy
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

# Thiết lập thư mục làm việc trong container
WORKDIR /app

# Cài đặt Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Kiểm tra & đảm bảo Playwright Chromium đã được cài đặt
RUN playwright install chromium

# Copy toàn bộ mã nguồn vào container
COPY . .

# Tạo các thư mục lưu trữ dữ liệu nếu chưa có
RUN mkdir -p data data/exports logs storage

# Biến môi trường mặc định
ENV PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_HEADLESS=true \
    PORT=5000

# Port ứng dụng lắng nghe
EXPOSE 5000

# Khởi chạy Gunicorn WSGI server với timeout cao hơn cho các tác vụ scraping
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "120", "wsgi:app"]
