import os
import sqlite3
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, List, Optional


def _utc_now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _ensure_dir(path: str) -> None:
    parent = os.path.dirname(path)
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)


def _dump_payload(payload: Any) -> str:
    if payload is None:
        return ""
    try:
        return json.dumps(payload, ensure_ascii=False)
    except Exception:
        return ""


def _load_payload(payload_json: str | None) -> Any:
    text = str(payload_json or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        return None


@dataclass(frozen=True)
class Conversation:
    id: str
    title: str
    created_at: str
    updated_at: str
    memory_summary: str


@dataclass(frozen=True)
class Message:
    id: str
    conversation_id: str
    role: str
    content: str
    created_at: str
    payload: Any = None


class AgentStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        _ensure_dir(self.db_path)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                  id TEXT PRIMARY KEY,
                  title TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  memory_summary TEXT NOT NULL DEFAULT ''
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                  id TEXT PRIMARY KEY,
                  conversation_id TEXT NOT NULL,
                  role TEXT NOT NULL,
                  content TEXT NOT NULL,
                  payload_json TEXT NOT NULL DEFAULT '',
                  created_at TEXT NOT NULL,
                  FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
                );
                """
            )
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(messages)").fetchall()}
            if "payload_json" not in columns:
                conn.execute("ALTER TABLE messages ADD COLUMN payload_json TEXT NOT NULL DEFAULT ''")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_messages_conv_time ON messages(conversation_id, created_at);"
            )

    def create_conversation(self, conv_id: str, title: str) -> Conversation:
        now = _utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO conversations(id, title, created_at, updated_at, memory_summary) VALUES(?,?,?,?,?)",
                (conv_id, title, now, now, ""),
            )
        return Conversation(id=conv_id, title=title, created_at=now, updated_at=now, memory_summary="")

    def get_conversation(self, conv_id: str) -> Optional[Conversation]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM conversations WHERE id = ?", (conv_id,)).fetchone()
        if not row:
            return None
        return Conversation(
            id=row["id"],
            title=row["title"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            memory_summary=row["memory_summary"] or "",
        )

    def list_conversations(self, limit: int = 50, offset: int = 0) -> List[Conversation]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM conversations ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [
            Conversation(
                id=r["id"],
                title=r["title"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
                memory_summary=r["memory_summary"] or "",
            )
            for r in rows
        ]

    def update_memory_summary(self, conv_id: str, memory_summary: str) -> None:
        now = _utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                "UPDATE conversations SET memory_summary = ?, updated_at = ? WHERE id = ?",
                (memory_summary, now, conv_id),
            )

    def update_conversation_title(self, conv_id: str, title: str) -> Optional[Conversation]:
        now = _utc_now_iso()
        clean_title = (title or "").strip() or "新对话"
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
                (clean_title, now, conv_id),
            )
            if cur.rowcount <= 0:
                return None
        return self.get_conversation(conv_id)

    def delete_conversation(self, conv_id: str) -> bool:
        with self._connect() as conn:
            conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conv_id,))
            cur = conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
            return cur.rowcount > 0

    def append_message(self, msg_id: str, conv_id: str, role: str, content: str, payload: Any = None) -> Message:
        now = _utc_now_iso()
        payload_json = _dump_payload(payload)
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO messages(id, conversation_id, role, content, payload_json, created_at) VALUES(?,?,?,?,?,?)",
                (msg_id, conv_id, role, content, payload_json, now),
            )
            conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conv_id))
        return Message(id=msg_id, conversation_id=conv_id, role=role, content=content, created_at=now, payload=payload)

    def list_messages(self, conv_id: str, limit: int = 200, offset: int = 0) -> List[Message]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM messages
                WHERE conversation_id = ?
                ORDER BY created_at ASC
                LIMIT ? OFFSET ?
                """,
                (conv_id, limit, offset),
            ).fetchall()
        return [
            Message(
                id=r["id"],
                conversation_id=r["conversation_id"],
                role=r["role"],
                content=r["content"],
                created_at=r["created_at"],
                payload=_load_payload(r["payload_json"]),
            )
            for r in rows
        ]


_app_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_db_path = os.path.join(_app_root, "data", "agent.sqlite3")
store = AgentStore(_db_path)
