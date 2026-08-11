"""
exporters/sheets_export.py — Đẩy leads lên Google Sheets.

Dùng Service Account (gspread + google-auth). Yêu cầu:
  1. GOOGLE_SHEET_ID trong .env
  2. File credentials tại settings.GOOGLE_SHEETS_CREDENTIALS_FILE
  3. Đã share Google Sheet cho email của Service Account (quyền Editor)
"""

import logging
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

_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]


class SheetsExportError(Exception):
    """Lỗi khi cấu hình thiếu hoặc gọi Google Sheets API thất bại."""


class SheetsExporter:
    """
    Ghi đè toàn bộ nội dung một worksheet với danh sách leads hiện tại.

    Sử dụng:
        exporter = SheetsExporter()
        url = exporter.export(leads)
    """

    def _get_client(self):
        try:
            import gspread
            from google.oauth2.service_account import Credentials
        except ImportError as e:
            raise SheetsExportError(
                "Thiếu thư viện gspread/google-auth. Chạy: pip install gspread google-auth"
            ) from e

        creds_path = settings.BASE_DIR / settings.GOOGLE_SHEETS_CREDENTIALS_FILE
        if not creds_path.exists():
            raise SheetsExportError(
                f"Không tìm thấy file credentials Service Account tại: {creds_path}. "
                "Xem hướng dẫn ở trang Cài đặt."
            )

        try:
            creds = Credentials.from_service_account_file(str(creds_path), scopes=_SCOPES)
        except Exception as e:
            raise SheetsExportError(f"File credentials không hợp lệ: {e}") from e

        return gspread.authorize(creds)

    def export(
        self,
        leads: List[Lead],
        sheet_id: Optional[str] = None,
        worksheet_name: Optional[str] = None,
    ) -> str:
        """
        Ghi đè worksheet với dữ liệu leads hiện tại.

        Args:
            leads: Danh sách Lead.
            sheet_id: ID Google Sheet. None = dùng settings.GOOGLE_SHEET_ID.
            worksheet_name: Tên tab. None = dùng settings.GOOGLE_SHEET_NAME.

        Returns:
            URL của Google Sheet.
        """
        sheet_id = sheet_id or settings.GOOGLE_SHEET_ID
        worksheet_name = worksheet_name or settings.GOOGLE_SHEET_NAME

        if not sheet_id:
            raise SheetsExportError(
                "Chưa cấu hình GOOGLE_SHEET_ID trong .env. Xem hướng dẫn ở trang Cài đặt."
            )

        client = self._get_client()

        try:
            spreadsheet = client.open_by_key(sheet_id)
        except Exception as e:
            raise SheetsExportError(
                f"Không mở được Google Sheet (kiểm tra ID và quyền chia sẻ cho Service Account): {e}"
            ) from e

        try:
            worksheet = spreadsheet.worksheet(worksheet_name)
        except Exception:
            worksheet = spreadsheet.add_worksheet(
                title=worksheet_name, rows=max(len(leads) + 10, 100), cols=len(_HEADERS)
            )

        # Đảo ngược thứ tự so với database: lead mới nhất (cuối danh sách DB) lên đầu sheet.
        ordered_leads = list(reversed(leads))

        rows = [_HEADERS]
        for lead in ordered_leads:
            rows.append([
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

        try:
            worksheet.clear()
            worksheet.update(values=rows, range_name="A1")
            self._format_as_table(worksheet, n_rows=len(rows), n_cols=len(_HEADERS))
        except Exception as e:
            raise SheetsExportError(f"Ghi dữ liệu lên Google Sheets thất bại: {e}") from e

        logger.info("Đã đồng bộ %d leads lên Google Sheets (thứ tự đảo ngược): %s", len(leads), sheet_id)
        return f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit#gid={worksheet.id}"

    def _format_as_table(self, worksheet, n_rows: int, n_cols: int) -> None:
        """
        Định dạng dữ liệu vừa ghi thành bảng: header in đậm có màu nền,
        đóng băng hàng đầu, kẻ viền, và tự co giãn độ rộng cột.

        Lỗi định dạng không nên làm hỏng việc export dữ liệu, nên mọi
        exception ở đây chỉ được log lại, không raise.
        """
        try:
            from gspread.utils import rowcol_to_a1

            last_cell = rowcol_to_a1(n_rows, n_cols)
            data_range = f"A1:{last_cell}"

            # Header: nền xanh đậm, chữ trắng, in đậm, căn giữa.
            worksheet.format("A1:{}".format(rowcol_to_a1(1, n_cols)), {
                "backgroundColor": {"red": 0.15, "green": 0.29, "blue": 0.66},
                "textFormat": {
                    "bold": True,
                    "foregroundColor": {"red": 1, "green": 1, "blue": 1},
                },
                "horizontalAlignment": "CENTER",
                "verticalAlignment": "MIDDLE",
            })

            # Toàn bộ bảng: viền mỏng, căn giữa theo chiều dọc.
            worksheet.format(data_range, {
                "verticalAlignment": "MIDDLE",
                "wrapStrategy": "CLIP",
                "borders": {
                    "top": {"style": "SOLID", "color": {"red": 0.85, "green": 0.85, "blue": 0.85}},
                    "bottom": {"style": "SOLID", "color": {"red": 0.85, "green": 0.85, "blue": 0.85}},
                    "left": {"style": "SOLID", "color": {"red": 0.85, "green": 0.85, "blue": 0.85}},
                    "right": {"style": "SOLID", "color": {"red": 0.85, "green": 0.85, "blue": 0.85}},
                },
            })

            worksheet.freeze(rows=1)

            body = {
                "requests": [
                    {
                        "autoResizeDimensions": {
                            "dimensions": {
                                "sheetId": worksheet.id,
                                "dimension": "COLUMNS",
                                "startIndex": 0,
                                "endIndex": n_cols,
                            }
                        }
                    },
                    {
                        "addBanding": {
                            "bandedRange": {
                                "range": {
                                    "sheetId": worksheet.id,
                                    "startRowIndex": 0,
                                    "endRowIndex": n_rows,
                                    "startColumnIndex": 0,
                                    "endColumnIndex": n_cols,
                                },
                                "rowProperties": {
                                    "headerColor": {"red": 0.15, "green": 0.29, "blue": 0.66},
                                    "firstBandColor": {"red": 1, "green": 1, "blue": 1},
                                    "secondBandColor": {"red": 0.94, "green": 0.96, "blue": 1},
                                },
                            }
                        }
                    },
                ]
            }
            worksheet.spreadsheet.batch_update(body)
        except Exception as e:
            logger.warning("Không định dạng được bảng trên Google Sheets: %s", e)
