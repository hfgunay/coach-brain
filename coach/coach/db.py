"""SQLite layer: only accounts, OAuth records and reminder channels.

The student's memory (notes, tasks, session receipts) is not here. It lives in the avenoxbeyin
vault set up for each user (vault.py).
"""
from __future__ import annotations

import hashlib
import json
import hmac
import secrets
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    pw_hash TEXT NOT NULL,
    dav_pw_hash TEXT,
    lang TEXT,
    first_session REAL,
    created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS oauth_clients (
    client_id TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS oauth_pending (
    id TEXT PRIMARY KEY,
    client_id TEXT NOT NULL,
    params TEXT NOT NULL,
    expires REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS oauth_codes (
    code_hash TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    expires REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS oauth_tokens (
    token_hash TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    client_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    scopes TEXT NOT NULL,
    resource TEXT,
    expires REAL,
    created REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS oauth_tokens_user ON oauth_tokens(user_id, client_id);
-- Reminder channel (Telegram etc.): only "to whom, when, in which language"; the content comes from the vault.
CREATE TABLE IF NOT EXISTS channel_links (
    user_id TEXT NOT NULL,
    channel TEXT NOT NULL,
    target TEXT NOT NULL,
    morning TEXT NOT NULL,
    evening TEXT NOT NULL,
    timezone TEXT NOT NULL,
    lang TEXT NOT NULL,
    muted INTEGER NOT NULL DEFAULT 0,
    last_morning TEXT,
    last_evening TEXT,
    created REAL NOT NULL,
    PRIMARY KEY (user_id, channel),
    UNIQUE (channel, target)
);
CREATE TABLE IF NOT EXISTS link_codes (
    code_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    expires REAL NOT NULL
);
"""

# Columns a link may change after it is created.
LINK_FIELDS = {"morning", "evening", "timezone", "lang", "muted", "last_morning", "last_evening"}


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored or not stored.startswith("scrypt$"):
        return False
    _, salt_hex, digest_hex = stored.split("$")
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1, dklen=32)
    return hmac.compare_digest(digest.hex(), digest_hex)


class DB:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.executescript(SCHEMA)
            self._migrate()

    def _migrate(self) -> None:
        """Brings databases created by the first (Turkish-named) version up to date."""
        cols = {r["name"] for r in self._conn.execute("PRAGMA table_info(users)")}
        if "lang" not in cols:
            self._conn.execute("ALTER TABLE users ADD COLUMN lang TEXT")
        if "first_session" not in cols:
            self._conn.execute("ALTER TABLE users ADD COLUMN first_session REAL")
        tables = {r["name"] for r in self._conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        if "kanal_baglantilari" in tables:
            self._conn.execute(
                "INSERT OR IGNORE INTO channel_links (user_id, channel, target, morning, evening, timezone, lang,"
                " muted, last_morning, last_evening, created) SELECT user_id, kanal, hedef, sabah, aksam,"
                " 'Europe/Istanbul', 'tr', sessiz, son_sabah, son_aksam, created FROM kanal_baglantilari")
            self._conn.execute("DROP TABLE kanal_baglantilari")
        # The OAuth scope was "koc"; connectors added then keep working without signing in again.
        self._conn.execute("UPDATE oauth_tokens SET scopes = replace(scopes, '\"koc\"', '\"coach\"')"
                           " WHERE scopes LIKE '%\"koc\"%'")
        for row in self._conn.execute("SELECT client_id, data FROM oauth_clients WHERE data LIKE '%koc%'").fetchall():
            data = json.loads(row["data"])
            if "koc" in (data.get("scope") or "").split():
                data["scope"] = " ".join("coach" if s == "koc" else s for s in data["scope"].split())
                self._conn.execute("UPDATE oauth_clients SET data = ? WHERE client_id = ?",
                                   (json.dumps(data), row["client_id"]))
        if "baglanti_kodlari" in tables:
            self._conn.execute("DROP TABLE baglanti_kodlari")  # short-lived codes; a new one is one tap away

    def q(self, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, args).fetchall()

    def x(self, sql: str, args: tuple = ()) -> int:
        with self._lock:
            return self._conn.execute(sql, args).rowcount

    # --- users -----------------------------------------------------------
    def create_user(self, email: str, password: str, lang: str | None = None) -> str:
        user_id = uuid.uuid4().hex
        self.x("INSERT INTO users (id, email, pw_hash, lang, created) VALUES (?, ?, ?, ?, ?)",
               (user_id, email.strip().lower(), hash_password(password), lang, time.time()))
        return user_id

    def user_by_email(self, email: str) -> sqlite3.Row | None:
        rows = self.q("SELECT * FROM users WHERE email = ?", (email.strip().lower(),))
        return rows[0] if rows else None

    def user(self, user_id: str) -> sqlite3.Row | None:
        rows = self.q("SELECT * FROM users WHERE id = ?", (user_id,))
        return rows[0] if rows else None

    def mark_first_session(self, user_id: str) -> None:
        self.x("UPDATE users SET first_session = ? WHERE id = ? AND first_session IS NULL", (time.time(), user_id))

    def onboarding(self, user_id: str) -> dict[str, bool]:
        """Which getting-started steps the student has finished: connector added, first chat, Telegram."""
        user = self.user(user_id)
        return {
            "connected": bool(self.q("SELECT 1 FROM oauth_tokens WHERE user_id = ? LIMIT 1", (user_id,))),
            "chatted": bool(user and user["first_session"]),
            "telegram": bool(self.q("SELECT 1 FROM channel_links WHERE user_id = ? LIMIT 1", (user_id,))),
        }

    def login(self, email: str, password: str) -> str | None:
        row = self.user_by_email(email)
        if row is None:
            verify_password(password, hash_password("timing-equalizer"))  # don't leak whether the account exists
            return None
        return row["id"] if verify_password(password, row["pw_hash"]) else None

    def reset_dav_password(self, user_id: str) -> str:
        password = secrets.token_urlsafe(18)
        self.x("UPDATE users SET dav_pw_hash = ? WHERE id = ?", (hash_password(password), user_id))
        return password

    def dav_login(self, email: str, password: str) -> str | None:
        row = self.user_by_email(email)
        if row is None or not verify_password(password, row["dav_pw_hash"]):
            return None
        return row["id"]

    # --- reminder channels -------------------------------------------------
    def create_link_code(self, user_id: str, seconds: int = 15 * 60) -> str:
        code = secrets.token_urlsafe(24)
        self.x("INSERT INTO link_codes (code_hash, user_id, expires) VALUES (?, ?, ?)",
               (token_hash(code), user_id, time.time() + seconds))
        return code

    def use_link_code(self, code: str) -> str | None:
        """Single use: deletes the code and returns its user when it is valid."""
        with self._lock:
            row = self._conn.execute("DELETE FROM link_codes WHERE code_hash = ? AND expires > ? RETURNING user_id",
                                     (token_hash(code), time.time())).fetchone()
        return row["user_id"] if row else None

    def link(self, user_id: str, channel: str, target: str, morning: str, evening: str, timezone: str,
             lang: str, today: str, now: str) -> None:
        """Links a channel to the user. Messages whose time already passed today are not sent right away."""
        self.x("DELETE FROM channel_links WHERE channel = ? AND target = ?", (channel, target))
        self.x("INSERT OR REPLACE INTO channel_links (user_id, channel, target, morning, evening, timezone, lang,"
               " last_morning, last_evening, created) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
               (user_id, channel, target, morning, evening, timezone, lang, today if now >= morning else None,
                today if now >= evening else None, time.time()))

    def channel_link(self, channel: str, target: str) -> sqlite3.Row | None:
        rows = self.q("SELECT * FROM channel_links WHERE channel = ? AND target = ?", (channel, target))
        return rows[0] if rows else None

    def channel_links(self) -> list[sqlite3.Row]:
        return self.q("SELECT * FROM channel_links")

    def update_link(self, channel: str, target: str, **fields: Any) -> None:
        assert set(fields) <= LINK_FIELDS
        for name, value in fields.items():
            self.x(f"UPDATE channel_links SET {name} = ? WHERE channel = ? AND target = ?", (value, channel, target))

    def mark_sent(self, user_id: str, channel: str, field: str, today: str) -> None:
        assert field in ("last_morning", "last_evening")
        self.x(f"UPDATE channel_links SET {field} = ? WHERE user_id = ? AND channel = ?", (today, user_id, channel))

    def unlink(self, channel: str, target: str) -> None:
        self.x("DELETE FROM channel_links WHERE channel = ? AND target = ?", (channel, target))

    # --- OAuth -------------------------------------------------------------
    def cleanup(self) -> None:
        now = time.time()
        self.x("DELETE FROM link_codes WHERE expires < ?", (now,))
        self.x("DELETE FROM oauth_pending WHERE expires < ?", (now,))
        self.x("DELETE FROM oauth_codes WHERE expires < ?", (now,))
        self.x("DELETE FROM oauth_tokens WHERE expires IS NOT NULL AND expires < ?", (now,))
