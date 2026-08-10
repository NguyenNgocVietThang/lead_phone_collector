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
import threading
from datetime import datetime

from flask import (
    Flask, render_template, request, jsonify, redirect,
    url_for, send_file, flash,
)

from config.settings import settings
from storage.database import LeadDatabase, Lead
from exporters.excel_export import ExcelExporter
from exporters.csv_export import CsvExporter

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Flask app setup
# ---------------------------------------------------------------------------

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = settings.FLASK_SECRET_KEY

db = LeadDatabase()

# Lưu trạng thái các jobs đang chạy
_active_jobs: dict = {}  # job_id -> {"status": str, "message": str}


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
    keyword = request.form.get("keyword", "").strip()
    area = request.form.get("area", "").strip()
    limit = int(request.form.get("limit", 50))

    if not keyword:
        flash("Vui lòng nhập từ khóa tìm kiếm.", "error")
        return redirect(url_for("index"))

    query = f"{keyword} {area}".strip()
    job_id = db.create_job("google_maps", query)

    # Chạy background thread
    thread = threading.Thread(
        target=_run_maps_job,
        args=(job_id, keyword, area, limit),
        daemon=True,
    )
    thread.start()

    flash(f"Đã bắt đầu thu thập Google Maps: '{query}'. Job ID: {job_id}", "success")
    return redirect(url_for("job_status_page", job_id=job_id))


@app.route("/collect/facebook", methods=["POST"])
def collect_facebook():
    """Trigger Facebook collection job."""
    page_url = request.form.get("page_url", "").strip()
    sources = request.form.getlist("sources") or ["about", "posts", "comments"]
    max_posts = int(request.form.get("max_posts", 30))

    if not page_url:
        flash("Vui lòng nhập URL Facebook page.", "error")
        return redirect(url_for("index"))

    job_id = db.create_job("facebook", page_url)

    thread = threading.Thread(
        target=_run_facebook_job,
        args=(job_id, page_url, sources, max_posts),
        daemon=True,
    )
    thread.start()

    flash(f"Đã bắt đầu thu thập Facebook: {page_url}. Job ID: {job_id}", "success")
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
    """Bảng danh sách leads với filter."""
    source = request.args.get("source", "")
    status = request.args.get("status", "")
    carrier = request.args.get("carrier", "")
    search = request.args.get("search", "")
    page = int(request.args.get("page", 1))
    per_page = 50

    leads = db.get_leads(
        source=source or None,
        status=status or None,
        carrier=carrier or None,
        search=search or None,
        limit=per_page,
        offset=(page - 1) * per_page,
    )

    stats = db.get_stats()
    return render_template(
        "leads.html",
        leads=leads,
        stats=stats,
        filters={"source": source, "status": status, "carrier": carrier, "search": search},
        page=page,
        per_page=per_page,
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
    """Download Excel."""
    source = request.args.get("source")
    status = request.args.get("status")
    leads = db.get_all_for_export(source=source or None, status=status or None)

    if not leads:
        flash("Không có dữ liệu để xuất.", "warning")
        return redirect(url_for("leads_page"))

    exporter = ExcelExporter()
    path = exporter.export(leads)
    return send_file(str(path), as_attachment=True, download_name=path.name)


@app.route("/export/csv")
def export_csv():
    """Download CSV."""
    source = request.args.get("source")
    status = request.args.get("status")
    leads = db.get_all_for_export(source=source or None, status=status or None)

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
        "selenium_headless": settings.SELENIUM_HEADLESS,
        "delay_min": settings.SELENIUM_DELAY_MIN,
        "delay_max": settings.SELENIUM_DELAY_MAX,
    }
    return render_template("settings.html", config=config_info)


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
                source="google_maps",
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


def _run_facebook_job(job_id: int, page_url: str, sources: list, max_posts: int):
    """Chạy Facebook collector trong background thread."""
    from collectors.facebook import FacebookCollector
    from storage.sheets import GoogleSheetsSync

    _active_jobs[job_id] = {"message": "Đang khởi động..."}

    def on_progress(msg: str):
        _active_jobs[job_id]["message"] = msg

    try:
        with FacebookCollector(progress_callback=on_progress) as collector:
            result = collector.collect(page_url, sources, max_posts)

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
