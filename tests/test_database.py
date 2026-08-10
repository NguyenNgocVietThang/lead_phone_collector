"""
tests/test_database.py — Unit tests cho LeadDatabase.
Chạy: pytest tests/test_database.py -v
"""

import tempfile
import pytest
from pathlib import Path
from typing import Dict, Any

from storage.database import LeadDatabase, Lead


@pytest.fixture
def tmp_db():
    """DB tạm thời dùng trong test, xóa sau khi xong."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    db = LeadDatabase(db_path=db_path)
    yield db
    db_path.unlink(missing_ok=True)


def make_lead(**kwargs) -> Lead:
    """Tạo Lead mẫu với giá trị mặc định."""
    defaults: Dict[str, Any] = {
        "name": "Test Biz",
        "phone_raw": "098 123 4567",
        "phone_normalized": "0981234567",
        "source": "google_maps",
        "source_url": "https://maps.google.com/test",
        "carrier": "Viettel",
    }
    defaults.update(kwargs)
    return Lead(**defaults)


class TestInsert:
    def test_insert_new_lead(self, tmp_db):
        lead = make_lead()
        lead_id = tmp_db.insert_lead(lead)
        assert lead_id is not None
        assert lead_id > 0

    def test_insert_duplicate_returns_none(self, tmp_db):
        lead = make_lead()
        first = tmp_db.insert_lead(lead)
        second = tmp_db.insert_lead(lead)  # Trùng phone_normalized
        assert first is not None
        assert second is None

    def test_insert_different_phones(self, tmp_db):
        lead1 = make_lead(phone_normalized="0981234567")
        lead2 = make_lead(phone_normalized="0912345678")
        id1 = tmp_db.insert_lead(lead1)
        id2 = tmp_db.insert_lead(lead2)
        assert id1 is not None
        assert id2 is not None
        assert id1 != id2

    def test_batch_insert(self, tmp_db):
        leads = [
            make_lead(phone_normalized=f"098123456{i}") for i in range(5)
        ]
        result = tmp_db.insert_leads_batch(leads)
        assert result["inserted"] == 5
        assert result["duplicates"] == 0

    def test_batch_insert_with_duplicates(self, tmp_db):
        lead = make_lead(phone_normalized="0981234567")
        tmp_db.insert_lead(lead)  # Thêm trước

        leads = [
            make_lead(phone_normalized="0981234567"),  # Trùng
            make_lead(phone_normalized="0912345678"),  # Mới
        ]
        result = tmp_db.insert_leads_batch(leads)
        assert result["inserted"] == 1
        assert result["duplicates"] == 1


class TestQuery:
    def test_get_leads_all(self, tmp_db):
        tmp_db.insert_lead(make_lead(phone_normalized="0981234567", source="google_maps"))
        tmp_db.insert_lead(make_lead(phone_normalized="0912345678", source="fb_playwright_post"))
        leads = tmp_db.get_leads()
        assert len(leads) == 2

    def test_get_leads_by_source(self, tmp_db):
        tmp_db.insert_lead(make_lead(phone_normalized="0981234567", source="google_maps"))
        tmp_db.insert_lead(make_lead(phone_normalized="0912345678", source="fb_playwright_post"))
        maps_leads = tmp_db.get_leads(source="google_maps")
        assert len(maps_leads) == 1
        assert maps_leads[0].source == "google_maps"

    def test_get_leads_by_status(self, tmp_db):
        tmp_db.insert_lead(make_lead(phone_normalized="0981234567", status="new"))
        tmp_db.insert_lead(make_lead(phone_normalized="0912345678", status="contacted"))
        new_leads = tmp_db.get_leads(status="new")
        assert len(new_leads) == 1

    def test_get_lead_by_id(self, tmp_db):
        lead = make_lead()
        lead_id = tmp_db.insert_lead(lead)
        fetched = tmp_db.get_lead_by_id(lead_id)
        assert fetched is not None
        assert fetched.phone_normalized == lead.phone_normalized

    def test_get_lead_not_found(self, tmp_db):
        result = tmp_db.get_lead_by_id(99999)
        assert result is None

    def test_search_fuzzy_unaccented(self, tmp_db):
        tmp_db.insert_lead(make_lead(name="Cửa hàng Gia Dụng Hải Hải", phone_normalized="0981234567"))
        tmp_db.insert_lead(make_lead(name="Thiết bị Điện Máy Hùng", phone_normalized="0912345678"))

        # Search unaccented "hang gia dung" should match "Cửa hàng Gia Dụng Hải Hải"
        results = tmp_db.get_leads(search="hang gia dung", search_mode="fuzzy")
        assert len(results) == 1
        assert results[0].phone_normalized == "0981234567"

        # Search accented "hàng gia dụng" should also match
        results2 = tmp_db.get_leads(search="hàng gia dụng", search_mode="fuzzy")
        assert len(results2) == 1
        assert results2[0].phone_normalized == "0981234567"

    def test_search_partial_query_finds_subset(self, tmp_db):
        # User requirement test: Searching "Cửa hàng gia dụng" must still find "Gia dụng"
        tmp_db.insert_lead(make_lead(name="Gia Dụng Miền Nam", phone_normalized="0981112223"))
        results = tmp_db.get_leads(search="Cửa hàng gia dụng")
        assert len(results) == 1
        assert results[0].name == "Gia Dụng Miền Nam"

    def test_search_space_normalization_and_case_insensitivity(self, tmp_db):
        tmp_db.insert_lead(make_lead(name="Cửa   hàng  Gia  Dụng", phone_normalized="0989998887"))
        # Search with irregular spacing and mixed uppercase
        results = tmp_db.get_leads(search="  CỬA   HÀNG   GIA   DỤNG  ")
        assert len(results) == 1
        assert results[0].phone_normalized == "0989998887"

    def test_search_exact(self, tmp_db):
        tmp_db.insert_lead(make_lead(name="Gia Dụng Cao Cấp", phone_normalized="0981112223"))
        results_exact = tmp_db.get_leads(search="Gia Dụng Cao Cấp", search_mode="exact")
        assert len(results_exact) == 1

        results_fail = tmp_db.get_leads(search="Gia Dụng Giá Rẻ", search_mode="exact")
        assert len(results_fail) == 0

    def test_count_leads(self, tmp_db):
        tmp_db.insert_lead(make_lead(name="Cửa hàng A", phone_normalized="0981234567", source="google_maps"))
        tmp_db.insert_lead(make_lead(name="Cửa hàng B", phone_normalized="0912345678", source="fb_playwright_post"))
        assert tmp_db.count_leads() == 2
        assert tmp_db.count_leads(source="google_maps") == 1
        assert tmp_db.count_leads(search="Cửa hàng A") == 2  # Matches both because "Cửa hàng" is shared, with A ranked higher


class TestUpdate:
    def test_update_status(self, tmp_db):
        lead_id = tmp_db.insert_lead(make_lead())
        success = tmp_db.update_lead_status(lead_id, "contacted", "Đã gọi")
        assert success is True
        updated = tmp_db.get_lead_by_id(lead_id)
        assert updated.status == "contacted"
        assert updated.notes == "Đã gọi"

    def test_update_nonexistent(self, tmp_db):
        success = tmp_db.update_lead_status(99999, "contacted")
        assert success is False


class TestStats:
    def test_stats_empty(self, tmp_db):
        stats = tmp_db.get_stats()
        assert stats["total"] == 0
        assert stats["today"] == 0

    def test_stats_with_data(self, tmp_db):
        tmp_db.insert_lead(make_lead(phone_normalized="0981234567", source="google_maps"))
        tmp_db.insert_lead(make_lead(phone_normalized="0912345678", source="fb_playwright_post"))
        stats = tmp_db.get_stats()
        assert stats["total"] == 2
        assert "google_maps" in stats["by_source"]
        assert stats["by_source"]["google_maps"] == 1


class TestJobs:
    def test_create_job(self, tmp_db):
        job_id = tmp_db.create_job("google_maps", "nhà hàng Hà Nội")
        assert job_id is not None
        job = tmp_db.get_job(job_id)
        assert job is not None
        assert job["status"] == "running"

    def test_finish_job(self, tmp_db):
        job_id = tmp_db.create_job("google_maps", "test")
        tmp_db.finish_job(job_id, total_found=10, new_leads=8, duplicates=2)
        job = tmp_db.get_job(job_id)
        assert job["status"] == "done"
        assert job["total_found"] == 10
        assert job["new_leads"] == 8

    def test_fail_job(self, tmp_db):
        job_id = tmp_db.create_job("facebook", "test")
        tmp_db.fail_job(job_id, "Connection timeout")
        job = tmp_db.get_job(job_id)
        assert job["status"] == "failed"
        assert "timeout" in job["error_message"]
