"""Channel-independent reminder core.

No memory logic here either: what to remind comes from the student's avenoxbeyin vault.
- due reviews: `review.due` in the engine's `triage` output (the notes' `review_at` field)
- tasks due today: task records under `tasks/` (`due_at`, `status`)
- button answers: the engine's `task-update` command (with its revision check)

It doesn't know where messages go. Telegram, later WhatsApp or our own app, is a thin adapter that
implements the `Channel` protocol; swapping the channel doesn't touch this file.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .db import DB
from .i18n import t
from .vault import Vault

log = logging.getLogger(__name__)
OPEN_STATUSES = {"active", "waiting"}
TIME_FORMAT = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def zone(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def valid_zone(name: str) -> bool:
    try:
        ZoneInfo(name)
        return True
    except (ZoneInfoNotFoundError, ValueError):
        return False


@dataclass
class Button:
    label: str
    data: str  # sent back by the channel; at most 64 bytes on Telegram


@dataclass
class Message:
    text: str
    buttons: list[list[Button]] = field(default_factory=list)


class Channel(Protocol):
    name: str

    async def send(self, target: str, message: Message) -> None: ...


# --- reading the vault -------------------------------------------------------
def _front_matter(path: Path) -> dict:
    """Reads Markdown front matter. The engine writes tasks as JSON and notes as simple YAML."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    body = text[3:end].strip()
    if body.startswith("{"):
        try:
            data = json.loads(body)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}
    data = {}
    for line in body.splitlines():
        if ":" in line and not line.startswith((" ", "-")):
            k, v = line.split(":", 1)
            data[k.strip()] = v.strip().strip('"').strip("'")
    return data


def _task_records(vault: Vault) -> list[dict]:
    root = vault.vault / "tasks"
    out = []
    for path in (root.rglob("*.md") if root.is_dir() else []):
        fm = _front_matter(path)
        if fm.get("kind") == "task" and fm.get("id"):
            out.append({"id": str(fm["id"]), "title": str(fm.get("title") or path.stem),
                        "due_at": str(fm.get("due_at") or "")[:10], "status": fm.get("status"),
                        "revision": fm.get("revision")})
    return out


def due_tasks(vault: Vault, today: date) -> list[dict]:
    """Open tasks due today or earlier, oldest first."""
    out = [task for task in _task_records(vault)
           if task["status"] in OPEN_STATUSES and task["due_at"] and task["due_at"] <= today.isoformat()]
    return sorted(out, key=lambda task: (task["due_at"], task["id"]))


def due_reviews(vault: Vault) -> list[dict]:
    """Reviews that are due according to the engine's triage output, with their titles."""
    triage = vault.cli("triage")
    out = []
    for record in (triage.get("review") or {}).get("due", []):
        source = record.get("source") or ""
        try:
            title = _front_matter(vault.file_path(source)).get("title")
        except Exception:  # noqa: BLE001 - the file name is enough when there's no title
            title = None
        out.append({"source": source, "title": title or Path(source).stem, "overdue": record.get("days_overdue", 0)})
    return out


# --- messages ------------------------------------------------------------------
def morning_message(vault: Vault, today: date, lang: str) -> Message | None:
    reviews, tasks = due_reviews(vault), due_tasks(vault, today)
    if not reviews and not tasks:
        return None
    lines = [t(lang, "rem_morning")]
    if tasks:
        lines.append("\n" + t(lang, "rem_tasks", n=len(tasks)))
        lines += [f"• {task['title']}" + (t(lang, "rem_overdue") if task["due_at"] < today.isoformat() else "")
                  for task in tasks[:8]]
    if reviews:
        lines.append("\n" + t(lang, "rem_reviews", n=len(reviews)))
        lines += [f"• {r['title']}" for r in reviews[:8]]
    lines.append("\n" + t(lang, "rem_start"))
    return Message("\n".join(lines))


def evening_messages(vault: Vault, today: date, lang: str) -> list[Message]:
    out = []
    for task in due_tasks(vault, today):
        buttons = []
        if len(f"g|d|{task['id']}".encode()) <= 64:
            buttons = [[Button(t(lang, "rem_done_button"), f"g|d|{task['id']}"),
                        Button(t(lang, "rem_tomorrow_button"), f"g|y|{task['id']}")]]
        out.append(Message(t(lang, "rem_task_question", title=task["title"]), buttons))
    return out


def handle_button(vault: Vault, data: str, today: date, lang: str) -> str:
    """Applies a button answer with the engine's task-update; re-reads once on a revision conflict.

    Button data: g|d|<id> marks the task done, g|y|<id> moves it to tomorrow (kept short for Telegram)."""
    try:
        kind, action, task_id = data.split("|", 2)
    except ValueError:
        return t(lang, "rem_button_invalid")
    if kind != "g" or action not in ("d", "y"):
        return t(lang, "rem_button_invalid")
    for _ in range(2):
        task = next((x for x in _task_records(vault) if x["id"] == task_id), None)
        if task is None:
            return t(lang, "rem_task_missing")
        if task["status"] not in OPEN_STATUSES:
            return t(lang, "rem_task_closed")
        due = date.fromisoformat(task["due_at"] or today.isoformat())
        changes = {"status": "done"} if action == "d" else {"due_at": (max(today, due) + timedelta(days=1)).isoformat()}
        result = vault.cli("task-update", payload={"id": task_id, "expected_revision": task["revision"],
                                                   "changes": changes})
        if not result.get("error"):
            return t(lang, "rem_marked_done") if action == "d" else t(lang, "rem_moved")
        if result.get("error") != "RevisionConflict":
            log.warning("task-update failed: %s", result)
            return t(lang, "rem_save_failed")
    return t(lang, "rem_task_changed")


# --- scheduler -----------------------------------------------------------------
class Scheduler:
    """Checks the linked users every minute and sends the morning and evening messages whose time
    has passed in the user's own time zone and weren't sent that day. Built for a single server
    instance (the same assumption as db.py)."""

    def __init__(self, db: DB, channels: dict[str, Channel], open_vault: Callable[[str], Vault]):
        self.db, self.channels, self.open_vault = db, channels, open_vault

    async def run(self, interval: float = 60) -> None:
        while True:
            try:
                await self.tick(datetime.now(timezone.utc))
            except Exception:  # noqa: BLE001 - keep the loop alive
                log.exception("reminder tick")
            await asyncio.sleep(interval)

    async def tick(self, now: datetime) -> int:
        """Sends what is due; returns the number of messages sent."""
        count = 0
        for link in self.db.channel_links():
            channel = self.channels.get(link["channel"])
            if channel is None or link["muted"]:
                continue
            local = now.astimezone(zone(link["timezone"]))
            today, clock = local.date().isoformat(), local.strftime("%H:%M")
            for when, last in (("morning", "last_morning"), ("evening", "last_evening")):
                if clock < link[when] or link[last] == today:
                    continue
                self.db.mark_sent(link["user_id"], link["channel"], last, today)  # never send twice, even after a crash
                vault, lang = self.open_vault(link["user_id"]), link["lang"]
                messages = await asyncio.to_thread(
                    lambda: [m for m in [morning_message(vault, local.date(), lang)] if m] if when == "morning"
                    else evening_messages(vault, local.date(), lang))
                for m in messages:
                    await channel.send(link["target"], m)
                    count += 1
        return count
