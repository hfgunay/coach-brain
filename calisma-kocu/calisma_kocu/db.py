"""SQLite katmanı: yalnız kullanıcılar ve OAuth kayıtları.

Öğrencinin hafızası (notlar, görevler, oturum sonuçları) burada değil, kullanıcı başına
kurulan avenoxbeyin kasasında durur (kasa.py).
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

SEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    pw_hash TEXT NOT NULL,
    dav_pw_hash TEXT,
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
"""


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def sifre_hashle(sifre: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(sifre.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${digest.hex()}"


def sifre_dogrula(sifre: str, kayitli: str | None) -> bool:
    if not kayitli or not kayitli.startswith("scrypt$"):
        return False
    _, salt_hex, digest_hex = kayitli.split("$")
    digest = hashlib.scrypt(sifre.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1, dklen=32)
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
            self._conn.executescript(SEMA)

    def q(self, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, args).fetchall()

    def x(self, sql: str, args: tuple = ()) -> int:
        with self._lock:
            return self._conn.execute(sql, args).rowcount

    # --- kullanıcılar -------------------------------------------------
    def kullanici_olustur(self, email: str, sifre: str) -> str:
        user_id = uuid.uuid4().hex
        self.x("INSERT INTO users (id, email, pw_hash, created) VALUES (?, ?, ?, ?)",
               (user_id, email.strip().lower(), sifre_hashle(sifre), time.time()))
        return user_id

    def kullanici_email(self, email: str) -> sqlite3.Row | None:
        rows = self.q("SELECT * FROM users WHERE email = ?", (email.strip().lower(),))
        return rows[0] if rows else None

    def kullanici(self, user_id: str) -> sqlite3.Row | None:
        rows = self.q("SELECT * FROM users WHERE id = ?", (user_id,))
        return rows[0] if rows else None

    def giris(self, email: str, sifre: str) -> str | None:
        row = self.kullanici_email(email)
        if row is None:
            sifre_dogrula(sifre, sifre_hashle("zamanlama-esitleme"))  # kullanıcı var/yok sızmasın
            return None
        return row["id"] if sifre_dogrula(sifre, row["pw_hash"]) else None

    def dav_sifresi_yenile(self, user_id: str) -> str:
        sifre = secrets.token_urlsafe(18)
        self.x("UPDATE users SET dav_pw_hash = ? WHERE id = ?", (sifre_hashle(sifre), user_id))
        return sifre

    def dav_giris(self, email: str, sifre: str) -> str | None:
        row = self.kullanici_email(email)
        if row is None or not sifre_dogrula(sifre, row["dav_pw_hash"]):
            return None
        return row["id"]

    # --- OAuth ---------------------------------------------------------
    def temizle(self) -> None:
        now = time.time()
        self.x("DELETE FROM oauth_pending WHERE expires < ?", (now,))
        self.x("DELETE FROM oauth_codes WHERE expires < ?", (now,))
        self.x("DELETE FROM oauth_tokens WHERE expires IS NOT NULL AND expires < ?", (now,))
