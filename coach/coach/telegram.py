"""Telegram adapter: a reminder channel and a file inbox.

Kept thin because the channel may be temporary: removing this file and `COACH_TELEGRAM_TOKEN` removes
the bot completely. Nothing is stored in Telegram; incoming files go straight into the student's vault.
The bot never calls a language model: chatting and solving questions stay in the student's own Claude.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
from datetime import datetime, timezone
from typing import Any, Callable

import httpx2 as httpx
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from .config import Settings
from .db import DB
from .i18n import LANGUAGES, normalize, t
from .reminders import TIME_FORMAT, Message, handle_button, morning_message, valid_zone, zone
from .vault import Vault

log = logging.getLogger(__name__)
CHANNEL = "telegram"
# The Bot API only lets bots download files up to 20 MB; big PDFs come through the upload page.
MAX_DOWNLOAD = 20 * 1024 * 1024


class Telegram:
    name = CHANNEL

    def __init__(self, settings: Settings, db: DB, open_vault: Callable[[str], Vault],
                 save: Callable[[str, list[tuple[str, bytes]], str], list[str]]):
        self.settings, self.db, self.open_vault, self.save = settings, db, open_vault, save
        self._api = f"{settings.telegram_api}/bot{settings.telegram_token}"
        self._file_api = f"{settings.telegram_api}/file/bot{settings.telegram_token}"
        # Telegram sends this value back in a header on every webhook call; it tells fake calls apart.
        self.secret = hmac.new(settings.telegram_token.encode(), b"webhook", hashlib.sha256).hexdigest()
        self.username: str | None = None

    # --- Bot API ---------------------------------------------------------------
    async def _call(self, method: str, **data: Any) -> Any:
        async with httpx.AsyncClient(timeout=30) as http:
            r = await http.post(f"{self._api}/{method}", json=data)
        body = r.json()
        if not body.get("ok"):
            raise RuntimeError(f"Telegram {method}: {body.get('description')}")
        return body.get("result")

    async def setup(self) -> None:
        """Learns the bot's username and points the webhook at this server."""
        me = await self._call("getMe")
        self.username = me.get("username")
        if self.settings.public_url.startswith("https://"):
            await self._call("setWebhook", url=f"{self.settings.public_url}/telegram/webhook", secret_token=self.secret,
                             allowed_updates=["message", "callback_query"], drop_pending_updates=False)
        else:
            log.warning("Telegram webhook not set: COACH_PUBLIC_URL is not https.")

    async def send(self, target: str, message: Message) -> None:
        data: dict[str, Any] = {"chat_id": target, "text": message.text}
        if message.buttons:
            data["reply_markup"] = {"inline_keyboard": [[{"text": b.label, "callback_data": b.data} for b in row]
                                                        for row in message.buttons]}
        await self._call("sendMessage", **data)

    async def _say(self, target: Any, text: str) -> None:
        await self.send(str(target), Message(text))

    def link_url(self, user_id: str) -> str | None:
        if not self.username:
            return None
        return f"https://t.me/{self.username}?start={self.db.create_link_code(user_id)}"

    # --- webhook -----------------------------------------------------------------
    async def webhook(self, request: Request) -> Response:
        if not hmac.compare_digest(request.headers.get("x-telegram-bot-api-secret-token", ""), self.secret):
            return Response(status_code=403)
        try:
            update = await request.json()
            if "callback_query" in update:
                await self._button(update["callback_query"])
            elif "message" in update:
                await self._message(update["message"])
        except Exception:  # noqa: BLE001 - don't make Telegram resend the same update forever
            log.exception("telegram update")
        return JSONResponse({"ok": True})

    async def _message(self, m: dict) -> None:
        chat = m.get("chat") or {}
        if chat.get("type") != "private":
            return  # no group chats: a vault belongs to one person
        target = str(chat["id"])
        text = (m.get("text") or "").strip()
        sender_lang = normalize((m.get("from") or {}).get("language_code"))
        if text.startswith("/start"):
            return await self._start(target, text[len("/start"):].strip(), sender_lang)
        link = self.db.channel_link(CHANNEL, target)
        if link is None:
            return await self._say(target, t(sender_lang, "tg_not_linked"))
        lang = link["lang"]
        if "photo" in m or "document" in m:
            return await self._file(target, link["user_id"], lang, m)
        command, *args = text.split() or [""]
        command = command.split("@")[0].lower()
        if command == "/today":
            vault = self.open_vault(link["user_id"])
            today = datetime.now(timezone.utc).astimezone(zone(link["timezone"])).date()
            message = await asyncio.to_thread(morning_message, vault, today, lang)
            return await self.send(target, message or Message(t(lang, "tg_nothing_today")))
        if command == "/time":
            if len(args) != 2 or not all(TIME_FORMAT.match(a) for a in args):
                return await self._say(target, t(lang, "tg_time_example"))
            self.db.update_link(CHANNEL, target, morning=args[0], evening=args[1])
            return await self._say(target, t(lang, "tg_time_set", morning=args[0], evening=args[1]))
        if command == "/timezone":
            if len(args) != 1 or not valid_zone(args[0]):
                return await self._say(target, t(lang, "tg_timezone_example"))
            self.db.update_link(CHANNEL, target, timezone=args[0])
            return await self._say(target, t(lang, "tg_timezone_set", tz=args[0]))
        if command == "/language":
            new = normalize(args[0]) if len(args) == 1 else None
            if new is None:
                return await self._say(target, t(lang, "tg_language_example") + " (" + ", ".join(LANGUAGES) + ")")
            self.db.update_link(CHANNEL, target, lang=new)
            return await self._say(target, t(new, "tg_language_set"))
        if command in ("/mute", "/unmute"):
            self.db.update_link(CHANNEL, target, muted=int(command == "/mute"))
            return await self._say(target, t(lang, "tg_muted" if command == "/mute" else "tg_unmuted"))
        if command == "/unlink":
            self.db.unlink(CHANNEL, target)
            return await self._say(target, t(lang, "tg_unlinked"))
        await self._say(target, t(lang, "tg_chat_elsewhere") + "\n\n" + t(lang, "tg_help"))

    async def _start(self, target: str, code: str, sender_lang: str | None) -> None:
        user_id = self.db.use_link_code(code) if code else None
        if user_id is None:
            link = self.db.channel_link(CHANNEL, target)
            if link:
                return await self._say(target, t(link["lang"], "tg_help"))
            return await self._say(target, t(sender_lang, "tg_bad_code"))
        user = self.db.user(user_id)
        lang = (user["lang"] if user else None) or sender_lang or "en"
        s = self.settings
        now = datetime.now(timezone.utc).astimezone(zone(s.timezone))
        self.db.link(user_id, CHANNEL, target, s.morning_time, s.evening_time, s.timezone, lang,
                     now.date().isoformat(), now.strftime("%H:%M"))
        await self._say(target, t(lang, "tg_linked", morning=s.morning_time, evening=s.evening_time, tz=s.timezone)
                        + "\n\n" + t(lang, "tg_help"))

    async def _file(self, target: str, user_id: str, lang: str, m: dict) -> None:
        if "photo" in m:
            info = max(m["photo"], key=lambda p: p.get("file_size", 0))
            name = f"telegram-{m.get('message_id', 'photo')}.jpg"
        else:
            info = m["document"]
            name = info.get("file_name") or f"telegram-{m.get('message_id', 'file')}"
        if info.get("file_size", 0) > MAX_DOWNLOAD:
            return await self._say(target, t(lang, "tg_file_too_big", url=f"{self.settings.public_url}/upload"))
        file = await self._call("getFile", file_id=info["file_id"])
        async with httpx.AsyncClient(timeout=120) as http:
            r = await http.get(f"{self._file_api}/{file['file_path']}")
        r.raise_for_status()
        paths = await asyncio.to_thread(self.save, user_id, [(name, r.content)], (m.get("caption") or "")[:300])
        await self._say(target, t(lang, "tg_saved", paths=", ".join(paths)))

    async def _button(self, cq: dict) -> None:
        target = str(((cq.get("message") or {}).get("chat") or {}).get("id", ""))
        link = self.db.channel_link(CHANNEL, target)
        if link is None:
            answer = t(normalize((cq.get("from") or {}).get("language_code")), "tg_not_linked_short")
        else:
            vault = self.open_vault(link["user_id"])
            today = datetime.now(timezone.utc).astimezone(zone(link["timezone"])).date()
            answer = await asyncio.to_thread(handle_button, vault, str(cq.get("data", "")), today, link["lang"])
        await self._call("answerCallbackQuery", callback_query_id=cq["id"], text=answer[:190])
        message = cq.get("message") or {}
        if message.get("message_id"):
            await self._call("editMessageText", chat_id=target, message_id=message["message_id"],
                             text=f"{message.get('text', '')}\n\n→ {answer}")
