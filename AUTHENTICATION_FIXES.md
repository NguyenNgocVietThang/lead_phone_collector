# Xác thực & Bảo mật Web UI (Lead Phone Collector)

Tài liệu chi tiết về cơ chế xác thực tài khoản người dùng, đăng nhập OAuth 2.0 và quản lý phiên làm việc trong Web UI của **Lead Phone Collector**.

---

## Các luồng xác thực được hỗ trợ

1. **Email / Mật khẩu (Native Auth)**:
   - Cho phép người dùng mới đăng ký tài khoản trực tiếp qua Form Web UI.
   - Mật khẩu được mã hóa an toàn bằng bộ hash của Werkzeug (`pbkdf2:sha256`).
   - Tự động nâng cấp hash mật khẩu SHA-256 từ các phiên bản cũ sau khi đăng nhập thành công.

2. **Google OAuth 2.0 / OpenID Connect**:
   - Đăng nhập hoặc đăng ký tự động chỉ với 1-click qua tài khoản Google.
   - Yêu cầu các scope tiêu chuẩn: `openid`, `email`, `profile`.
   - Tự động liên kết danh tính Google OAuth với tài khoản hiện có nếu trùng khớp địa chỉ Email (email được chuẩn hóa chữ thường).

3. **Facebook OAuth**:
   - Đăng nhập hoặc đăng ký tự động bằng tài khoản Facebook.
   - Yêu cầu scope: `public_profile`, `email`.
   - Trong trường hợp tài khoản Facebook không chia sẻ email, ứng dụng sẽ thông báo người dùng đăng nhập bằng Email hoặc tài khoản OAuth khác.

4. **Đăng xuất an toàn (Logout)**:
   - Thao tác đăng xuất chỉ xóa Session của ứng dụng Lead Phone Collector trong Flask.
   - Không đăng xuất tài khoản Google/Facebook cá nhân trên trình duyệt.
   - Không làm ảnh hưởng hay xóa các file Cookies collector (`data/cookies/fb_cookies.json`).

---

## Phân biệt Web UI Auth & Collector Auth Sessions

> **Khái niệm quan trọng**:
> - **Web UI Auth**: Dùng để quản lý người dùng truy cập Dashboard, xem báo cáo, kích hoạt các job scraping trên giao diện web (`users` & `oauth_identities` table).
> - **Collector Auth Sessions**: Dùng cho trình duyệt tự động Playwright để thu thập dữ liệu Facebook Groups / Search dưới danh nghĩa session Facebook được lưu qua lệnh `python main.py login --service facebook` (`data/cookies/fb_cookies.json`).
>
> Hai luồng này hoàn toàn độc lập với nhau.

---

## Cấu hình Môi trường (`.env`)

Để kích hoạt tính năng Đăng nhập Web UI & OAuth, cấu hình trong file `.env`:

```dotenv
# Key bí mật mã hóa Flask Session & CSRF
FLASK_SECRET_KEY=replace-with-a-long-random-secret-key

# URL gốc của ứng dụng
APP_BASE_URL=http://localhost:5000

# Google OAuth Credentials
GOOGLE_CLIENT_ID=your-google-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-google-client-secret

# Facebook OAuth Credentials
FACEBOOK_APP_ID=your-facebook-app-id
FACEBOOK_APP_SECRET=your-facebook-app-secret
```

### URL Callbacks đăng ký tại OAuth Provider

- **Local Development**:
  ```text
  http://localhost:5000/auth/google/callback
  http://localhost:5000/auth/facebook/callback
  ```

- **Production Deployment**:
  Thao tác trên Production cần đặt `APP_BASE_URL=https://your-domain.com` và đăng ký callback matching exact URI:
  ```text
  https://your-domain.com/auth/google/callback
  https://your-domain.com/auth/facebook/callback
  ```

---

## Cấu trúc Cơ sở Dữ liệu Xác thực (`storage/database.py`)

### 1. Bảng `users`
Lưu trữ thông tin tài khoản người dùng chính.

```sql
CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name       TEXT NOT NULL,
    email           TEXT UNIQUE NOT NULL,
    password_hash   TEXT,
    auth_provider   TEXT DEFAULT 'email',
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_login      DATETIME
);
```

### 2. Bảng `oauth_identities`
Lưu trữ các liên kết OAuth Provider (Google, Facebook) về tài khoản người dùng tương ứng.

```sql
CREATE TABLE IF NOT EXISTS oauth_identities (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             INTEGER NOT NULL,
    provider            TEXT NOT NULL,
    provider_subject    TEXT NOT NULL,
    provider_email      TEXT NOT NULL,
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_login          DATETIME,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(provider, provider_subject)
);
```

---

## Các biện pháp bảo mật đã áp dụng

- **Chuẩn hóa Email**: Email luôn được chuyển về dạng chữ thường (`strip().lower()`) trước khi tra cứu hoặc tạo mới tài khoản.
- **Bảo vệ CSRF**: Tất cả biểu mẫu HTML (Đăng nhập, Đăng ký, Đăng xuất) đều kiểm tra CSRF token hợp lệ.
- **Session Validation**: Tất cả các route yêu cầu đăng nhập phải xác thực `user_id` hợp lệ trong Session. Đã loại bỏ hoàn toàn cơ chế đăng nhập theo Username không mật khẩu.
- **OAuth State Token Verification**: Kiểm tra tham số `state` chống các cuộc tấn công CSRF / Replay Attack trong quá trình trao đổi OAuth callback code.

---

## Kiểm thử nhanh tính năng Xác thực

Chạy suite kiểm thử tự động với `pytest`:

```powershell
# Chạy suite kiểm thử authentication
venv\Scripts\python.exe -m pytest tests/test_auth.py -v
```
