"""
storage/database.py — Quản lý SQLite database cho leads và collection jobs.

Tự động tạo DB + tables khi chạy lần đầu.
Hỗ trợ insert, dedup, query, và cập nhật trạng thái lead.
"""

import logging
import re
import sqlite3
import unicodedata
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any, Iterator, Tuple

from config.settings import settings

logger = logging.getLogger(__name__)


def remove_accents(input_str: Optional[str]) -> str:
    """Loại bỏ dấu tiếng Việt, chuyển về chữ thường và chuẩn hóa khoảng trắng dư thừa."""
    if not input_str:
        return ""
    s = str(input_str).replace("đ", "d").replace("Đ", "d")
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.lower()
    s = re.sub(r"\s+", " ", s).strip()
    return s


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
    collector_user      TEXT,
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
    collector_user  TEXT,
    started_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    finished_at     DATETIME,
    error_message   TEXT
);

CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name       TEXT NOT NULL,
    email           TEXT UNIQUE NOT NULL,
    password_hash   TEXT,
    auth_provider   TEXT DEFAULT 'email',
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_login      DATETIME
);

CREATE INDEX IF NOT EXISTS idx_leads_source ON leads(source);
CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
CREATE INDEX IF NOT EXISTS idx_leads_collected_at ON leads(collected_at);
CREATE INDEX IF NOT EXISTS idx_leads_carrier ON leads(carrier);
"""

_OAUTH_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS oauth_identities (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             INTEGER NOT NULL,
    provider            TEXT NOT NULL,
    provider_subject    TEXT NOT NULL,
    provider_email      TEXT NOT NULL,
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_login          DATETIME,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(provider, provider_subject)
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_oauth_identities_user ON oauth_identities(user_id);
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
    collector_user: str = ""
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
            "collector_user": self.collector_user,
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
    collector_user: str = ""
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
        """Tạo connection với row_factory và hàm UNACCENT tùy chỉnh."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.create_function("UNACCENT", 1, remove_accents)
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
        """Tạo tables nếu chưa tồn tại và tự động chuyển đổi source cũ sang fb_playwright_."""
        with self._connect() as conn:
            conn.executescript(_SCHEMA_SQL)
            self._migrate_users_password_nullable(conn)
            conn.executescript(_OAUTH_SCHEMA_SQL)
            try:
                conn.execute("UPDATE leads SET source = REPLACE(source, 'fb_selenium_', 'fb_playwright_') WHERE source LIKE 'fb_selenium_%';")
                conn.execute("UPDATE collection_jobs SET source = REPLACE(source, 'fb_selenium_', 'fb_playwright_') WHERE source LIKE 'fb_selenium_%';")
            except Exception as e:
                logger.debug("Lỗi khi migrate source trong DB: %s", e)

            # Auto-migrate collector_user columns
            try:
                cols = [row[1] for row in conn.execute("PRAGMA table_info(leads);").fetchall()]
                if "collector_user" not in cols:
                    conn.execute("ALTER TABLE leads ADD COLUMN collector_user TEXT;")
                    logger.info("Đã bổ sung cột collector_user vào bảng leads.")
            except Exception as e:
                logger.debug("Lỗi khi migrate collector_user cho leads: %s", e)

            try:
                cols_jobs = [row[1] for row in conn.execute("PRAGMA table_info(collection_jobs);").fetchall()]
                if "collector_user" not in cols_jobs:
                    conn.execute("ALTER TABLE collection_jobs ADD COLUMN collector_user TEXT;")
                    logger.info("Đã bổ sung cột collector_user vào bảng collection_jobs.")
            except Exception as e:
                logger.debug("Lỗi khi migrate collector_user cho collection_jobs: %s", e)

            try:
                conn.execute("CREATE INDEX IF NOT EXISTS idx_leads_collector_user ON leads(collector_user);")
            except Exception as e:
                logger.debug("Lỗi tạo index collector_user: %s", e)

        logger.debug("Database khởi tạo thành công tại: %s", self.db_path)

    @staticmethod
    def _migrate_users_password_nullable(conn: sqlite3.Connection) -> None:
        """Cho phép tài khoản OAuth không có mật khẩu, đồng thời giữ nguyên user cũ."""
        columns = conn.execute("PRAGMA table_info(users);").fetchall()
        password_column = next((row for row in columns if row[1] == "password_hash"), None)
        if not password_column or password_column[3] == 0:
            return

        conn.commit()
        conn.execute("PRAGMA foreign_keys=OFF;")
        try:
            conn.executescript("""
                BEGIN;
                CREATE TABLE users_migrated (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    full_name       TEXT NOT NULL,
                    email           TEXT UNIQUE NOT NULL,
                    password_hash   TEXT,
                    auth_provider   TEXT DEFAULT 'email',
                    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_login      DATETIME
                );
                INSERT INTO users_migrated
                    (id, full_name, email, password_hash, auth_provider, created_at, last_login)
                SELECT id, full_name, lower(email), password_hash, auth_provider, created_at, last_login
                FROM users;
                DROP TABLE users;
                ALTER TABLE users_migrated RENAME TO users;
                COMMIT;
            """)
        except Exception:
            if conn.in_transaction:
                conn.rollback()
            raise
        finally:
            conn.execute("PRAGMA foreign_keys=ON;")
        logger.info("Đã migrate users.password_hash sang nullable.")

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
                 content, address, website, carrier, status, notes, collector_user)
            VALUES
                (:name, :phone_raw, :phone_normalized, :source, :source_url,
                 :content, :address, :website, :carrier, :status, :notes, :collector_user)
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
                "collector_user": lead.collector_user or "",
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

    def _build_search_conditions(
        self,
        search: str,
        search_mode: str = "fuzzy"
    ) -> Tuple[List[str], Dict[str, Any], str]:
        r"""
        Xây dựng điều kiện SQL WHERE, parameters và ORDER BY score cho tìm kiếm.

        - Khớp 1 phần / bất kỳ từ nào (ví dụ: tìm "Cửa hàng gia dụng" vẫn tìm thấy "Gia dụng").
        - Không phân biệt chữ hoa/thường (case-insensitive).
        - Loại bỏ dấu tiếng Việt (accent-insensitive).
        - Chuẩn hóa khoảng trắng dư thừa (\s+ -> space).
        - Sắp xếp kết quả khớp nhiều từ nhất/khớp tốt nhất lên đầu.
        """
        conditions = []
        params: Dict[str, Any] = {}
        order_by_score = ""

        search_normalized = remove_accents(search)
        if not search_normalized:
            return conditions, params, order_by_score

        fields = ["name", "phone_raw", "phone_normalized", "address", "content", "notes", "website"]

        if search_mode == "exact":
            unaccented_search = f"%{search_normalized}%"
            exact_conds = []
            for f_idx, field in enumerate(fields):
                p_key = f"exact_search_{f_idx}"
                exact_conds.append(f"UNACCENT({field}) LIKE :{p_key}")
                params[p_key] = unaccented_search
            conditions.append(f"({' OR '.join(exact_conds)})")

        else:
            tokens = [t for t in search_normalized.split() if t]

            phrase_param = f"%{search_normalized}%"
            params["search_full_phrase"] = phrase_param

            all_match_clauses = []
            for f_idx, field in enumerate(fields):
                all_match_clauses.append(f"UNACCENT({field}) LIKE :search_full_phrase")

            score_parts = []
            for t_idx, token in enumerate(tokens):
                token_val = f"%{token}%"
                t_field_conds = []
                for f_idx, field in enumerate(fields):
                    p_key = f"tok_{t_idx}_{f_idx}"
                    t_field_conds.append(f"UNACCENT({field}) LIKE :{p_key}")
                    params[p_key] = token_val
                
                t_clause = f"({' OR '.join(t_field_conds)})"
                all_match_clauses.append(t_clause)
                score_parts.append(f"(CASE WHEN {t_clause} THEN 1 ELSE 0 END)")

            conditions.append(f"({' OR '.join(all_match_clauses)})")

            if score_parts:
                score_expr = " + ".join(score_parts)
                order_by_score = f"({score_expr}) DESC,"

        return conditions, params, order_by_score

    def _build_source_condition(self, source: str) -> Tuple[str, Dict[str, Any]]:
        """Xây dựng SQL clause và parameters cho việc lọc theo nguồn (tổng quát hoặc chi tiết)."""
        s = (source or "").strip()
        if not s:
            return "", {}

        if s == "facebook":
            return "source LIKE 'fb_%'", {}
        elif s in ["fb_post", "fb_posts"]:
            return "(source LIKE '%post%' AND source LIKE 'fb_%')", {}
        elif s in ["fb_comment", "fb_comments"]:
            return "(source LIKE '%comment%' AND source LIKE 'fb_%')", {}
        elif s in ["fb_profile", "fb_about", "fb_bio"]:
            return "(source LIKE '%about%' OR source LIKE '%bio%' OR source LIKE '%profile%')", {}
        elif s in ["fb_liker", "fb_likers"]:
            return "source LIKE '%liker%'", {}
        elif s == "google_maps":
            return "source LIKE 'google_maps%'", {}
        elif s == "google_maps_details":
            return "(source = 'google_maps' OR source = 'google_maps_details')", {}
        elif s in ["google_maps_comment", "google_maps_review"]:
            return "(source = 'google_maps_comment' OR source = 'google_maps_review')", {}
        else:
            return "source = :src_param", {"src_param": s}

    # Cột được phép sort từ UI (whitelist để tránh SQL injection qua query param).
    SORTABLE_COLUMNS = {
        "name": "name",
        "phone": "phone_normalized",
        "source": "source",
        "collector_user": "collector_user",
        "address": "address",
        "status": "status",
        "collected_at": "collected_at",
    }

    def get_leads(
        self,
        source: Optional[str] = None,
        status: Optional[str] = None,
        carrier: Optional[str] = None,
        collector_user: Optional[str] = None,
        limit: int = 1000,
        offset: int = 0,
        search: Optional[str] = None,
        search_mode: str = "fuzzy",
        sort_by: Optional[str] = None,
        sort_dir: str = "asc",
    ) -> List[Lead]:
        """Truy vấn leads với filter và tìm kiếm (gần đúng, trùng 1 phần, chính xác)."""
        conditions = []
        params: Dict[str, Any] = {}
        order_clause = "ORDER BY collected_at DESC"

        if source:
            s_cond, s_params = self._build_source_condition(source)
            if s_cond:
                conditions.append(s_cond)
                params.update(s_params)
        if status:
            conditions.append("status = :status")
            params["status"] = status
        if carrier:
            conditions.append("carrier = :carrier")
            params["carrier"] = carrier
        if collector_user:
            conditions.append("collector_user = :collector_user")
            params["collector_user"] = collector_user

        if search and search.strip():
            s_conds, s_params, order_score = self._build_search_conditions(search, search_mode)
            conditions.extend(s_conds)
            params.update(s_params)
            if order_score:
                order_clause = f"ORDER BY {order_score} collected_at DESC"

        # Sort theo cột do người dùng chọn (bấm tiêu đề cột) — ưu tiên hơn thứ hạng tìm kiếm.
        sort_col = self.SORTABLE_COLUMNS.get((sort_by or "").strip())
        if sort_col:
            direction = "DESC" if (sort_dir or "").lower() == "desc" else "ASC"
            order_clause = f"ORDER BY {sort_col} {direction}, collected_at DESC"

        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        sql = f"""
            SELECT * FROM leads {where}
            {order_clause}
            LIMIT :limit OFFSET :offset
        """
        params["limit"] = limit
        params["offset"] = offset

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [Lead.from_row(r) for r in rows]

    def count_leads(
        self,
        source: Optional[str] = None,
        status: Optional[str] = None,
        carrier: Optional[str] = None,
        collector_user: Optional[str] = None,
        search: Optional[str] = None,
        search_mode: str = "fuzzy",
    ) -> int:
        """Đếm số lượng leads thỏa mãn các điều kiện lọc và tìm kiếm."""
        conditions = []
        params: Dict[str, Any] = {}

        if source:
            s_cond, s_params = self._build_source_condition(source)
            if s_cond:
                conditions.append(s_cond)
                params.update(s_params)
        if status:
            conditions.append("status = :status")
            params["status"] = status
        if carrier:
            conditions.append("carrier = :carrier")
            params["carrier"] = carrier
        if collector_user:
            conditions.append("collector_user = :collector_user")
            params["collector_user"] = collector_user

        if search and search.strip():
            s_conds, s_params, _ = self._build_search_conditions(search, search_mode)
            conditions.extend(s_conds)
            params.update(s_params)

        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        sql = f"SELECT COUNT(*) FROM leads {where}"

        with self._connect() as conn:
            return conn.execute(sql, params).fetchone()[0]

    def get_distinct_collectors(self) -> List[str]:
        """Lấy danh sách tất cả những người tìm kiếm duy nhất từ DB."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT collector_user FROM leads WHERE collector_user IS NOT NULL AND collector_user != '' ORDER BY collector_user ASC"
            ).fetchall()
        return [r[0] for r in rows if r[0]]

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

        by_source_map = {r["source"]: r["cnt"] for r in by_source}
        # Nhóm nguồn theo prefix để không bỏ sót các source key mới/khác nhau
        # (vd: "google_maps_details", "google_maps_comment", "google_maps"...).
        google_maps_total = sum(
            cnt for src, cnt in by_source_map.items() if src.startswith("google_maps")
        )
        facebook_total = sum(
            cnt for src, cnt in by_source_map.items() if src.startswith("fb_")
        )

        return {
            "total": total,
            "today": today,
            "by_source": by_source_map,
            "by_status": {r["status"]: r["cnt"] for r in by_status},
            "by_carrier": {r["carrier"]: r["cnt"] for r in by_carrier},
            "by_source_group": {
                "google_maps": google_maps_total,
                "facebook": facebook_total,
            },
        }

    def get_all_for_export(
        self,
        source: Optional[str] = None,
        status: Optional[str] = None,
        carrier: Optional[str] = None,
        collector_user: Optional[str] = None,
        search: Optional[str] = None,
        search_mode: str = "fuzzy",
    ) -> List[Lead]:
        """Lấy tất cả leads để export (không phân trang)."""
        return self.get_leads(
            source=source,
            status=status,
            carrier=carrier,
            collector_user=collector_user,
            search=search,
            search_mode=search_mode,
            limit=100_000,
        )

    # ── Jobs CRUD ────────────────────────────────────────────────────────────

    def create_job(self, source: str, query: str, collector_user: str = "") -> int:
        """Tạo job mới, trả về ID."""
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO collection_jobs (source, query, collector_user) VALUES (?, ?, ?)",
                (source, query, collector_user or ""),
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

    # ── User CRUD ────────────────────────────────────────────────────────────

    def create_user(self, full_name: str, email: str, password_hash: Optional[str], auth_provider: str = "email") -> Optional[int]:
        """
        Tạo người dùng mới.

        Returns:
            ID của user được tạo, hoặc None nếu email đã tồn tại.
        """
        sql = """
            INSERT OR IGNORE INTO users
                (full_name, email, password_hash, auth_provider)
            VALUES
                (?, ?, ?, ?)
        """
        with self._connect() as conn:
            cursor = conn.execute(sql, (full_name, email.strip().lower(), password_hash, auth_provider))
            if cursor.rowcount > 0:
                logger.info("Tạo user mới: %s (%s)", email, full_name)
                return cursor.lastrowid
            else:
                logger.debug("Email đã tồn tại: %s", email)
                return None

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Lấy thông tin người dùng theo email."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE email = ?", (email.strip().lower(),)
            ).fetchone()
        return dict(row) if row else None

    def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Lấy thông tin người dùng theo ID nội bộ."""
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None

    def update_user_password_hash(self, user_id: int, password_hash: str) -> bool:
        """Nâng cấp hoặc thay đổi password hash của người dùng."""
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (password_hash, user_id),
            )
            return cursor.rowcount > 0

    def login_oauth_user(
        self,
        provider: str,
        provider_subject: str,
        email: str,
        full_name: str,
    ) -> Dict[str, Any]:
        """Đăng nhập, tạo mới hoặc liên kết một danh tính OAuth theo email."""
        provider = provider.strip().lower()
        provider_subject = provider_subject.strip()
        email = email.strip().lower()
        full_name = full_name.strip() or email.split("@", 1)[0]
        now = datetime.now().isoformat()

        with self._connect() as conn:
            identity = conn.execute(
                """
                SELECT users.* FROM oauth_identities
                JOIN users ON users.id = oauth_identities.user_id
                WHERE oauth_identities.provider = ? AND oauth_identities.provider_subject = ?
                """,
                (provider, provider_subject),
            ).fetchone()

            if identity:
                user_id = identity["id"]
                conn.execute(
                    """
                    UPDATE oauth_identities SET provider_email = ?, last_login = ?
                    WHERE provider = ? AND provider_subject = ?
                    """,
                    (email, now, provider, provider_subject),
                )
            else:
                user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
                if user:
                    user_id = user["id"]
                else:
                    cursor = conn.execute(
                        """
                        INSERT INTO users (full_name, email, password_hash, auth_provider, last_login)
                        VALUES (?, ?, NULL, ?, ?)
                        """,
                        (full_name, email, provider, now),
                    )
                    user_id = cursor.lastrowid

                conn.execute(
                    """
                    INSERT INTO oauth_identities
                        (user_id, provider, provider_subject, provider_email, last_login)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (user_id, provider, provider_subject, email, now),
                )

            conn.execute("UPDATE users SET last_login = ? WHERE id = ?", (now, user_id))
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            return dict(row)

    def get_oauth_identity(self, provider: str, provider_subject: str) -> Optional[Dict[str, Any]]:
        """Lấy danh tính OAuth để phục vụ kiểm thử và quản trị."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM oauth_identities WHERE provider = ? AND provider_subject = ?",
                (provider.strip().lower(), provider_subject.strip()),
            ).fetchone()
        return dict(row) if row else None

    def update_user_last_login(self, email: str) -> bool:
        """Cập nhật thời gian đăng nhập cuối cùng."""
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE users SET last_login = ? WHERE email = ?",
                (datetime.now().isoformat(), email),
            )
            return cursor.rowcount > 0
