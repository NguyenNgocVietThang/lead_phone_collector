"""
storage/sheets.py — Đồng bộ leads lên Google Sheets.

Dùng gspread với Service Account JSON.
Chỉ append leads mới (check theo phone_normalized), không ghi đè.
"""

import os
import logging
from typing import List

import gspread
from gspread.utils import ValueInputOption
from google.oauth2.service_account import Credentials

from config.settings import settings
from storage.database import Lead

logger = logging.getLogger(__name__)

# Header cột trong Google Sheet
_SHEET_HEADERS = [
    "ID", "Tên", "Số điện thoại", "Nhà mạng",
    "Nguồn", "URL nguồn", "Địa chỉ", "Website",
    "Nội dung chứa SĐT", "Trạng thái", "Ngày thu thập",
]


class GoogleSheetsSync:
    """
    Đồng bộ leads lên Google Sheets.

    Yêu cầu:
        - File JSON Service Account tại đường dẫn cấu hình trong .env
        - Google Sheet đã được share quyền Editor cho Service Account email

    Sử dụng:
        syncer = GoogleSheetsSync()
        syncer.sync_leads(leads)
    """

    def __init__(self):
        self._client = None
        self._sheet = None

    def is_configured(self) -> bool:
        """Kiểm tra đã cấu hình đủ chưa."""
        creds_file = settings.GOOGLE_SHEETS_CREDENTIALS_FILE
        has_creds = os.path.exists(creds_file)
        has_sheet_id = bool(settings.GOOGLE_SHEET_ID)
        return has_creds and has_sheet_id

    def sync_leads(self, leads: List[Lead]) -> dict:
        """
        Đồng bộ danh sách leads lên Google Sheets.
        Chỉ append leads có phone_normalized chưa có trong Sheet.

        Args:
            leads: Danh sách Lead cần sync.

        Returns:
            {"synced": int, "skipped": int, "error": str|None}
        """
        if not leads:
            return {"synced": 0, "skipped": 0, "error": None}

        if not self.is_configured():
            logger.warning("Google Sheets chưa được cấu hình. Bỏ qua sync.")
            return {"synced": 0, "skipped": 0, "error": "Chưa cấu hình Google Sheets"}

        try:
            sheet = self._get_sheet()
            if not sheet:
                logger.error("Không thể mở Google Sheet.")
                return {"synced": 0, "skipped": 0, "error": "Không thể kết nối tới Google Sheet"}

            existing_phones = self._get_existing_phones(sheet)
            logger.info("Sheet hiện có %d SĐT đã sync.", len(existing_phones))

            rows_to_add = []
            skipped = 0

            for lead in leads:
                if lead.phone_normalized in existing_phones:
                    skipped += 1
                    continue
                rows_to_add.append(self._lead_to_row(lead))

            if rows_to_add:
                sheet.append_rows(rows_to_add, value_input_option=ValueInputOption.user_entered)
                logger.info("Đã sync %d leads mới lên Google Sheets.", len(rows_to_add))

            return {"synced": len(rows_to_add), "skipped": skipped, "error": None}

        except Exception as e:
            logger.error("Lỗi khi sync Google Sheets: %s", e, exc_info=True)
            return {"synced": 0, "skipped": 0, "error": str(e)}

    def sync_lead(self, lead: Lead) -> bool:
        """Sync một lead đơn lẻ."""
        result = self.sync_leads([lead])
        return result["synced"] > 0

    def ensure_headers(self) -> bool:
        """Tạo header row nếu sheet trống."""
        try:
            sheet = self._get_sheet()
            if not sheet:
                return False
            existing = sheet.get_all_values()
            if not existing:
                sheet.append_row(_SHEET_HEADERS, value_input_option=ValueInputOption.user_entered)
                # Format header: bold
                sheet.format("A1:K1", {
                    "textFormat": {"bold": True},
                    "backgroundColor": {"red": 0.26, "green": 0.52, "blue": 0.96},
                })
                logger.info("Đã tạo header cho Google Sheet.")
            return True
        except Exception as e:
            logger.error("Lỗi tạo header: %s", e)
            return False

    # ── Private helpers ────────────────────────────────────────────────────

    def _get_client(self):
        """Khởi tạo gspread client nếu chưa có."""
        if self._client:
            return self._client

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_file(
            settings.GOOGLE_SHEETS_CREDENTIALS_FILE,
            scopes=scopes,
        )
        self._client = gspread.authorize(creds)
        return self._client

    def _get_sheet(self):
        """Lấy worksheet object."""
        if self._sheet:
            return self._sheet

        try:
            client = self._get_client()
            if not client:
                return None

            spreadsheet = client.open_by_key(settings.GOOGLE_SHEET_ID)

            try:
                self._sheet = spreadsheet.worksheet(settings.GOOGLE_SHEET_NAME)
            except Exception:
                # Tạo sheet mới nếu chưa tồn tại
                self._sheet = spreadsheet.add_worksheet(
                    title=settings.GOOGLE_SHEET_NAME,
                    rows=10000,
                    cols=len(_SHEET_HEADERS),
                )
                self.ensure_headers()

            return self._sheet
        except Exception as e:
            logger.error("Không thể lấy Google Sheet: %s", e)
            self._sheet = None
            return None

    def _get_existing_phones(self, sheet) -> set:
        """Lấy tập hợp phone_normalized đã có trong Sheet (cột C = index 2)."""
        if not sheet:
            return set()
        try:
            all_values = sheet.get_all_values()
            if len(all_values) <= 1:  # Chỉ có header hoặc trống
                return set()
            # Cột C (index 2) = "Số điện thoại"
            return {row[2] for row in all_values[1:] if len(row) > 2 and row[2]}
        except Exception as e:
            logger.warning("Không lấy được danh sách SĐT hiện có: %s", e)
            return set()

    @staticmethod
    def _lead_to_row(lead: Lead) -> List[str]:
        """Chuyển Lead thành row cho Google Sheets."""
        return [
            str(lead.id or ""),
            lead.name or "",
            lead.phone_normalized or "",
            lead.carrier or "",
            lead.source or "",
            lead.source_url or "",
            lead.address or "",
            lead.website or "",
            (lead.content or "")[:200],  # Giới hạn độ dài
            lead.status or "new",
            lead.collected_at or "",
        ]
