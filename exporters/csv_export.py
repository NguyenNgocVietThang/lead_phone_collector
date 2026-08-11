"""
exporters/csv_export.py — Xuất leads ra file CSV.

Encoding UTF-8 BOM để tương thích Excel tiếng Việt.
"""

import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from config.settings import settings
from storage.database import Lead
from processors.source_helper import format_source_label

logger = logging.getLogger(__name__)

_HEADERS = [
    "ID", "Tên", "Số điện thoại",
    "Nguồn", "Người tìm kiếm", "URL nguồn", "Địa chỉ", "Website",
    "Nội dung chứa SĐT", "Trạng thái", "Ngày thu thập",
]


class CsvExporter:
    """
    Xuất leads ra CSV, encoding UTF-8 BOM.

    Sử dụng:
        exporter = CsvExporter()
        path = exporter.export(leads)
    """

    def export(
        self,
        leads: List[Lead],
        output_path: Optional[Path] = None,
        filename_prefix: str = "leads",
    ) -> Path:
        """
        Xuất leads ra CSV.

        Args:
            leads: Danh sách Lead.
            output_path: Đường dẫn file. None = tự tạo trong data/exports/.
            filename_prefix: Tiền tố tên file.

        Returns:
            Path đến file CSV.
        """
        if output_path is None:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            settings.EXPORT_DIR.mkdir(parents=True, exist_ok=True)
            output_path = settings.EXPORT_DIR / f"{filename_prefix}_{ts}.csv"

        # utf-8-sig = UTF-8 với BOM (Excel VN đọc được tiếng Việt)
        with open(str(output_path), "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f, delimiter=",", quotechar='"',
                                quoting=csv.QUOTE_MINIMAL)
            writer.writerow(_HEADERS)

            for lead in leads:
                writer.writerow([
                    lead.id or "",
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
                ])

        logger.info("Đã xuất %d leads ra CSV: %s", len(leads), output_path)
        return output_path
