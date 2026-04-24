"""
BNP Database Module
====================
Normalized SQLite database for conversation logging, AI session tracking,
and persistent memory storage.

Architecture Principle:
    AI_SKILLS.md  →  STATIC SYSTEM RULES / PROMPT CONFIG
    DATABASE       →  REAL DATA STORAGE (this module)
"""

import os
import sqlite3
import uuid
import time
from datetime import datetime
from typing import Optional, List, Dict, Any
from threading import Lock

# Database path (same directory as project root)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "bane_data.db")

_db_lock = Lock()


def _get_connection() -> sqlite3.Connection:
    """Get a thread-safe database connection."""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_database() -> None:
    """Initialize all database tables. Safe to call multiple times."""
    with _db_lock:
        conn = _get_connection()
        try:
            conn.executescript("""
                -- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                -- TABLE: users
                -- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                CREATE TABLE IF NOT EXISTS users (
                    user_id         TEXT PRIMARY KEY,
                    platform        TEXT NOT NULL,
                    platform_user_id TEXT NOT NULL,
                    username        TEXT,
                    created_at      TEXT DEFAULT (datetime('now'))
                );

                -- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                -- TABLE: conversations
                -- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                CREATE TABLE IF NOT EXISTS conversations (
                    conversation_id TEXT PRIMARY KEY,
                    user_id         TEXT NOT NULL,
                    source_platform TEXT NOT NULL,
                    started_at      TEXT DEFAULT (datetime('now')),
                    last_active_at  TEXT DEFAULT (datetime('now')),
                    status          TEXT DEFAULT 'active',
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                );

                -- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                -- TABLE: messages
                -- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                CREATE TABLE IF NOT EXISTS messages (
                    message_id      TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    sender_type     TEXT NOT NULL CHECK(sender_type IN ('USER', 'AI', 'SYSTEM')),
                    message_content TEXT NOT NULL,
                    timestamp       TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id)
                );

                -- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                -- TABLE: ai_sessions
                -- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                CREATE TABLE IF NOT EXISTS ai_sessions (
                    session_id      TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    ai_model        TEXT NOT NULL,
                    request_time    TEXT NOT NULL,
                    response_time   TEXT,
                    latency_ms      REAL,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id)
                );

                -- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                -- TABLE: sources
                -- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                CREATE TABLE IF NOT EXISTS sources (
                    source_id   TEXT PRIMARY KEY,
                    session_id  TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_name TEXT,
                    FOREIGN KEY (session_id) REFERENCES ai_sessions(session_id)
                );

                -- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                -- TABLE: knowledge_memory (Phase 7)
                -- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                CREATE TABLE IF NOT EXISTS knowledge_memory (
                    memory_id        TEXT PRIMARY KEY,
                    topic            TEXT NOT NULL,
                    summary          TEXT NOT NULL,
                    importance_score INTEGER DEFAULT 5,
                    created_at       TEXT DEFAULT (datetime('now'))
                );

                -- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                -- INDEXES for performance
                -- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id);
                CREATE INDEX IF NOT EXISTS idx_messages_time ON messages(timestamp);
                CREATE INDEX IF NOT EXISTS idx_conv_user ON conversations(user_id);
                CREATE INDEX IF NOT EXISTS idx_sessions_conv ON ai_sessions(conversation_id);
            """)
            conn.commit()

            # ── Schema Migration: add chrome_profile column if missing ──
            existing = [row[1] for row in conn.execute("PRAGMA table_info(conversations)").fetchall()]
            if "chrome_profile" not in existing:
                conn.execute("ALTER TABLE conversations ADD COLUMN chrome_profile TEXT DEFAULT ''")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_conv_profile ON conversations(chrome_profile)")
                conn.commit()
        finally:
            conn.close()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# USER OPERATIONS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def ensure_user(platform: str, platform_user_id: str, username: Optional[str] = None) -> str:
    """Create or retrieve a user. Returns the internal user_id."""
    with _db_lock:
        conn = _get_connection()
        try:
            row = conn.execute(
                "SELECT user_id FROM users WHERE platform = ? AND platform_user_id = ?",
                (platform, str(platform_user_id))
            ).fetchone()

            if row:
                return row["user_id"]

            user_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO users (user_id, platform, platform_user_id, username) VALUES (?, ?, ?, ?)",
                (user_id, platform, str(platform_user_id), username)
            )
            conn.commit()
            return user_id
        finally:
            conn.close()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONVERSATION OPERATIONS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_or_create_conversation(
    user_id: str,
    source_platform: str,
    timeout_minutes: int = 30,
    chrome_profile: str = ""
) -> str:
    """
    Get the active conversation for a user+profile or create a new one.
    A conversation is 'stale' after timeout_minutes of inactivity.
    Each unique chrome_profile maintains its own isolated conversation context.
    """
    with _db_lock:
        conn = _get_connection()
        try:
            cutoff = datetime.utcnow().isoformat()
            row = conn.execute(
                """SELECT conversation_id, last_active_at FROM conversations
                   WHERE user_id = ? AND source_platform = ? AND chrome_profile = ? AND status = 'active'
                   ORDER BY last_active_at DESC LIMIT 1""",
                (user_id, source_platform, chrome_profile)
            ).fetchone()

            if row:
                last_active = datetime.fromisoformat(row["last_active_at"])
                elapsed = (datetime.utcnow() - last_active).total_seconds() / 60
                if elapsed < timeout_minutes:
                    # Update activity timestamp
                    conn.execute(
                        "UPDATE conversations SET last_active_at = ? WHERE conversation_id = ?",
                        (cutoff, row["conversation_id"])
                    )
                    conn.commit()
                    return row["conversation_id"]
                else:
                    # Mark old conversation as closed
                    conn.execute(
                        "UPDATE conversations SET status = 'closed' WHERE conversation_id = ?",
                        (row["conversation_id"],)
                    )

            # Create new conversation
            conv_id = str(uuid.uuid4())
            conn.execute(
                """INSERT INTO conversations
                   (conversation_id, user_id, source_platform, chrome_profile)
                   VALUES (?, ?, ?, ?)""",
                (conv_id, user_id, source_platform, chrome_profile)
            )
            conn.commit()
            return conv_id
        finally:
            conn.close()


