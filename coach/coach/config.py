"""Settings read from environment variables (COACH_*)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping


def _list(value: str | None) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def _public_url(env: Mapping[str, str], default: str) -> str:
    """Turns COACH_PUBLIC_URL into a clean base URL.

    Adds https:// when the scheme is missing (http:// for local addresses). Without the variable,
    falls back to RAILWAY_PUBLIC_DOMAIN, which Railway sets for every generated domain.
    """
    value = (env.get("COACH_PUBLIC_URL") or "").strip()
    if not value and env.get("RAILWAY_PUBLIC_DOMAIN"):
        value = env["RAILWAY_PUBLIC_DOMAIN"].strip()
    if not value:
        return default
    if "://" not in value:
        local = value.split(":")[0] in ("localhost", "127.0.0.1", "0.0.0.0")
        value = ("http://" if local else "https://") + value
    return value.rstrip("/")


@dataclass(frozen=True)
class Settings:
    # The server's public address, e.g. https://coach.example.com (no trailing slash).
    public_url: str = "http://localhost:8000"
    # Persistent disk for the database and the users' vaults.
    data_dir: Path = Path("./data")
    host: str = "0.0.0.0"
    port: int = 8000
    # When not empty, sign-up asks for one of these codes (closed beta).
    invite_codes: list[str] = field(default_factory=list)
    # When true, anyone can sign up without an invite code.
    open_signup: bool = False
    access_token_seconds: int = 24 * 3600
    refresh_token_seconds: int = 90 * 24 * 3600
    # Registered clients may only redirect to these domains (and their subdomains). This stops a link
    # that redirects to an attacker's site from handing over a student's account.
    allowed_redirects: list[str] = field(default_factory=lambda: [
        "claude.ai", "claude.com", "anthropic.com", "chatgpt.com", "openai.com", "localhost", "127.0.0.1"])
    # Extra Host headers when running behind a reverse proxy (Caddy, Fly).
    allowed_hosts: list[str] = field(default_factory=list)
    # Telegram reminder bot (@BotFather token). The bot is off when empty.
    telegram_token: str = ""
    telegram_api: str = "https://api.telegram.org"
    # Starting reminder times and time zone for a newly linked student; each student changes them in the bot.
    morning_time: str = "09:00"
    evening_time: str = "22:00"
    timezone: str = "Europe/Istanbul"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "coach.sqlite3"

    @property
    def vault_root(self) -> Path:
        return self.data_dir / "vaults"

    @property
    def state_root(self) -> Path:
        """avenoxbeyin runtime state (index, locks); kept outside the vault and WebDAV."""
        return self.data_dir / "state"

    @classmethod
    def from_env(cls, source: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if source is None else source
        return cls(
            public_url=_public_url(env, cls.public_url),
            data_dir=Path(env.get("COACH_DATA_DIR", "./data")),
            host=env.get("COACH_HOST", cls.host),
            port=int(env.get("PORT", env.get("COACH_PORT", cls.port))),
            invite_codes=_list(env.get("COACH_INVITE_CODES")),
            open_signup=env.get("COACH_OPEN_SIGNUP", "").lower() in ("1", "true", "yes"),
            allowed_hosts=_list(env.get("COACH_ALLOWED_HOSTS")),
            telegram_token=env.get("COACH_TELEGRAM_TOKEN", "").strip(),
            telegram_api=env.get("COACH_TELEGRAM_API", cls.telegram_api).rstrip("/"),
            morning_time=env.get("COACH_MORNING_TIME", cls.morning_time),
            evening_time=env.get("COACH_EVENING_TIME", cls.evening_time),
            timezone=env.get("COACH_TIMEZONE", cls.timezone),
            **({"allowed_redirects": _list(env["COACH_ALLOWED_REDIRECTS"])}
               if env.get("COACH_ALLOWED_REDIRECTS") else {}),
        )
