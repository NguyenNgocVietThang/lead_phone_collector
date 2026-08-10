"""
main.py — CLI entry point cho Lead Phone Collector.

Sử dụng:
    python main.py ui                                         # Khởi động Web UI
    python main.py maps --keyword "nhà hàng" --area "HN"    # Google Maps
    python main.py facebook --url "https://fb.com/page"      # Facebook
    python main.py export --format excel                      # Xuất Excel
    python main.py export --format csv                        # Xuất CSV
    python main.py stats                                      # Thống kê
"""

import argparse
import logging
import sys
from pathlib import Path

from config.settings import settings

# Force UTF-8 encoding for Windows terminals
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')  # type: ignore
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')  # type: ignore

# Setup logging ngay khi khởi động
settings.setup_logging()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CLI Handlers
# ---------------------------------------------------------------------------

def cmd_ui(args):
    """Khởi động Flask Web UI."""
    print(f"\n[WEB] Khoi dong Web UI tai http://localhost:{settings.FLASK_PORT}")
    print("   Nhấn Ctrl+C để dừng.\n")
    from ui.app import run_ui
    run_ui()


def cmd_maps(args):
    """Thu thập từ Google Maps."""
    import re
    from collectors.google_maps import GoogleMapsCollector
    from storage.database import LeadDatabase, Lead
    from storage.sheets import GoogleSheetsSync

    keyword = re.sub(r"\s+", " ", args.keyword or "").strip()
    area = re.sub(r"\s+", " ", args.area or "").strip()
    db = LeadDatabase()
    job_id = db.create_job("google_maps", f"{keyword} {area}".strip())

    print(f"\n🗺️  Thu thập Google Maps: '{keyword}' @ '{area}' (limit={args.limit})")
    print("   Vui lòng đợi...\n")

    def on_progress(current, total):
        print(f"   [{current}/{total}] Đang xử lý...", end="\r")

    try:
        with GoogleMapsCollector(headless=not args.show_browser, progress_callback=on_progress) as collector:
            result = collector.search(args.keyword, args.area, args.limit)

        print(f"\n✅ Hoàn thành! Tìm được {result.total_with_phone} SĐT từ {result.total_scraped} địa điểm.")

        if result.errors:
            print(f"⚠️  {len(result.errors)} lỗi xảy ra.")

        # Lưu vào DB
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

        batch = db.insert_leads_batch(leads)
        print(f"💾 Lưu DB: {batch['inserted']} mới, {batch['duplicates']} trùng")

        if batch['inserted'] > 0:
            print("🔄 Đang sync Google Sheets...")
            GoogleSheetsSync().sync_leads(db.get_leads(limit=batch['inserted'] + 5))

        db.finish_job(job_id, result.total_with_phone, batch['inserted'], batch['duplicates'])

        # Print sample results
        if leads:
            print(f"\n{'─'*60}")
            print(f"{'SĐT':<14} {'Tên':<30} {'Nhà mạng':<12}")
            print(f"{'─'*60}")
            for l in leads[:10]:
                print(f"{l.phone_normalized:<14} {(l.name or '')[:28]:<30} {l.carrier or '?':<12}")
            if len(leads) > 10:
                print(f"... và {len(leads) - 10} leads khác.")
            print(f"{'─'*60}")

        if args.export:
            _auto_export(db, args.export)

    except KeyboardInterrupt:
        print("\n\n⛔ Đã dừng bởi người dùng.")
        db.fail_job(job_id, "Interrupted by user")
    except Exception as e:
        logger.error("Lỗi Maps: %s", e, exc_info=True)
        db.fail_job(job_id, str(e))
        print(f"\n❌ Lỗi: {e}")
        sys.exit(1)


