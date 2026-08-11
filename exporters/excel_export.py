"""
exporters/excel_export.py — Xuất leads ra file Excel (.xlsx).

Format đẹp: header màu, auto-width cột, sheet thống kê riêng.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import openpyxl
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from config.settings import settings
from storage.database import Lead
from processors.source_helper import format_source_label

logger = logging.getLogger(__name__)

# Màu sắc header
_HEADER_FILL_COLOR = "1A73E8"    # Xanh Google
_HEADER_FONT_COLOR = "FFFFFF"    # Trắng

# Màu xen kẽ dòng
_ROW_EVEN_COLOR = "F8F9FA"
_ROW_ODD_COLOR = "FFFFFF"

# Màu theo status
_STATUS_COLORS = {
    "new": "E8F5E9",       # Xanh lá nhạt
    "contacted": "FFF3E0",  # Cam nhạt
    "qualified": "E3F2FD", # Xanh dương nhạt
    "rejected": "FFEBEE",  # Đỏ nhạt
}

# Cột và độ rộng
_COLUMNS = [
    ("ID", 6),
    ("Tên", 30),
    ("Số điện thoại", 16),
    ("Nguồn", 22),
    ("Người tìm kiếm", 24),
    ("URL nguồn", 45),
    ("Địa chỉ", 40),
    ("Website", 35),
    ("Nội dung chứa SĐT", 60),
    ("Trạng thái", 14),
    ("Ngày thu thập", 20),
]


class ExcelExporter:
    """
    Xuất leads ra file Excel với format chuyên nghiệp.

    Sử dụng:
        exporter = ExcelExporter()
        path = exporter.export(leads)
        print(f"Đã xuất: {path}")
    """

    def export(
        self,
        leads: List[Lead],
        output_path: Optional[Path] = None,
        filename_prefix: str = "leads",
    ) -> Path:
        """
        Xuất danh sách leads ra Excel.

        Args:
            leads: Danh sách Lead cần xuất.
            output_path: Đường dẫn file output. None = tự tạo trong data/exports/.
            filename_prefix: Tiền tố tên file.

        Returns:
            Path đến file Excel đã tạo.
        """
        try:
            from openpyxl import Workbook
        except ImportError:
            raise ImportError("Cần cài openpyxl: pip install openpyxl")

        if output_path is None:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            settings.EXPORT_DIR.mkdir(parents=True, exist_ok=True)
            output_path = settings.EXPORT_DIR / f"{filename_prefix}_{ts}.xlsx"

        wb = Workbook()

        # Sheet 1: Dữ liệu leads
        ws = wb.active
        assert ws is not None
        ws.title = "Leads"
        self._write_leads_sheet(ws, leads)

        # Sheet 2: Thống kê
        ws_stats = wb.create_sheet("Thống kê")
        self._write_stats_sheet(ws_stats, leads)

        wb.save(str(output_path))
        logger.info("Đã xuất %d leads ra: %s", len(leads), output_path)
        return output_path

    # ── Private ─────────────────────────────────────────────────────────────

    def _write_leads_sheet(self, ws, leads: List[Lead]):
        # Header
        header_fill = PatternFill(fill_type="solid", fgColor=_HEADER_FILL_COLOR)  # type: ignore
        header_font = Font(bold=True, color=_HEADER_FONT_COLOR, size=11)
        center_align = Alignment(horizontal="center", vertical="center", wrap_text=False)

        thin_border = Border(
            bottom=Side(style="thin", color="DDDDDD"),
        )

        for col_idx, (header, width) in enumerate(_COLUMNS, start=1):
            cell = ws.cell(row=1, column=col_idx, value=header)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = center_align
            ws.column_dimensions[get_column_letter(col_idx)].width = width

        ws.row_dimensions[1].height = 22
        ws.freeze_panes = "A2"  # Đóng băng header

        # Dữ liệu
        for row_idx, lead in enumerate(leads, start=2):
            row_data = [
                lead.id,
                lead.name or "",
                lead.phone_normalized or "",
                format_source_label(lead.source or ""),
                lead.collector_user or "",
                lead.source_url or "",
                lead.address or "",
                lead.website or "",
                (lead.content or "")[:300],
                lead.status or "new",
                lead.collected_at or "",
            ]

            # Màu nền theo status
            status_color = _STATUS_COLORS.get(lead.status, _ROW_ODD_COLOR)
            row_fill = PatternFill(fill_type="solid", fgColor=status_color)  # type: ignore

            for col_idx, value in enumerate(row_data, start=1):
                cell = ws.cell(row=row_idx, column=col_idx, value=value)
                cell.fill = row_fill
                cell.border = thin_border
                cell.alignment = Alignment(vertical="center", wrap_text=False)

            ws.row_dimensions[row_idx].height = 18

        # Auto-filter
        if leads:
            ws.auto_filter.ref = f"A1:{get_column_letter(len(_COLUMNS))}{len(leads) + 1}"

    def _write_stats_sheet(self, ws, leads: List[Lead]):
        header_fill = PatternFill(fill_type="solid", fgColor=_HEADER_FILL_COLOR)  # type: ignore

        ws.column_dimensions["A"].width = 20
        ws.column_dimensions["B"].width = 15

        # Tổng quan
        c_title = ws.cell(1, 1, "Thống kê tổng quan")
        c_title.font = Font(bold=True, size=13)
        ws.cell(2, 1, "Tổng leads")
        ws.cell(2, 2, len(leads))
        ws.cell(3, 1, "Ngày xuất")
        ws.cell(3, 2, datetime.now().strftime("%d/%m/%Y %H:%M"))

        # Theo nguồn
        c_src_hdr = ws.cell(5, 1, "Theo nguồn")
        c_src_hdr.font = Font(bold=True)
        c_src_hdr.fill = header_fill
        c_src_hdr.font = Font(bold=True, color="FFFFFF")
        c_src_cnt = ws.cell(5, 2, "Số lượng")
        c_src_cnt.fill = header_fill
        c_src_cnt.font = Font(bold=True, color="FFFFFF")

        source_counts: dict = {}
        for lead in leads:
            source_counts[lead.source] = source_counts.get(lead.source, 0) + 1

        row = 6
        for source, count in sorted(source_counts.items(), key=lambda x: -x[1]):
            ws.cell(row, 1, source)
            ws.cell(row, 2, count)
            row += 1

        # Theo nhà mạng
        c_car_hdr = ws.cell(row + 1, 1, "Theo nhà mạng")
        c_car_hdr.font = Font(bold=True)
        c_car_hdr.fill = header_fill
        c_car_hdr.font = Font(bold=True, color="FFFFFF")
        c_car_cnt = ws.cell(row + 1, 2, "Số lượng")
        c_car_cnt.fill = header_fill
        c_car_cnt.font = Font(bold=True, color="FFFFFF")

        carrier_counts: dict = {}
        for lead in leads:
            c = lead.carrier or "Không rõ"
            carrier_counts[c] = carrier_counts.get(c, 0) + 1

        row += 2
        for carrier, count in sorted(carrier_counts.items(), key=lambda x: -x[1]):
            ws.cell(row, 1, carrier)
            ws.cell(row, 2, count)
            row += 1
