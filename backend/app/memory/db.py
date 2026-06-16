"""SQLite 持久化层（aiosqlite）。"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import aiosqlite

from app.memory.models import ExtractedEvent, ProfileFact

logger = logging.getLogger("pet.memory.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS user_profile (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL,
    category    TEXT NOT NULL,
    key         TEXT NOT NULL,
    value       TEXT NOT NULL,
    confidence  REAL NOT NULL DEFAULT 0.7,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(session_id, category, key)
);
CREATE INDEX IF NOT EXISTS idx_profile_session ON user_profile(session_id);

CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL,
    content     TEXT NOT NULL,
    category    TEXT NOT NULL DEFAULT 'general',
    importance  INTEGER NOT NULL DEFAULT 5,
    turn_number INTEGER,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id);
CREATE INDEX IF NOT EXISTS idx_events_importance ON events(session_id, importance DESC);

CREATE TABLE IF NOT EXISTS conversation_summaries (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL,
    summary     TEXT NOT NULL,
    turn_start  INTEGER NOT NULL,
    turn_end    INTEGER NOT NULL,
    msg_count   INTEGER NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_summaries_session ON conversation_summaries(session_id, turn_start);

CREATE TABLE IF NOT EXISTS turns (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL,
    turn_number INTEGER NOT NULL,
    user_text   TEXT NOT NULL,
    assistant_text TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_turns_session ON turns(session_id, turn_number);
"""


class MemoryDB:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._conn: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

    async def init(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self._db_path)
        self._conn.row_factory = aiosqlite.Row
        async with self._lock:
            for stmt in _SCHEMA.strip().split(";"):
                stmt = stmt.strip()
                if stmt:
                    await self._conn.execute(stmt)
            await self._conn.commit()
        logger.info("memory db opened: %s", self._db_path)

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    # ------------------------------------------------------------------
    # user_profile
    # ------------------------------------------------------------------

    async def upsert_profile_fact(
        self, session_id: str, fact: ProfileFact, turn_number: int | None = None
    ) -> None:
        async with self._lock:
            await self._conn.execute(  # type: ignore[union-attr]
                """
                INSERT INTO user_profile(session_id, category, key, value, confidence, updated_at)
                VALUES (?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(session_id, category, key)
                DO UPDATE SET value=excluded.value,
                              confidence=excluded.confidence,
                              updated_at=excluded.updated_at
                """,
                (session_id, fact.category, fact.key, fact.value, fact.confidence),
            )
            await self._conn.commit()  # type: ignore[union-attr]

    async def get_profile(self, session_id: str) -> list[dict[str, Any]]:
        async with self._conn.execute(  # type: ignore[union-attr]
            "SELECT category, key, value, confidence FROM user_profile WHERE session_id=? ORDER BY category, key",
            (session_id,),
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # events
    # ------------------------------------------------------------------

    async def add_event(
        self, session_id: str, event: ExtractedEvent, turn_number: int | None = None
    ) -> None:
        async with self._lock:
            await self._conn.execute(  # type: ignore[union-attr]
                """
                INSERT INTO events(session_id, content, category, importance, turn_number)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, event.content, event.category, event.importance, turn_number),
            )
            await self._conn.commit()  # type: ignore[union-attr]

    async def get_top_events(
        self, session_id: str, limit: int = 10, min_importance: int = 1
    ) -> list[dict[str, Any]]:
        async with self._conn.execute(  # type: ignore[union-attr]
            """
            SELECT content, category, importance, created_at
            FROM events
            WHERE session_id=? AND importance >= ?
            ORDER BY importance DESC, id DESC
            LIMIT ?
            """,
            (session_id, min_importance, limit),
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # conversation_summaries
    # ------------------------------------------------------------------

    async def add_summary(
        self,
        session_id: str,
        summary: str,
        turn_start: int,
        turn_end: int,
        msg_count: int,
    ) -> None:
        async with self._lock:
            await self._conn.execute(  # type: ignore[union-attr]
                """
                INSERT INTO conversation_summaries(session_id, summary, turn_start, turn_end, msg_count)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, summary, turn_start, turn_end, msg_count),
            )
            await self._conn.commit()  # type: ignore[union-attr]

    async def get_summaries(self, session_id: str) -> list[dict[str, Any]]:
        async with self._conn.execute(  # type: ignore[union-attr]
            "SELECT summary, turn_start, turn_end FROM conversation_summaries WHERE session_id=? ORDER BY turn_start",
            (session_id,),
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # turns
    # ------------------------------------------------------------------

    async def add_turn(
        self, session_id: str, turn_number: int, user_text: str, assistant_text: str
    ) -> None:
        async with self._lock:
            await self._conn.execute(  # type: ignore[union-attr]
                """
                INSERT INTO turns(session_id, turn_number, user_text, assistant_text)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, turn_number, user_text, assistant_text),
            )
            await self._conn.commit()  # type: ignore[union-attr]

    async def get_turn_count(self, session_id: str) -> int:
        async with self._conn.execute(  # type: ignore[union-attr]
            "SELECT COUNT(*) FROM turns WHERE session_id=?", (session_id,)
        ) as cur:
            row = await cur.fetchone()
        return row[0] if row else 0
