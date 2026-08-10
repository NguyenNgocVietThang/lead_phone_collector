"""
ui/app.py — Flask Web UI cho Lead Phone Collector.

Routes:
  GET  /                    Dashboard + thống kê
  POST /collect/maps        Trigger Google Maps job
  POST /collect/facebook    Trigger Facebook job
  GET  /leads               Bảng leads với filter
  POST /api/leads/<id>/status  Cập nhật status
  GET  /api/job-status/<id>    Kiểm tra tiến độ job
  GET  /export/excel        Download Excel
  GET  /export/csv          Download CSV
  GET  /settings            Trang cấu hình
"""

import logging
import re
import threading
from datetime import datetime

from flask import (
    Flask, render_template, request, jsonify, redirect,
    url_for, send_file, flash, session,
)

from config.settings import settings
from storage.database import LeadDatabase, Lead
from processors.source_helper import get_source_info
from exporters.excel_export import ExcelExporter
from exporters.csv_export import CsvExporter

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Flask app setup
# ---------------------------------------------------------------------------

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = settings.FLASK_SECRET_KEY
app.jinja_env.filters["source_info"] = get_source_info

db = LeadDatabase()

# Lưu trạng thái các jobs đang chạy
_active_jobs: dict = {}  # job_id -> {"status": str, "message": str}

EXEMPT_ENDPOINTS = {"login", "login_social", "logout", "static"}


@app.before_request
def check_authentication():
    """Kiểm tra bắt buộc đăng nhập trước khi truy cập bất kỳ trang nào."""
    if request.endpoint and request.endpoint not in EXEMPT_ENDPOINTS:
        if not session.get("user_identity"):
            return redirect(url_for("login", next=request.url))


# ---------------------------------------------------------------------------
# Routes — Authentication
# ---------------------------------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    """Trang đăng nhập."""
    if request.method == "POST":
        identity = request.form.get("user_identity", "").strip()
        if not identity:
            flash("Vui lòng nhập tên hoặc email đăng nhập.", "error")
            return render_template("login.html")
        session["user_identity"] = identity
        session["auth_provider"] = "direct"
        flash(f"Đăng nhập thành công với tên: {identity}", "success")
        next_url = request.args.get("next") or url_for("index")
        return redirect(next_url)

    if session.get("user_identity"):
        return redirect(url_for("index"))
    return render_template("login.html")


@app.route("/login/social/<provider>", methods=["GET", "POST"])
def login_social(provider: str):
    """Đăng nhập bằng tài khoản Facebook hoặc Google đã lưu phiên hoặc mở trình duyệt tương tác."""
    from storage.auth import AuthManager
    provider = provider.lower().strip()

    # Nếu chưa có phiên đăng nhập đã lưu, tự động mở trình duyệt tương tác để người dùng đăng nhập
    if not AuthManager.is_logged_in(provider):
        flash(f"Chưa có phiên làm việc {provider.upper()}. Đang mở trình duyệt để bạn đăng nhập...", "info")
        AuthManager.launch_interactive_login(provider, timeout_seconds=120)

    user_info = AuthManager.get_user_info(provider)
    if user_info.get("logged_in"):
        name = user_info.get("name", f"Tài khoản {provider.title()}")
        session["user_identity"] = name
        session["auth_provider"] = provider
        flash(f"Đã kết nối thành công tài khoản {provider.upper()}: {name}", "success")
    else:
        name = f"Tài khoản {provider.title()}"
        session["user_identity"] = name
        session["auth_provider"] = provider
        flash(f"Đã tạo phiên làm việc mặc định cho {provider.upper()}.", "warning")

    next_url = request.args.get("next") or url_for("index")
    return redirect(next_url)


@app.route("/logout", methods=["POST"])
def logout():
    """Đăng xuất tài khoản."""
    session.clear()
    flash("Đã đăng xuất khỏi hệ thống.", "info")
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# Routes — Dashboard
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    """Dashboard chính."""
    stats = db.get_stats()
    recent_leads = db.get_leads(limit=10)
    recent_jobs = db.get_jobs(limit=5)
    return render_template(
        "index.html",
        stats=stats,
        recent_leads=recent_leads,
        recent_jobs=recent_jobs,
        now=datetime.now(),
    )


# ---------------------------------------------------------------------------
# Routes — Collection
# ---------------------------------------------------------------------------

