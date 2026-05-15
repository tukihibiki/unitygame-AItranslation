import hashlib
import sqlite3
import time
import os
import logging
import threading

logger = logging.getLogger(__name__)


class TranslationCache:
    """SQLite-based persistent LRU translation cache."""

    def __init__(self, db_path: str = "./translations.db", max_entries: int = 10000):
        self._db_path = db_path
        self._max_entries = max_entries
        self._local = threading.local()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self._db_path)
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
        return self._local.conn

    def _init_db(self):
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS translations (
                source_hash TEXT PRIMARY KEY,
                source_text TEXT NOT NULL,
                translated_text TEXT NOT NULL,
                model TEXT,
                hit_count INTEGER DEFAULT 1,
                duration_ms REAL DEFAULT 0,
                created_at REAL,
                last_accessed_at REAL
            )
        """)
        # Add column if missing (migration)
        try:
            conn.execute("ALTER TABLE translations ADD COLUMN duration_ms REAL DEFAULT 0")
        except Exception:
            pass
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_last_accessed
            ON translations(last_accessed_at)
        """)
        conn.commit()

    def _hash(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

    def lookup(self, text: str) -> str | None:
        h = self._hash(text)
        conn = self._get_conn()
        row = conn.execute(
            "SELECT source_text, translated_text FROM translations WHERE source_hash = ?",
            (h,),
        ).fetchone()

        if row is None:
            return None

        stored_text, translated = row
        if stored_text != text:
            return None

        conn.execute(
            "UPDATE translations SET hit_count = hit_count + 1, last_accessed_at = ? WHERE source_hash = ?",
            (time.time(), h),
        )
        conn.commit()
        logger.debug(f"Cache HIT: '{text[:40]}...' -> '{translated[:40]}...'")
        return translated

    def store(self, source_text: str, translated_text: str, model: str = "", duration_ms: float = 0):
        h = self._hash(source_text)
        now = time.time()
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO translations
               (source_hash, source_text, translated_text, model, duration_ms, created_at, last_accessed_at)
               VALUES (?, ?, ?, ?, ?, COALESCE((SELECT created_at FROM translations WHERE source_hash=?), ?), ?)""",
            (h, source_text, translated_text, model, duration_ms, h, now, now),
        )
        conn.commit()
        self._evict_if_needed()

    def _evict_if_needed(self):
        conn = self._get_conn()
        count = conn.execute("SELECT COUNT(*) FROM translations").fetchone()[0]
        if count > self._max_entries:
            excess = count - self._max_entries + 100
            conn.execute(
                "DELETE FROM translations WHERE source_hash IN (SELECT source_hash FROM translations ORDER BY last_accessed_at ASC LIMIT ?)",
                (excess,),
            )
            conn.commit()
            logger.info(f"Cache eviction: removed {excess} oldest entries")

    def stats(self) -> dict:
        conn = self._get_conn()
        count = conn.execute("SELECT COUNT(*) FROM translations").fetchone()[0]
        total_hits = conn.execute("SELECT COALESCE(SUM(hit_count), 0) FROM translations").fetchone()[0]
        return {"entries": count, "total_hits": total_hits}

    def close(self):
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None
