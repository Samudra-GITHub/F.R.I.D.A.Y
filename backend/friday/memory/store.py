"""Persistent, user-controlled memory for W.E.D.N.E.S.D.A.Y.

SQLite for records, FTS5 for keyword retrieval (no vector or graph database). Every record
carries provenance (``source_kind``) instead of an invented confidence score. Deleting a
memory purges its content and search-index entry and leaves a tombstone, so the record
cannot silently reappear from re-indexing.

Only the authenticated desktop UI writes memories; the model has no memory-writing tool.
"""

import re
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

MEMORY_KINDS = ("preference", "profile", "project", "decision", "procedure", "fact")
SOURCE_KINDS = ("explicit_user_statement", "user_correction", "imported", "model_suggestion")
MAX_CONTENT_CHARS = 1000

_SCHEMA = """
PRAGMA journal_mode = WAL;
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    content TEXT NOT NULL,
    scope TEXT NOT NULL DEFAULT 'personal',
    source_kind TEXT NOT NULL,
    source_reference TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    expires_at TEXT
);
CREATE VIRTUAL TABLE IF NOT EXISTS memory_search USING fts5(
    content, memory_id UNINDEXED, tokenize = 'porter unicode61'
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class MemoryStore:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(db_path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(_SCHEMA)
        self._db.commit()

    def close(self) -> None:
        with self._lock:
            self._db.close()

    @staticmethod
    def _row(row: sqlite3.Row) -> Dict[str, Any]:
        return {key: row[key] for key in row.keys()}

    @staticmethod
    def _validate(kind: Optional[str], content: Optional[str], source_kind: Optional[str]) -> None:
        if kind is not None and kind not in MEMORY_KINDS:
            raise ValueError(f"Unknown memory kind '{kind}'. Allowed: {', '.join(MEMORY_KINDS)}")
        if source_kind is not None and source_kind not in SOURCE_KINDS:
            raise ValueError(f"Unknown source kind '{source_kind}'")
        if content is not None:
            if not content.strip():
                raise ValueError("Memory content cannot be empty")
            if len(content) > MAX_CONTENT_CHARS:
                raise ValueError(f"Memory content exceeds {MAX_CONTENT_CHARS} characters")

    def _expire(self) -> None:
        now = _now()
        expired = self._db.execute(
            "SELECT id FROM memories WHERE status = 'active' AND expires_at IS NOT NULL AND expires_at <= ?",
            (now,),
        ).fetchall()
        for row in expired:
            self._tombstone(row["id"], "expired")

    def _tombstone(self, memory_id: str, status: str) -> None:
        self._db.execute("DELETE FROM memory_search WHERE memory_id = ?", (memory_id,))
        self._db.execute(
            "UPDATE memories SET content = '', status = ?, updated_at = ? WHERE id = ?",
            (status, _now(), memory_id),
        )

    def create(
        self,
        kind: str,
        content: str,
        source_kind: str = "explicit_user_statement",
        scope: str = "personal",
        source_reference: Optional[str] = None,
        expires_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        self._validate(kind, content, source_kind)
        memory_id = f"mem_{uuid.uuid4().hex[:12]}"
        now = _now()
        with self._lock:
            self._db.execute(
                "INSERT INTO memories (id, kind, content, scope, source_kind, source_reference, status, created_at, updated_at, expires_at)"
                " VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)",
                (memory_id, kind, content.strip(), scope[:64], source_kind, source_reference, now, now, expires_at),
            )
            self._db.execute("INSERT INTO memory_search (content, memory_id) VALUES (?, ?)", (content.strip(), memory_id))
            self._db.commit()
            return self.get(memory_id)  # type: ignore[return-value]

    def get(self, memory_id: str) -> Optional[Dict[str, Any]]:
        row = self._db.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
        return self._row(row) if row else None

    def list(self, include_deleted: bool = False, limit: int = 200) -> List[Dict[str, Any]]:
        with self._lock:
            self._expire()
            self._db.commit()
            sql = "SELECT * FROM memories"
            if not include_deleted:
                sql += " WHERE status = 'active'"
            sql += " ORDER BY updated_at DESC LIMIT ?"
            return [self._row(r) for r in self._db.execute(sql, (limit,)).fetchall()]

    def update(self, memory_id: str, content: Optional[str] = None, kind: Optional[str] = None) -> Optional[Dict[str, Any]]:
        self._validate(kind, content, None)
        with self._lock:
            current = self.get(memory_id)
            if not current or current["status"] != "active":
                return None
            new_content = content.strip() if content is not None else current["content"]
            self._db.execute(
                "UPDATE memories SET content = ?, kind = ?, source_kind = ?, updated_at = ? WHERE id = ?",
                (
                    new_content,
                    kind or current["kind"],
                    "user_correction" if content is not None else current["source_kind"],
                    _now(),
                    memory_id,
                ),
            )
            self._db.execute("DELETE FROM memory_search WHERE memory_id = ?", (memory_id,))
            self._db.execute("INSERT INTO memory_search (content, memory_id) VALUES (?, ?)", (new_content, memory_id))
            self._db.commit()
            return self.get(memory_id)

    def delete(self, memory_id: str) -> bool:
        with self._lock:
            current = self.get(memory_id)
            if not current or current["status"] != "active":
                return False
            self._tombstone(memory_id, "deleted")
            self._db.commit()
            return True

    def search(self, query: str, limit: int = 8) -> List[Dict[str, Any]]:
        """Keyword search over active memories. User syntax is reduced to quoted terms."""
        terms = re.findall(r"[\w']+", query.lower())[:12]
        if not terms:
            return []
        match = " OR ".join('"' + t.replace('"', "") + '"' for t in terms)
        with self._lock:
            self._expire()
            rows = self._db.execute(
                "SELECT m.* FROM memory_search s JOIN memories m ON m.id = s.memory_id"
                " WHERE memory_search MATCH ? AND m.status = 'active' ORDER BY s.rank LIMIT ?",
                (match, limit),
            ).fetchall()
            return [self._row(r) for r in rows]

    def context_for(self, user_text: str, limit: int = 6) -> List[Dict[str, Any]]:
        """Preferences/profile always apply; other kinds only when keyword-relevant."""
        with self._lock:
            standing = [
                self._row(r)
                for r in self._db.execute(
                    "SELECT * FROM memories WHERE status = 'active' AND kind IN ('preference', 'profile')"
                    " ORDER BY updated_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            ]
        seen = {m["id"] for m in standing}
        relevant = [m for m in self.search(user_text, limit=limit) if m["id"] not in seen]
        return (standing + relevant)[:limit]
