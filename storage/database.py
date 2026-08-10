"""
storage/database.py — Quản lý SQLite database cho leads và collection jobs.

Tự động tạo DB + tables khi chạy lần đầu.
Hỗ trợ insert, dedup, query, và cập nhật trạng thái lead.
"""

import logging
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any, Iterator

from config.settings import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SQL Schema
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS leads (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT,
    phone_raw           TEXT NOT NULL,
    phone_normalized    TEXT UNIQUE NOT NULL,
    source              TEXT NOT NULL,
    source_url          TEXT,
    content             TEXT,
    address             TEXT,
    website             TEXT,
    carrier             TEXT,
    status              TEXT DEFAULT 'new',
    notes               TEXT,
    collected_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS collection_jobs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source          TEXT NOT NULL,
    query           TEXT,
    status          TEXT DEFAULT 'running',
    total_found     INTEGER DEFAULT 0,
    new_leads       INTEGER DEFAULT 0,
    duplicates      INTEGER DEFAULT 0,
    started_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    finished_at     DATETIME,
    error_message   TEXT
);

CREATE INDEX IF NOT EXISTS idx_leads_source ON leads(source);
CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
CREATE INDEX IF NOT EXISTS idx_leads_collected_at ON leads(collected_at);
CREATE INDEX IF NOT EXISTS idx_leads_carrier ON leads(carrier);
"""


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Lead:
    """Đại diện cho một bản ghi lead."""
    id: Optional[int] = None
    name: str = ""
    phone_raw: str = ""
    phone_normalized: str = ""
    source: str = ""
    source_url: str = ""
    content: str = ""
    address: str = ""
    website: str = ""
    carrier: str = ""
    status: str = "new"
    notes: str = ""
    collected_at: Optional[str] = None
    updated_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "phone_raw": self.phone_raw,
            "phone_normalized": self.phone_normalized,
            "source": self.source,
            "source_url": self.source_url,
            "content": self.content,
            "address": self.address,
            "website": self.website,
            "carrier": self.carrier,
            "status": self.status,
            "notes": self.notes,
            "collected_at": self.collected_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Lead":
        return cls(**dict(row))


@dataclass
class CollectionJob:
    """Đại diện cho một công việc thu thập."""
    id: Optional[int] = None
    source: str = ""
    query: str = ""
    status: str = "running"
    total_found: int = 0
    new_leads: int = 0
    duplicates: int = 0
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    error_message: Optional[str] = None


# ---------------------------------------------------------------------------
# LeadDatabase
# ---------------------------------------------------------------------------

class LeadDatabase:
    """
    Quản lý SQLite database.

    Sử dụng:
        db = LeadDatabase()
        db.insert_lead(Lead(phone_raw="098...", phone_normalized="0981234567", ...))
        leads = db.get_leads(status="new", limit=100)
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or settings.DATABASE_PATH
        self.db_path = Path(self.db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    # ── Context manager ─────────────────────────────────────────────────────

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Tạo connection với row_factory để truy cập cột theo tên."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ── Init ─────────────────────────────────────────────────────────────────

    def _init_db(self):
        """Tạo tables nếu chưa tồn tại."""
        with self._connect() as conn:
            conn.executescript(_SCHEMA_SQL)
        logger.debug("Database khởi tạo thành công tại: %s", self.db_path)

    # ── Lead CRUD ────────────────────────────────────────────────────────────

    def insert_lead(self, lead: Lead) -> Optional[int]:
        """
        Chèn lead mới. Bỏ qua nếu `phone_normalized` đã tồn tại.

        Returns:
            ID của lead được chèn, hoặc None nếu bị trùng.
        """
        sql = """
            INSERT OR IGNORE INTO leads
                (name, phone_raw, phone_normalized, source, source_url,
                 content, address, website, carrier, status, notes)
            VALUES
                (:name, :phone_raw, :phone_normalized, :source, :source_url,
                 :content, :address, :website, :carrier, :status, :notes)
        """
        with self._connect() as conn:
            cursor = conn.execute(sql, {
                "name": lead.name or "",
                "phone_raw": lead.phone_raw or "",
                "phone_normalized": lead.phone_normalized,
                "source": lead.source,
                "source_url": lead.source_url or "",
                "content": lead.content or "",
                "address": lead.address or "",
                "website": lead.website or "",
                "carrier": lead.carrier or "",
                "status": lead.status or "new",
                "notes": lead.notes or "",
            })
            if cursor.rowcount > 0:
                logger.debug("Chèn lead mới: %s (%s)", lead.phone_normalized, lead.name)
                return cursor.lastrowid
            else:
                logger.debug("Bỏ qua trùng: %s", lead.phone_normalized)
                return None

    def insert_leads_batch(self, leads: List[Lead]) -> Dict[str, int]:
        """
        Chèn nhiều leads cùng lúc.

        Returns:
            {"inserted": int, "duplicates": int}
        """
        inserted = 0
        duplicates = 0
        for lead in leads:
            result = self.insert_lead(lead)
            if result is not None:
                inserted += 1
            else:
                duplicates += 1
        logger.info("Batch insert: %d mới, %d trùng.", inserted, duplicates)
        return {"inserted": inserted, "duplicates": duplicates}

    def get_leads(
        self,
        source: Optional[str] = None,
        status: Optional[str] = None,
        carrier: Optional[str] = None,
        limit: int = 1000,
        offset: int = 0,
        search: Optional[str] = None,
    ) -> List[Lead]:
        """Truy vấn leads với filter."""
        conditions = []
        params: Dict[str, Any] = {}

        if source:
            conditions.append("source = :source")
            params["source"] = source
        if status:
            conditions.append("status = :status")
            params["status"] = status
        if carrier:
            conditions.append("carrier = :carrier")
            params["carrier"] = carrier
        if search:
            conditions.append(
                "(name LIKE :search OR phone_normalized LIKE :search OR address LIKE :search)"
            )
            params["search"] = f"%{search}%"

        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        sql = f"""
            SELECT * FROM leads {where}
            ORDER BY collected_at DESC
            LIMIT :limit OFFSET :offset
        """
        params["limit"] = limit
        params["offset"] = offset

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [Lead.from_row(r) for r in rows]

    def get_lead_by_id(self, lead_id: int) -> Optional[Lead]:
        """Lấy lead theo ID."""
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
        return Lead.from_row(row) if row else None

    def update_lead_status(self, lead_id: int, status: str, notes: str = "") -> bool:
        """Cập nhật trạng thái lead."""
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE leads SET status = ?, notes = ?, updated_at = ? WHERE id = ?",
                (status, notes, datetime.now().isoformat(), lead_id),
            )
            return cursor.rowcount > 0

    def get_stats(self) -> Dict[str, Any]:
        """Thống kê tổng quan."""
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
            by_source = conn.execute(
                "SELECT source, COUNT(*) as cnt FROM leads GROUP BY source"
            ).fetchall()
            by_status = conn.execute(
                "SELECT status, COUNT(*) as cnt FROM leads GROUP BY status"
            ).fetchall()
            by_carrier = conn.execute(
                "SELECT carrier, COUNT(*) as cnt FROM leads WHERE carrier IS NOT NULL "
                "AND carrier != '' GROUP BY carrier ORDER BY cnt DESC"
            ).fetchall()
            today = conn.execute(
                "SELECT COUNT(*) FROM leads WHERE date(collected_at) = date('now')"
            ).fetchone()[0]

        return {
            "total": total,
            "today": today,
            "by_source": {r["source"]: r["cnt"] for r in by_source},
            "by_status": {r["status"]: r["cnt"] for r in by_status},
            "by_carrier": {r["carrier"]: r["cnt"] for r in by_carrier},
        }

    def get_all_for_export(
        self,
        source: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Lead]:
        """Lấy tất cả leads để export (không phân trang)."""
        return self.get_leads(source=source, status=status, limit=100_000)

    # ── Jobs CRUD ────────────────────────────────────────────────────────────

    def create_job(self, source: str, query: str) -> int:
        """Tạo job mới, trả về ID."""
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO collection_jobs (source, query) VALUES (?, ?)",
                (source, query),
            )
            return cursor.lastrowid or 0

    def update_job(self, job_id: int, **kwargs) -> None:
        """Cập nhật thông tin job (status, total_found, new_leads, ...)."""
        if not kwargs:
            return
        fields = ", ".join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values()) + [job_id]
        with self._connect() as conn:
            conn.execute(f"UPDATE collection_jobs SET {fields} WHERE id = ?", values)

    def finish_job(self, job_id: int, total_found: int, new_leads: int, duplicates: int):
        """Đánh dấu job hoàn thành."""
        self.update_job(
            job_id,
            status="done",
            total_found=total_found,
            new_leads=new_leads,
            duplicates=duplicates,
            finished_at=datetime.now().isoformat(),
        )

    def fail_job(self, job_id: int, error: str):
        """Đánh dấu job thất bại."""
        self.update_job(
            job_id,
            status="failed",
            error_message=error[:500],
            finished_at=datetime.now().isoformat(),
        )

    def get_jobs(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Lấy danh sách jobs gần đây."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM collection_jobs ORDER BY started_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_job(self, job_id: int) -> Optional[Dict[str, Any]]:
        """Lấy thông tin một job theo ID."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM collection_jobs WHERE id = ?", (job_id,)
            ).fetchone()
        return dict(row) if row else None
