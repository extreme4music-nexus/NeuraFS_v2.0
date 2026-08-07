"""NeuraFS Persistent State Tracking Database Module."""

import os
import sys
import time
import sqlite3
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional

DB_FILE = Path.home() / ".neurafs" / "state.db"


class StateManager:
    """Manages SQLite persistent state tracking with OS-level file security."""

    @classmethod
    def _apply_file_security(cls, file_path: Path):
        """Applies strict OS-level permissions that persist even when services are stopped."""
        if not file_path.exists():
            return
        try:
            if sys.platform == "win32":
                import ctypes
                FILE_ATTRIBUTE_HIDDEN = 0x2
                FILE_ATTRIBUTE_SYSTEM = 0x4
                attrs = ctypes.windll.kernel32.GetFileAttributesW(str(file_path))
                if attrs != -1:
                    new_attrs = attrs | FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM
                    ctypes.windll.kernel32.SetFileAttributesW(str(file_path), new_attrs)
            else:
                os.chmod(file_path, 0o600)  # Read/Write only for owner
        except Exception:
            pass

    @classmethod
    def _get_connection(cls) -> sqlite3.Connection:
        """Returns a database connection configured with WAL mode."""
        DB_FILE.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(DB_FILE), timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    @classmethod
    def init_db(cls):
        """Initializes database schema and secures file permissions on disk."""
        with cls._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS files_state (
                    file_id TEXT PRIMARY KEY,
                    original_path TEXT UNIQUE NOT NULL,
                    hcs_path TEXT,
                    file_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    file_size INTEGER DEFAULT 0,
                    hcs_size INTEGER DEFAULT 0,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
            """)
            conn.commit()

        # Apply persistent OS security to both DB and WAL journal files
        cls._apply_file_security(DB_FILE)
        wal_file = DB_FILE.with_name("state.db-wal")
        shm_file = DB_FILE.with_name("state.db-shm")
        if wal_file.exists():
            cls._apply_file_security(wal_file)
        if shm_file.exists():
            cls._apply_file_security(shm_file)

    @classmethod
    def register_file(cls, original_path: str, file_type: str, status: str = "QUEUED") -> str:
        """Registers a new file or updates an existing record."""
        cls.init_db()
        abs_path = os.path.abspath(original_path)
        file_size = os.path.getsize(abs_path) if os.path.exists(abs_path) else 0
        now = time.time()

        with cls._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT file_id FROM files_state WHERE original_path = ?", (abs_path,))
            row = cursor.fetchone()

            if row:
                file_id = row["file_id"]
                cursor.execute("""
                    UPDATE files_state 
                    SET status = ?, file_size = ?, updated_at = ?
                    WHERE file_id = ?
                """, (status, file_size, now, file_id))
            else:
                file_id = str(uuid.uuid4())
                cursor.execute("""
                    INSERT INTO files_state (file_id, original_path, file_type, status, file_size, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (file_id, abs_path, file_type, status, file_size, now, now))

            conn.commit()
            return file_id

    @classmethod
    def update_status(cls, original_path: str, status: str, hcs_path: Optional[str] = None):
        """Updates lifecycle state and generated container metadata."""
        cls.init_db()
        abs_path = os.path.abspath(original_path)
        now = time.time()
        hcs_size = os.path.getsize(hcs_path) if hcs_path and os.path.exists(hcs_path) else 0

        with cls._get_connection() as conn:
            if hcs_path:
                conn.execute("""
                    UPDATE files_state 
                    SET status = ?, hcs_path = ?, hcs_size = ?, updated_at = ?
                    WHERE original_path = ?
                """, (status, os.path.abspath(hcs_path), hcs_size, now, abs_path))
            else:
                conn.execute("""
                    UPDATE files_state 
                    SET status = ?, updated_at = ?
                    WHERE original_path = ?
                """, (status, now, abs_path))
            conn.commit()
            
    @classmethod
    def get_queue_metrics(cls) -> Dict[str, int]:
        """Queries SQLite DB for active pending and processing counts across processes."""
        cls.init_db()
        try:
            with cls._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT
                        SUM(CASE WHEN status = 'QUEUED' THEN 1 ELSE 0 END) as pending,
                        SUM(CASE WHEN status = 'PROCESSING' THEN 1 ELSE 0 END) as processing
                    FROM files_state
                """)
                row = cursor.fetchone()
                pending = row["pending"] if row and row["pending"] is not None else 0
                processing = row["processing"] if row and row["processing"] is not None else 0
                return {"pending": pending, "processing": processing}
        except Exception:
            return {"pending": 0, "processing": 0}

    @classmethod
    def recover_interrupted_states(cls) -> int:
        """Self-healing: Resets any stranded PROCESSING states back to QUEUED after power loss."""
        cls.init_db()
        now = time.time()
        with cls._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE files_state 
                SET status = 'QUEUED', updated_at = ?
                WHERE status = 'PROCESSING'
            """, (now,))
            recovered_count = cursor.rowcount
            conn.commit()
            return recovered_count

    @classmethod
    def get_all_records(cls) -> List[Dict[str, Any]]:
        """Returns all tracked records for internal query auditing."""
        cls.init_db()
        with cls._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM files_state ORDER BY updated_at DESC")
            return [dict(row) for row in cursor.fetchall()]