@app.route("/collect/maps", methods=["POST"])
def collect_maps():
    """Trigger Google Maps collection job."""
    keyword = re.sub(r"\s+", " ", request.form.get("keyword", "")).strip()
    area = re.sub(r"\s+", " ", request.form.get("area", "")).strip()
    limit = int(request.form.get("limit", 50))
    collector_user = session.get("user_identity", "Admin")

    if not keyword:
        flash("Vui lòng nhập từ khóa tìm kiếm.", "error")
        return redirect(url_for("index"))

    query = re.sub(r"\s+", " ", f"{keyword} {area}").strip()
    job_id = db.create_job("google_maps", query, collector_user=collector_user)

    # Chạy background thread
    thread = threading.Thread(
        target=_run_maps_job,
        args=(job_id, keyword, area, limit, collector_user),
        daemon=True,
    )
    thread.start()

    flash(f"Đã bắt đầu thu thập Google Maps: '{query}'. Job ID: {job_id}", "success")
    return redirect(url_for("job_status_page", job_id=job_id))


@app.route("/collect/facebook", methods=["POST"])
def collect_facebook():
    """Trigger Facebook collection job (Page, Profile cá nhân, Group, hoặc Từ khóa search)."""
    target_type = request.form.get("target_type", "auto").strip()
    target_value = request.form.get("target_value", "").strip() or request.form.get("page_url", "").strip()
    sources = request.form.getlist("sources") or ["about", "posts", "comments", "likers"]
    max_posts = int(request.form.get("max_posts", 30))
    collector_user = session.get("user_identity", "Admin")

    if not target_value:
        flash("Vui lòng nhập URL Facebook hoặc từ khóa tìm kiếm.", "error")
        return redirect(url_for("index"))

    job_id = db.create_job("facebook", f"[{target_type}] {target_value}", collector_user=collector_user)

    thread = threading.Thread(
        target=_run_facebook_job,
        args=(job_id, target_value, target_type, sources, max_posts, collector_user),
        daemon=True,
    )
    thread.start()

    flash(f"Đã bắt đầu thu thập Facebook [{target_type}]: '{target_value}'. Job ID: {job_id}", "success")
    return redirect(url_for("job_status_page", job_id=job_id))


@app.route("/job/<int:job_id>")
def job_status_page(job_id: int):
    """Trang theo dõi tiến độ job."""
    job = db.get_job(job_id)
    if not job:
        flash("Không tìm thấy job.", "error")
        return redirect(url_for("index"))
    return render_template("job_status.html", job=job)


# ---------------------------------------------------------------------------
# Routes — Leads
# ---------------------------------------------------------------------------