def cmd_facebook(args):
    """Thu thập từ Facebook (Page, Group, hoặc Tìm kiếm từ khóa)."""
    from collectors.facebook import FacebookCollector
    from storage.database import LeadDatabase, Lead
    from storage.sheets import GoogleSheetsSync

    target_type = getattr(args, "mode", "auto") or "auto"
    target = getattr(args, "target", None) or getattr(args, "url", "")

    db = LeadDatabase()
    job_id = db.create_job("facebook", f"[{target_type}] {target}")
    sources = args.sources.split(",") if args.sources else ["about", "posts", "comments"]

    print(f"\n📘 Thu thập Facebook [{target_type}]: {target}")
    print(f"   Nguồn: {', '.join(sources)} | Max posts: {args.max_posts}\n")

    def on_progress(msg: str):
        print(f"   → {msg}")

    try:
        with FacebookCollector(headless=not args.show_browser, progress_callback=on_progress) as collector:
            result = collector.collect(target=target, target_type=target_type, sources=sources, max_posts=args.max_posts)

        print(f"\n✅ Hoàn thành! Tìm được {result.total_found} SĐT.")

        leads = []
        for r in result.results:
            leads.append(Lead(
                name=r.page_name,
                phone_raw=r.phone_raw,
                phone_normalized=r.phone_normalized,
                source=r.source,
                source_url=r.source_url,
                content=r.content,
                carrier=r.carrier,
            ))

        batch = db.insert_leads_batch(leads)
        print(f"💾 Lưu DB: {batch['inserted']} mới, {batch['duplicates']} trùng")

        if batch['inserted'] > 0:
            GoogleSheetsSync().sync_leads(db.get_leads(limit=batch['inserted'] + 5))

        db.finish_job(job_id, result.total_found, batch['inserted'], batch['duplicates'])

        if args.export:
            _auto_export(db, args.export)

    except KeyboardInterrupt:
        print("\n\n⛔ Đã dừng bởi người dùng.")
        db.fail_job(job_id, "Interrupted by user")
    except Exception as e:
        logger.error("Lỗi Facebook: %s", e, exc_info=True)
        db.fail_job(job_id, str(e))
        print(f"\n❌ Lỗi: {e}")
        sys.exit(1)


def cmd_login(args):
    """Đăng nhập tương tác để lưu session cookies."""
    from storage.auth import AuthManager
    service = getattr(args, "service", "facebook") or "facebook"
    print(f"\n🔑 Khởi động trình duyệt đăng nhập tương tác cho {service.upper()}...")
    print("Vui lòng thực hiện đăng nhập trên cửa sổ trình duyệt vừa mở...\n")
    success = AuthManager.launch_interactive_login(service=service)
    if success:
        print(f"\n✅ Đã lưu thành công phiên đăng nhập {service.upper()}!")
    else:
        print(f"\n❌ Không lưu được phiên đăng nhập {service.upper()}.")


def cmd_export(args):
    """Xuất dữ liệu ra file."""
    from storage.database import LeadDatabase
    from exporters.excel_export import ExcelExporter
    from exporters.csv_export import CsvExporter

    db = LeadDatabase()
    leads = db.get_all_for_export(
        source=args.source or None,
        status=args.status or None,
    )

    if not leads:
        print("⚠️  Không có dữ liệu để xuất.")
        return

    output = Path(args.output) if args.output else None

    if args.format == "excel":
        path = ExcelExporter().export(leads, output)
        print(f"✅ Đã xuất {len(leads)} leads → {path}")
    elif args.format == "csv":
        path = CsvExporter().export(leads, output)
        print(f"✅ Đã xuất {len(leads)} leads → {path}")
    else:
        print(f"❌ Format không hợp lệ: {args.format}. Chọn: excel, csv")
        sys.exit(1)


