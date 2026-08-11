# Huong Dan Trien Khai (Deployment Guide)

Tài liệu này hướng dẫn chi tiết các phương án triển khai ứng dụng Lead Phone Collector lên các dịch vụ đám mây PaaS (Render, Railway, Fly.io) hoặc VPS Linux bằng Docker.

---

## Phương an 1: Trien khai len Render.com (Free / Paid PaaS)

Render là dịch vụ đám mây hỗ trợ chạy ứng dụng Docker rất dễ dàng.

### Cac buoc thuc hien:
1. Đăng ký/Đăng nhập tài khoản tại https://render.com
2. Kết nối tài khoản GitHub/GitLab của bạn với Render.
3. Tạo **New Web Service** va chọn repository dự án này.
4. Chọn môi trường **Docker** (Render sẽ tự động phát hiện `Dockerfile`).
5. Thiết lập các Biến môi trường (Environment Variables):
   - `FLASK_SECRET_KEY`: Chuỗi bí mật ngẫu nhiên bảo mật session.
   - `APP_BASE_URL`: Đặt URL thực tế của ứng dụng (ví dụ: `https://lead-phone-collector.onrender.com`).
   - `PLAYWRIGHT_HEADLESS`: `true`
6. (Tùy chọn) Thêm Persistent Disk mount vào thư mục `/app/data` để duy trì file cơ sở dữ liệu SQLite (`leads.db`) khi dịch vụ khởi động lại.
7. Chọn **Create Web Service** và chờ Render build Docker image và khởi chạy.

---

## Phuong an 2: Trien khai len Railway.app

Railway cung cấp khả năng tự động build Dockerfile và cấu hình tên miền HTTPS chỉ trong vài thao tác.

### Cac buoc thuc hien:
1. Truy cập https://railway.app và đăng nhập bằng GitHub.
2. Chọn **New Project** -> **Deploy from GitHub repo**.
3. Chọn repository dự án Lead Phone Collector.
4. Railway sẽ tự động phát hiện `Dockerfile` và tiến hành build.
5. Trong mục **Variables**, thêm các biến cần thiết:
   - `FLASK_SECRET_KEY`
   - `APP_BASE_URL` (URL được Railway cấp dạng `https://xxx.up.railway.app`)
   - `PLAYWRIGHT_HEADLESS=true`
6. Thêm Volume trong tab **Volumes** và gắn mount path là `/app/data`.
7. Đợi tiến trình deploy hoàn tất và truy cập đường dẫn do Railway cung cấp.

---

## Phuong an 3: Trien khai len Fly.io

Fly.io phù hợp cho việc chạy Docker container với độ trễ thấp và hỗ trợ lưu trữ Persistent Volume tốt.

### Cac buoc thuc hien:
1. Cài đặt Fly CLI trên máy tính:
   - Windows (PowerShell): `iwr https://fly.io/install.ps1 -useb | iex`
2. Đăng nhập Fly.io qua terminal:
   ```bash
   fly auth login
   ```
3. Khởi tạo ứng dụng Fly:
   ```bash
   fly launch
   ```
4. Tạo Volume lưu trữ dữ liệu DB:
   ```bash
   fly volumes create lead_data --size 1
   ```
5. Đẩy ứng dụng lên Fly:
   ```bash
   fly deploy
   ```

---

## Phuong an 4: Trien khai bang Docker Compose tren Linux VPS

Nếu bạn sở hữu máy chủ riêng (Ubuntu/Debian VPS), bạn có thể chạy ứng dụng qua Docker Compose.

### Cac buoc thuc hien:
1. Cài đặt Docker & Docker Compose trên VPS.
2. Clone repository về VPS:
   ```bash
   git clone <URL_REPOSITORY_CUANGBAN>
   cd lead_phone_collector
   ```
3. Chỉnh sửa file `.env` hoặc cấu hình trong `docker-compose.yml`.
4. Khởi chạy ứng dụng dưới dạng daemon:
   ```bash
   docker-compose up -d --build
   ```
5. Kiểm tra log ứng dụng:
   ```bash
   docker-compose logs -f
   ```
6. (Tùy chọn) Cấu hình Nginx reverse proxy với HTTPS (Let's Encrypt Certbot) trỏ về port `5000`.

---

## Cap nhat OAuth Callback URLs sau khi Deploy

Sau khi ứng dụng của bạn có địa chỉ URL công khai (ví dụ: `https://ten-app.onrender.com`), hãy cập nhật Redirect URIs cho Google & Facebook OAuth:

1. **Google Cloud Console**:
   - Authorized redirect URIs: `https://ten-app.onrender.com/auth/google/callback`

2. **Facebook Developers Console**:
   - Valid OAuth Redirect URIs: `https://ten-app.onrender.com/auth/facebook/callback`

3. Cập nhật biến môi trường `APP_BASE_URL=https://ten-app.onrender.com` trên bảng điều khiển của PaaS.
