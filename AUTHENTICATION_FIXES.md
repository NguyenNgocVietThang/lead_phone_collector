# Xác thực Web UI

## Các luồng được hỗ trợ

- Đăng ký và đăng nhập bằng email/mật khẩu.
- Đăng nhập hoặc đăng ký tự động bằng Google OpenID Connect.
- Đăng nhập hoặc đăng ký tự động bằng Facebook OAuth.
- Đăng xuất chỉ xóa session của Lead Phone Collector; không đăng xuất tài khoản Google/Facebook trên trình duyệt và không xóa cookie collector.

Đăng nhập OAuth của Web UI hoàn toàn độc lập với lệnh `python main.py login --service ...`. Lệnh CLI đó chỉ lưu Playwright `storage_state` để collector truy cập dữ liệu mà người dùng đã được phép xem.

## Cấu hình

Sao chép `.env.example` thành `.env` rồi điền:

```dotenv
FLASK_SECRET_KEY=replace-with-a-long-random-secret
APP_BASE_URL=http://localhost:5000
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
FACEBOOK_APP_ID=
FACEBOOK_APP_SECRET=
```

Callback local:

```text
http://localhost:5000/auth/google/callback
http://localhost:5000/auth/facebook/callback
```

Khi triển khai, dùng HTTPS và thay `APP_BASE_URL` bằng origin công khai. Callback đăng ký tại từng nhà cung cấp phải khớp chính xác với URL ứng dụng tạo ra.

Google cần các scope `openid email profile`. Facebook cần `public_profile,email`; tài khoản Facebook không trả email sẽ được yêu cầu dùng tài khoản khác hoặc đăng nhập bằng email.

## Dữ liệu và bảo mật

- Bảng `oauth_identities` lưu provider ID và liên kết về `users`; không lưu access token hoặc refresh token.
- Email do provider trả về được chuẩn hóa chữ thường. Danh tính OAuth mới có cùng email sẽ liên kết với tài khoản hiện có.
- Mật khẩu mới dùng bộ tạo hash của Werkzeug. Hash SHA-256 từ phiên bản cũ được nâng cấp tự động sau lần đăng nhập đúng tiếp theo.
- Các biểu mẫu đăng nhập, đăng ký và đăng xuất kiểm tra CSRF.
- Session chỉ hợp lệ khi chứa `user_id`; kiểu đăng nhập bằng tên không mật khẩu đã bị loại bỏ.

## Kiểm tra nhanh

```powershell
venv\Scripts\python.exe -m pytest -q --basetemp "D:\Tool map fb\data\pytest_tmp" -p no:cacheprovider
python main.py ui
```