@app.route("/leads")
def leads_page():
    """Bảng danh sách leads với filter và tìm kiếm linh hoạt (gần đúng / trùng 1 phần / chính xác)."""
    source = request.args.get("source", "")
    status = request.args.get("status", "")
    carrier = request.args.get("carrier", "")
    collector_user = request.args.get("collector_user", "")
    search = request.args.get("search", "")
    search_mode = request.args.get("search_mode", "fuzzy")
    page = int(request.args.get("page", 1))
    per_page = 50

    total_leads = db.count_leads(
        source=source or None,
        status=status or None,
        carrier=carrier or None,
        collector_user=collector_user or None,
        search=search or None,
        search_mode=search_mode,
    )

    leads = db.get_leads(
        source=source or None,
        status=status or None,
        carrier=carrier or None,
        collector_user=collector_user or None,
        search=search or None,
        search_mode=search_mode,
        limit=per_page,
        offset=(page - 1) * per_page,
    )

    distinct_collectors = db.get_distinct_collectors()
    total_pages = max(1, (total_leads + per_page - 1) // per_page)

    stats = db.get_stats()
    return render_template(
        "leads.html",
        leads=leads,
        stats=stats,
        distinct_collectors=distinct_collectors,
        filters={
            "source": source,
            "status": status,
            "carrier": carrier,
            "collector_user": collector_user,
            "search": search,
            "search_mode": search_mode,
        },
        page=page,
        per_page=per_page,
        total_leads=total_leads,
        total_pages=total_pages,
    )


# ---------------------------------------------------------------------------
# Routes — API
# ---------------------------------------------------------------------------

@app.route("/api/leads/<int:lead_id>/status", methods=["POST"])
def update_lead_status(lead_id: int):
    """Cập nhật trạng thái lead."""
    data = request.get_json() or {}
    new_status = data.get("status", "")
    notes = data.get("notes", "")

    valid_statuses = ["new", "contacted", "qualified", "rejected"]
    if new_status not in valid_statuses:
        return jsonify({"ok": False, "error": "Status không hợp lệ"}), 400

    success = db.update_lead_status(lead_id, new_status, notes)
    return jsonify({"ok": success})


@app.route("/api/job-status/<int:job_id>")
def api_job_status(job_id: int):
    """Kiểm tra trạng thái job (polling từ frontend)."""
    job = db.get_job(job_id)
    if not job:
        return jsonify({"error": "Không tìm thấy job"}), 404

    active = _active_jobs.get(job_id, {})
    return jsonify({
        **job,
        "live_message": active.get("message", ""),
    })


@app.route("/api/stats")
def api_stats():
    """Trả về thống kê dạng JSON."""
    return jsonify(db.get_stats())


# ---------------------------------------------------------------------------
# Routes — Export
# ---------------------------------------------------------------------------

@app.route("/export/excel")
def export_excel():
    """Download Excel với filter và tìm kiếm."""
    source = request.args.get("source")
    status = request.args.get("status")
    carrier = request.args.get("carrier")
    collector_user = request.args.get("collector_user")
    search = request.args.get("search")
    search_mode = request.args.get("search_mode", "fuzzy")

    leads = db.get_all_for_export(
        source=source or None,
        status=status or None,
        carrier=carrier or None,
        collector_user=collector_user or None,
        search=search or None,
        search_mode=search_mode,
    )

    if not leads:
        flash("Không có dữ liệu để xuất.", "warning")
        return redirect(url_for("leads_page"))

    exporter = ExcelExporter()
    path = exporter.export(leads)
    return send_file(str(path), as_attachment=True, download_name=path.name)


@app.route("/export/csv")
def export_csv():
    """Download CSV với filter và tìm kiếm."""
    source = request.args.get("source")
    status = request.args.get("status")
    carrier = request.args.get("carrier")
    collector_user = request.args.get("collector_user")
    search = request.args.get("search")
    search_mode = request.args.get("search_mode", "fuzzy")

    leads = db.get_all_for_export(
        source=source or None,
        status=status or None,
        carrier=carrier or None,
        collector_user=collector_user or None,
        search=search or None,
        search_mode=search_mode,
    )

    if not leads:
        flash("Không có dữ liệu để xuất.", "warning")
        return redirect(url_for("leads_page"))

    exporter = CsvExporter()
    path = exporter.export(leads)
    return send_file(str(path), as_attachment=True, download_name=path.name)


# ---------------------------------------------------------------------------
# Routes — Settings
# ---------------------------------------------------------------------------

@app.route("/settings")
def settings_page():
    """Trang cấu hình."""
    config_info = {
        "google_sheet_id": settings.GOOGLE_SHEET_ID,
        "google_sheet_name": settings.GOOGLE_SHEET_NAME,
        "sheets_configured": bool(settings.GOOGLE_SHEET_ID),
        "facebook_token_configured": bool(settings.FACEBOOK_ACCESS_TOKEN),
        "is_fb_logged_in": settings.is_fb_logged_in,
        "is_google_logged_in": settings.is_google_logged_in,
        "playwright_headless": settings.PLAYWRIGHT_HEADLESS,
        "selenium_headless": settings.PLAYWRIGHT_HEADLESS,
        "delay_min": settings.PLAYWRIGHT_DELAY_MIN,
        "delay_max": settings.PLAYWRIGHT_DELAY_MAX,
    }
    return render_template("settings.html", config=config_info)


# ---------------------------------------------------------------------------
# Routes — Authentication & Session Management
# ---------------------------------------------------------------------------

@app.route("/auth/login/<service>", methods=["POST"])
def auth_login(service: str):
    """Mở trình duyệt đăng nhập tương tác cho Facebook hoặc Google."""
    from storage.auth import AuthManager

    def run_login():
        AuthManager.launch_interactive_login(service=service)

    thread = threading.Thread(target=run_login, daemon=True)
    thread.start()
    flash(f"Đã mở cửa sổ trình duyệt đăng nhập {service.upper()}. Vui lòng hoàn tất đăng nhập trên màn hình!", "info")
    return redirect(url_for("settings_page"))


@app.route("/auth/logout/<service>", methods=["POST"])
def auth_logout(service: str):
    """Xóa phiên đăng nhập."""
    from storage.auth import AuthManager
    if AuthManager.clear_session(service):
        flash(f"Đã xóa phiên đăng nhập {service.upper()}.", "success")
    else:
        flash(f"Không có phiên đăng nhập {service.upper()} nào để xóa.", "warning")
    return redirect(url_for("settings_page"))


@app.route("/auth/save-json/<service>", methods=["POST"])
def auth_save_json(service: str):
    """Lưu thủ công mảng storage_state JSON."""
    from storage.auth import AuthManager
    json_str = request.form.get("cookie_json", "").strip()
    if not json_str:
        flash("Vui lòng dán nội dung JSON phiên làm việc.", "error")
    elif AuthManager.save_cookie_json(service, json_str):
        flash(f"Đã lưu thành công phiên làm việc JSON cho {service.upper()}!", "success")
    else:
        flash("Định dạng JSON không hợp lệ.", "error")
    return redirect(url_for("settings_page"))


@app.route("/auth/status")
def auth_status():
    """Trả về JSON trạng thái đăng nhập."""
    return jsonify({
        "facebook": settings.is_fb_logged_in,
        "google": settings.is_google_logged_in,
    })


# ---------------------------------------------------------------------------
# Background job runners
# ---------------------------------------------------------------------------

def _run_maps_job(job_id: int, keyword: str, area: str, limit: int):
    """Chạy Google Maps collector trong background thread."""
    from collectors.google_maps import GoogleMapsCollector
    from storage.sheets import GoogleSheetsSync

    _active_jobs[job_id] = {"message": "Đang khởi động trình duyệt..."}

    def on_progress(current, total):
        _active_jobs[job_id]["message"] = f"Đang xử lý {current}/{total} địa điểm..."

    try:
        with GoogleMapsCollector(progress_callback=on_progress) as collector:
            _active_jobs[job_id]["message"] = "Đang tìm kiếm trên Google Maps..."
            result = collector.search(keyword, area, limit)

        _active_jobs[job_id]["message"] = "Đang lưu vào database..."

        leads = []
        for biz in result.businesses:
            if not biz.phone_normalized:
                continue
            leads.append(Lead(
                name=biz.name,
                phone_raw=biz.phone_raw,
                phone_normalized=biz.phone_normalized,
                source=getattr(biz, "source", "google_maps_details") or "google_maps_details",
                source_url=biz.maps_url,
                content=f"Google Maps: {biz.name}",
                address=biz.address,
                website=biz.website,
                carrier=biz.carrier,
            ))

        batch_result = db.insert_leads_batch(leads)

        # Sync Google Sheets
        if batch_result["inserted"] > 0:
            _active_jobs[job_id]["message"] = "Đang sync lên Google Sheets..."
            all_new = db.get_leads(source="google_maps", limit=batch_result["inserted"] * 2)
            GoogleSheetsSync().sync_leads(all_new[:batch_result["inserted"]])

        db.finish_job(
            job_id,
            total_found=result.total_with_phone,
            new_leads=batch_result["inserted"],
            duplicates=batch_result["duplicates"],
        )
        _active_jobs[job_id]["message"] = "Hoàn thành!"

    except Exception as e:
        logger.error("Lỗi Maps job %d: %s", job_id, e, exc_info=True)
        db.fail_job(job_id, str(e))
        _active_jobs[job_id]["message"] = f"Lỗi: {e}"
    finally:
        # Dọn dẹp sau 5 phút
        threading.Timer(300, lambda: _active_jobs.pop(job_id, None)).start()


def _run_facebook_job(job_id: int, target: str, target_type: str, sources: list, max_posts: int, collector_user: str = ""):
    """Chạy Facebook collector trong background thread (hỗ trợ page, group, search)."""
    from collectors.facebook import FacebookCollector
    from storage.sheets import GoogleSheetsSync

    _active_jobs[job_id] = {"message": "Đang khởi động..."}

    def on_progress(msg: str):
        _active_jobs[job_id]["message"] = msg

    try:
        with FacebookCollector(progress_callback=on_progress) as collector:
            result = collector.collect(target=target, target_type=target_type, sources=sources, max_posts=max_posts)

        leads = []
        for fb_result in result.results:
            leads.append(Lead(
                name=fb_result.page_name,
                phone_raw=fb_result.phone_raw,
                phone_normalized=fb_result.phone_normalized,
                source=fb_result.source,
                source_url=fb_result.source_url,
                content=fb_result.content,
                carrier=fb_result.carrier,
                collector_user=collector_user or "",
            ))

        batch_result = db.insert_leads_batch(leads)

        if batch_result["inserted"] > 0:
            _active_jobs[job_id]["message"] = "Đang sync lên Google Sheets..."
            new_leads = db.get_leads(limit=batch_result["inserted"] + 10)
            GoogleSheetsSync().sync_leads(new_leads[:batch_result["inserted"]])

        db.finish_job(
            job_id,
            total_found=result.total_found,
            new_leads=batch_result["inserted"],
            duplicates=batch_result["duplicates"],
        )
        _active_jobs[job_id]["message"] = "Hoàn thành!"

    except Exception as e:
        logger.error("Lỗi Facebook job %d: %s", job_id, e, exc_info=True)
        db.fail_job(job_id, str(e))
        _active_jobs[job_id]["message"] = f"Lỗi: {e}"
    finally:
        threading.Timer(300, lambda: _active_jobs.pop(job_id, None)).start()


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

def run_ui():
    """Khởi động Flask server."""
    settings.setup_logging()
    logger.info("Khởi động Web UI tại http://localhost:%d", settings.FLASK_PORT)
    app.run(
        host="0.0.0.0",
        port=settings.FLASK_PORT,
        debug=settings.FLASK_DEBUG,
        use_reloader=False,
    )
