"""Tests for GoogleSheetsSync in storage/sheets.py."""

from unittest.mock import MagicMock, patch
import pytest
from storage.database import Lead
from storage.sheets import GoogleSheetsSync


@pytest.fixture
def sample_lead():
    return Lead(
        id=1,
        name="Nguyễn Văn A",
        phone_raw="0912345678",
        phone_normalized="84912345678",
        carrier="VinaPhone",
        source="Facebook Group",
        source_url="https://facebook.com/groups/123",
        address="Hà Nội",
        website="",
        content="Cần tìm dịch vụ thi công",
        status="new",
        collected_at="2026-08-10 09:00:00",
    )


def test_sync_leads_unconfigured(sample_lead):
    syncer = GoogleSheetsSync()
    with patch.object(syncer, "is_configured", return_value=False):
        result = syncer.sync_leads([sample_lead])
        assert result["synced"] == 0
        assert result["error"] == "Chưa cấu hình Google Sheets"


def test_sync_leads_connection_failure(sample_lead):
    syncer = GoogleSheetsSync()
    with patch.object(syncer, "is_configured", return_value=True), patch.object(
        syncer, "_get_sheet", return_value=None
    ):
        result = syncer.sync_leads([sample_lead])
        assert result["synced"] == 0
        assert result["error"] == "Không thể kết nối tới Google Sheet"


def test_sync_leads_success(sample_lead):
    syncer = GoogleSheetsSync()
    mock_sheet = MagicMock()
    mock_sheet.get_all_values.return_value = [["Header1", "Header2", "Số điện thoại"]]

    with patch.object(syncer, "is_configured", return_value=True), patch.object(
        syncer, "_get_sheet", return_value=mock_sheet
    ):
        result = syncer.sync_leads([sample_lead])
        assert result["synced"] == 1
        assert result["skipped"] == 0
        assert result["error"] is None
        mock_sheet.append_rows.assert_called_once()