def get_profile_conversations(
    user_id: str,
    chrome_profile: str,
    limit: int = 20
) -> List[Dict[str, Any]]:
    """Retrieve recent conversations for a specific chrome profile."""
    with _db_lock:
        conn = _get_connection()
        try:
            rows = conn.execute(
                """SELECT conversation_id, source_platform, started_at, last_active_at, status
                   FROM conversations
                   WHERE user_id = ? AND chrome_profile = ?
                   ORDER BY last_active_at DESC
                   LIMIT ?""",
                (user_id, chrome_profile, limit)
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()



# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MESSAGE OPERATIONS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def save_message(conversation_id: str, sender_type: str, content: str) -> str:
    """Save a message to the database. Returns message_id."""
    with _db_lock:
        conn = _get_connection()
        try:
            msg_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO messages (message_id, conversation_id, sender_type, message_content) VALUES (?, ?, ?, ?)",
                (msg_id, conversation_id, sender_type.upper(), content)
            )
            conn.commit()
            return msg_id
        finally:
            conn.close()


def get_recent_messages(conversation_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Retrieve the most recent messages for a conversation (for context building)."""
    with _db_lock:
        conn = _get_connection()
        try:
            rows = conn.execute(
                """SELECT sender_type, message_content, timestamp
                   FROM messages
                   WHERE conversation_id = ?
                   ORDER BY timestamp DESC
                   LIMIT ?""",
                (conversation_id, limit)
            ).fetchall()
            # Return in chronological order (oldest first)
            return [dict(r) for r in reversed(rows)]
        finally:
            conn.close()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AI SESSION OPERATIONS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def create_ai_session(conversation_id: str, ai_model: str) -> str:
    """Create an AI session record. Returns session_id."""
    with _db_lock:
        conn = _get_connection()
        try:
            session_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO ai_sessions (session_id, conversation_id, ai_model, request_time) VALUES (?, ?, ?, ?)",
                (session_id, conversation_id, ai_model, datetime.utcnow().isoformat())
            )
            conn.commit()
            return session_id
        finally:
            conn.close()


def complete_ai_session(session_id: str, request_start: float) -> None:
    """Mark an AI session as complete with latency data."""
    latency = (time.time() - request_start) * 1000  # ms
    with _db_lock:
        conn = _get_connection()
        try:
            conn.execute(
                "UPDATE ai_sessions SET response_time = ?, latency_ms = ? WHERE session_id = ?",
                (datetime.utcnow().isoformat(), round(latency, 2), session_id)
            )
            conn.commit()
        finally:
            conn.close()


def log_source(session_id: str, source_type: str, source_name: Optional[str] = None) -> None:
    """Log which AI source handled the request."""
    with _db_lock:
        conn = _get_connection()
        try:
            conn.execute(
                "INSERT INTO sources (source_id, session_id, source_type, source_name) VALUES (?, ?, ?, ?)",
                (str(uuid.uuid4()), session_id, source_type, source_name)
            )
            conn.commit()
        finally:
            conn.close()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# KNOWLEDGE MEMORY (Phase 7 — Optional)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def save_memory(topic: str, summary: str, importance: int = 5) -> str:
    """Store a piece of knowledge for long-term memory."""
    with _db_lock:
        conn = _get_connection()
        try:
            mem_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO knowledge_memory (memory_id, topic, summary, importance_score) VALUES (?, ?, ?, ?)",
                (mem_id, topic, summary, importance)
            )
            conn.commit()
            return mem_id
        finally:
            conn.close()


def search_memory(keyword: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Search knowledge memory by keyword."""
    with _db_lock:
        conn = _get_connection()
        try:
            rows = conn.execute(
                """SELECT topic, summary, importance_score, created_at
                   FROM knowledge_memory
                   WHERE topic LIKE ? OR summary LIKE ?
                   ORDER BY importance_score DESC, created_at DESC
                   LIMIT ?""",
                (f"%{keyword}%", f"%{keyword}%", limit)
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# STATISTICS / ANALYTICS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_stats() -> Dict[str, Any]:
    """Get pipeline statistics."""
    with _db_lock:
        conn = _get_connection()
        try:
            total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            total_convos = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
            total_messages = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
            total_sessions = conn.execute("SELECT COUNT(*) FROM ai_sessions").fetchone()[0]
            avg_latency = conn.execute("SELECT AVG(latency_ms) FROM ai_sessions WHERE latency_ms IS NOT NULL").fetchone()[0]

            return {
                "total_users": total_users,
                "total_conversations": total_convos,
                "total_messages": total_messages,
                "total_ai_sessions": total_sessions,
                "avg_latency_ms": round(avg_latency, 2) if avg_latency else 0
            }
        finally:
            conn.close()
