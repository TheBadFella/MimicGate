"""Durable browser-thread routing for OpenAI-compatible conversations."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3
import threading
import time
from typing import Any, Iterator


@dataclass(frozen=True, slots=True)
class ConversationRoute:
    project_key: str
    app_key: str
    conversation_key: str
    thread_id: str
    transcript: tuple[dict[str, Any], ...]
    message_hashes: tuple[str, ...]
    contract_hash: str
    revision: int
    created_at: float
    updated_at: float


@dataclass(frozen=True, slots=True)
class ResponseRoute:
    response_id: str
    project_key: str
    app_key: str
    conversation_key: str
    revision: int
    transcript: tuple[dict[str, Any], ...]
    message_hashes: tuple[str, ...]
    created_at: float


class ConversationStore:
    """Small SQLite ledger mapping logical conversations to browser threads."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._lock, self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversation_routes (
                    project_key TEXT NOT NULL,
                    app_key TEXT NOT NULL,
                    conversation_key TEXT NOT NULL,
                    thread_id TEXT NOT NULL,
                    transcript_json TEXT NOT NULL DEFAULT '[]',
                    message_hashes_json TEXT NOT NULL DEFAULT '[]',
                    contract_hash TEXT NOT NULL DEFAULT '',
                    revision INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY (project_key, app_key, conversation_key)
                );
                CREATE TABLE IF NOT EXISTS response_routes (
                    response_id TEXT PRIMARY KEY,
                    project_key TEXT NOT NULL,
                    app_key TEXT NOT NULL,
                    conversation_key TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    transcript_json TEXT NOT NULL DEFAULT '[]',
                    message_hashes_json TEXT NOT NULL DEFAULT '[]',
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS response_routes_conversation_idx
                ON response_routes(project_key, app_key, conversation_key);
                """
            )

    @staticmethod
    def _decode_list(value: str) -> tuple[Any, ...]:
        try:
            decoded = json.loads(value)
        except (TypeError, ValueError):
            return ()
        return tuple(decoded) if isinstance(decoded, list) else ()

    @classmethod
    def _route_from_row(cls, row: sqlite3.Row | None) -> ConversationRoute | None:
        if row is None:
            return None
        return ConversationRoute(
            project_key=row["project_key"], app_key=row["app_key"],
            conversation_key=row["conversation_key"], thread_id=row["thread_id"],
            transcript=cls._decode_list(row["transcript_json"]),
            message_hashes=cls._decode_list(row["message_hashes_json"]),
            contract_hash=row["contract_hash"], revision=int(row["revision"]),
            created_at=float(row["created_at"]), updated_at=float(row["updated_at"]),
        )

    def get_route(self, project_key: str, app_key: str, conversation_key: str) -> ConversationRoute | None:
        with self._lock, self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM conversation_routes WHERE project_key=? AND app_key=? AND conversation_key=?",
                (project_key, app_key, conversation_key),
            ).fetchone()
        return self._route_from_row(row)

    def save_route(
        self, *, project_key: str, app_key: str, conversation_key: str,
        thread_id: str, transcript: list[dict[str, Any]] | tuple[dict[str, Any], ...],
        message_hashes: list[str] | tuple[str, ...], contract_hash: str,
    ) -> ConversationRoute:
        now = time.time()
        with self._lock, self._connection() as connection:
            existing = connection.execute(
                "SELECT revision, created_at FROM conversation_routes WHERE project_key=? AND app_key=? AND conversation_key=?",
                (project_key, app_key, conversation_key),
            ).fetchone()
            revision = int(existing["revision"]) + 1 if existing else 1
            created_at = float(existing["created_at"]) if existing else now
            connection.execute(
                """
                INSERT INTO conversation_routes(project_key,app_key,conversation_key,thread_id,
                    transcript_json,message_hashes_json,contract_hash,revision,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(project_key,app_key,conversation_key) DO UPDATE SET
                    thread_id=excluded.thread_id, transcript_json=excluded.transcript_json,
                    message_hashes_json=excluded.message_hashes_json, contract_hash=excluded.contract_hash,
                    revision=excluded.revision, updated_at=excluded.updated_at
                """,
                (project_key, app_key, conversation_key, thread_id,
                 json.dumps(list(transcript), ensure_ascii=False, separators=(",", ":")),
                 json.dumps(list(message_hashes), separators=(",", ":")), contract_hash,
                 revision, created_at, now),
            )
        route = self.get_route(project_key, app_key, conversation_key)
        if route is None:
            raise RuntimeError("Conversation route was not persisted")
        return route

    def delete_route(self, project_key: str, app_key: str, conversation_key: str) -> None:
        with self._lock, self._connection() as connection:
            connection.execute(
                "DELETE FROM conversation_routes WHERE project_key=? AND app_key=? AND conversation_key=?",
                (project_key, app_key, conversation_key),
            )

    def save_response(self, response_id: str, route: ConversationRoute) -> None:
        with self._lock, self._connection() as connection:
            connection.execute(
                """INSERT OR REPLACE INTO response_routes(response_id,project_key,app_key,
                conversation_key,revision,transcript_json,message_hashes_json,created_at)
                VALUES(?,?,?,?,?,?,?,?)""",
                (response_id, route.project_key, route.app_key, route.conversation_key,
                 route.revision, json.dumps(list(route.transcript), ensure_ascii=False),
                 json.dumps(list(route.message_hashes)), time.time()),
            )

    def get_response(self, response_id: str) -> ResponseRoute | None:
        with self._lock, self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM response_routes WHERE response_id=?", (response_id,)
            ).fetchone()
        if row is None:
            return None
        return ResponseRoute(
            response_id=row["response_id"], project_key=row["project_key"], app_key=row["app_key"],
            conversation_key=row["conversation_key"], revision=int(row["revision"]),
            transcript=self._decode_list(row["transcript_json"]),
            message_hashes=self._decode_list(row["message_hashes_json"]),
            created_at=float(row["created_at"]),
        )

    def prune(self, *, retention_seconds: int, max_routes: int) -> None:
        """Bound plaintext transcript retention by age and route count."""
        cutoff = time.time() - max(0, retention_seconds)
        with self._lock, self._connection() as connection:
            connection.execute("DELETE FROM response_routes WHERE created_at < ?", (cutoff,))
            connection.execute("DELETE FROM conversation_routes WHERE updated_at < ?", (cutoff,))
            overflow = connection.execute(
                "SELECT COUNT(*) FROM conversation_routes"
            ).fetchone()[0] - max(1, max_routes)
            if overflow > 0:
                victims = connection.execute(
                    "SELECT project_key,app_key,conversation_key FROM conversation_routes ORDER BY updated_at ASC LIMIT ?",
                    (overflow,),
                ).fetchall()
                for victim in victims:
                    connection.execute(
                        "DELETE FROM conversation_routes WHERE project_key=? AND app_key=? AND conversation_key=?",
                        tuple(victim),
                    )