def cmd_stats(args):
    """Hiển thị thống kê."""
    from storage.database import LeadDatabase

    db = LeadDatabase()
    stats = db.get_stats()

    print(f"\n{'━'*40}")
    print("  📊 Thống kê Lead Phone Collector")
    print(f"{'━'*40}")
    print(f"  Tổng leads:   {stats['total']:>8,}")
    print(f"  Hôm nay:      {stats['today']:>8,}")
    print("\n  Theo nguồn:")
    for src, cnt in stats['by_source'].items():
        print(f"    {src:<30} {cnt:>6,}")
    print("\n  Theo nhà mạng:")
    for carrier, cnt in stats['by_carrier'].items():
        print(f"    {carrier:<30} {cnt:>6,}")
    print("\n  Theo trạng thái:")
    for status, cnt in stats['by_status'].items():
        print(f"    {status:<30} {cnt:>6,}")
    print(f"{'━'*40}\n")


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _auto_export(db, fmt: str):
    from exporters.excel_export import ExcelExporter
    from exporters.csv_export import CsvExporter
    leads = db.get_all_for_export()
    if fmt == "excel":
        path = ExcelExporter().export(leads)
    else:
        path = CsvExporter().export(leads)
    print(f"📥 Đã tự động xuất → {path}")


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="Lead Phone Collector — Thu thập SĐT từ Google Maps & Facebook",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ví dụ:
  python main.py ui
  python main.py maps --keyword "quán cà phê" --area "Hà Nội" --limit 50
  python main.py facebook --url "https://facebook.com/tenpagecuaban"
  python main.py export --format excel
  python main.py stats
        """,
    )

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    # ui
    sub.add_parser("ui", help="Khởi động Web UI (Flask)")

    # maps
    p_maps = sub.add_parser("maps", help="Thu thập từ Google Maps")
    p_maps.add_argument("-k", "--keyword", required=True, help="Từ khóa tìm kiếm")
    p_maps.add_argument("-a", "--area", default="", help="Khu vực (VD: Hà Nội)")
    p_maps.add_argument("-l", "--limit", type=int, default=50, help="Số lượng tối đa")
    p_maps.add_argument("--show-browser", action="store_true", help="Hiện browser (không headless)")
    p_maps.add_argument("--export", choices=["excel", "csv"], help="Tự động xuất sau khi thu thập")

    # facebook
    p_fb = sub.add_parser("facebook", help="Thu thập từ Facebook Page, Group hoặc Từ khóa tìm kiếm")
    p_fb.add_argument("-m", "--mode", choices=["page", "group", "search", "auto"], default="auto",
                      help="Loại mục tiêu (page, group, search, auto)")
    p_fb.add_argument("--url", "-t", "--target", dest="target", required=True,
                      help="URL Facebook Page/Group hoặc Từ khóa tìm kiếm")
    p_fb.add_argument("--sources", default="about,posts,comments",
                      help="Nguồn (mặc định: about,posts,comments)")
    p_fb.add_argument("--max-posts", type=int, default=30, help="Số posts tối đa")
    p_fb.add_argument("--show-browser", action="store_true", help="Hiện browser")
    p_fb.add_argument("--export", choices=["excel", "csv"], help="Tự động xuất")

    # login
    p_login = sub.add_parser("login", help="Đăng nhập tương tác để lưu phiên làm việc (Facebook / Google)")
    p_login.add_argument("-s", "--service", choices=["facebook", "google"], default="facebook",
                         help="Dịch vụ đăng nhập (facebook hoặc google)")

    # export
    p_exp = sub.add_parser("export", help="Xuất dữ liệu ra file")
    p_exp.add_argument("-f", "--format", choices=["excel", "csv"], default="excel")
    p_exp.add_argument("-o", "--output", help="Đường dẫn file output")
    p_exp.add_argument("--source", help="Lọc theo nguồn")
    p_exp.add_argument("--status", help="Lọc theo trạng thái")

    # stats
    sub.add_parser("stats", help="Hiển thị thống kê")

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = build_parser()
    args = parser.parse_args()

    handlers = {
        "ui": cmd_ui,
        "maps": cmd_maps,
        "facebook": cmd_facebook,
        "login": cmd_login,
        "export": cmd_export,
        "stats": cmd_stats,
    }
    handlers[args.command](args)
