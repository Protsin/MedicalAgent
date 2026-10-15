"""SQLite persistence for consultation sessions."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3
import threading
from typing import Any
import uuid
from datetime import datetime, timezone

from .triage import Urgency

SCHEMA_VERSION = 1


class NotFoundError(LookupError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


@dataclass(frozen=True)
class Session:
    id: str
    patient_alias: str
    age_years: int | None
    sex: str
    urgency: str
    departments: list[str]
    created_at: str
    updated_at: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "patient_alias": self.patient_alias,
            "age_years": self.age_years,
            "sex": self.sex,
            "urgency": self.urgency,
            "departments": self.departments,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class Message:
    id: int
    session_id: str
    role: str
    content: str
    triage: dict[str, Any] | None
    created_at: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "role": self.role,
            "content": self.content,
            "triage": self.triage,
            "created_at": self.created_at,
        }


class Store:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self._connection: sqlite3.Connection | None = None
        self._lock = threading.RLock()
        self.initialize()

    def initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    patient_alias TEXT NOT NULL,
                    age_years INTEGER,
                    sex TEXT NOT NULL,
                    urgency TEXT NOT NULL,
                    departments_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    role TEXT NOT NULL CHECK(role IN ('user','assistant','system')),
                    content TEXT NOT NULL,
                    triage_json TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_messages_session
                    ON messages(session_id, id);
                """
            )
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def close(self) -> None:
        with self._lock:
            self._close_unlocked()

    def _close_unlocked(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def _connect(self) -> sqlite3.Connection:
        if self._connection is None:
            self._connection = sqlite3.connect(self.path, check_same_thread=False)
            self._connection.row_factory = sqlite3.Row
            self._connection.execute("PRAGMA foreign_keys = ON")
        return self._connection

    @staticmethod
    def _session_from_row(row: sqlite3.Row) -> Session:
        return Session(
            id=row["id"],
            patient_alias=row["patient_alias"],
            age_years=row["age_years"],
            sex=row["sex"],
            urgency=row["urgency"],
            departments=json.loads(row["departments_json"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def create_session(
        self,
        patient_alias: str = "未命名访客",
        age_years: int | None = None,
        sex: str = "unknown",
    ) -> Session:
        if age_years is not None and not (0 <= age_years <= 120):
            raise ValueError("age_years must be between 0 and 120")
        if sex not in {"male", "female", "other", "unknown"}:
            raise ValueError("invalid sex value")
        if not patient_alias.strip():
            raise ValueError("patient_alias cannot be empty")
        now = utc_now()
        session = Session(
            id=uuid.uuid4().hex,
            patient_alias=patient_alias.strip()[:80],
            age_years=age_years,
            sex=sex,
            urgency=Urgency.INFO_NEEDED.value,
            departments=[],
            created_at=now,
            updated_at=now,
        )
        with self._lock, self._connect() as connection:
            connection.execute(
                """INSERT INTO sessions
                   (id, patient_alias, age_years, sex, urgency, departments_json, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    session.id,
                    session.patient_alias,
                    session.age_years,
                    session.sex,
                    session.urgency,
                    json.dumps(session.departments, ensure_ascii=False),
                    session.created_at,
                    session.updated_at,
                ),
            )
        return session

    def list_sessions(self, limit: int = 50) -> list[Session]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM sessions ORDER BY updated_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._session_from_row(row) for row in rows]

    def get_session(self, session_id: str) -> Session:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
        if row is None:
            raise NotFoundError("session not found")
        return self._session_from_row(row)

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        triage: dict[str, Any] | None = None,
    ) -> Message:
        if role not in {"user", "assistant", "system"}:
            raise ValueError("invalid message role")
        self.get_session(session_id)
        created_at = utc_now()
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                """INSERT INTO messages (session_id, role, content, triage_json, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    session_id,
                    role,
                    content,
                    json.dumps(triage, ensure_ascii=False) if triage is not None else None,
                    created_at,
                ),
            )
            message_id = int(cursor.lastrowid)
            connection.execute(
                "UPDATE sessions SET updated_at = ? WHERE id = ?", (created_at, session_id)
            )
        return Message(
            id=message_id,
            session_id=session_id,
            role=role,
            content=content,
            triage=triage,
            created_at=created_at,
        )

    def update_triage(self, session_id: str, urgency: str, departments: list[str]) -> Session:
        # Ensure the session exists before writing.
        self.get_session(session_id)
        with self._lock, self._connect() as connection:
            connection.execute(
                "UPDATE sessions SET urgency = ?, departments_json = ?, updated_at = ? WHERE id = ?",
                (urgency, json.dumps(departments, ensure_ascii=False), utc_now(), session_id),
            )
        return self.get_session(session_id)

    def list_messages(self, session_id: str) -> list[Message]:
        self.get_session(session_id)
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM messages WHERE session_id = ? ORDER BY id", (session_id,)
            ).fetchall()
        return [
            Message(
                id=row["id"],
                session_id=row["session_id"],
                role=row["role"],
                content=row["content"],
                triage=json.loads(row["triage_json"]) if row["triage_json"] else None,
                created_at=row["created_at"],
            )
            for row in rows
        ]
