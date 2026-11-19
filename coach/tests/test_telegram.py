"""Telegram adapter and reminder core: end to end against a fake Bot API."""
import asyncio
import hashlib
import hmac
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from coach.config import Settings
from coach.server import create_app
from test_e2e import INVITE, PASSWORD, PNG, _connect, _ok, _port, _tools

TOKEN = "123:ABC"
SECRET = hmac.new(TOKEN.encode(), b"webhook", hashlib.sha256).hexdigest()
TZ = ZoneInfo("Europe/Istanbul")


class FakeTelegram:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def sent(self, method="sendMessage"):
        return [v for m, v in self.calls if m == method]

    async def api(self, request: Request):
        method = request.path_params["method"]
        data = await request.json()
        self.calls.append((method, data))
        result = {"getMe": {"username": "test_bot"},
                  "getFile": {"file_path": "photos/question.png"}}.get(method, {"message_id": len(self.calls)})
        return JSONResponse({"ok": True, "result": result})

    async def file(self, request: Request):
        return Response(PNG, media_type="image/png")

    def app(self):
        return Starlette(routes=[Route(f"/bot{TOKEN}/{{method}}", self.api, methods=["POST"]),
                                 Route(f"/file/bot{TOKEN}/{{path:path}}", self.file)])


def _serve(app, port):
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    return server


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    fake = FakeTelegram()
    tg_port, port = _port(), _port()
    tg = _serve(fake.app(), tg_port)
    url = f"http://127.0.0.1:{port}"
    settings = Settings(public_url=url, data_dir=Path(tmp_path_factory.mktemp("tg")), host="127.0.0.1", port=port,
                        invite_codes=[INVITE], telegram_token=TOKEN, telegram_api=f"http://127.0.0.1:{tg_port}",
                        timezone="Europe/Istanbul")
    app = create_app(settings)
    srv = _serve(app, port)
    yield url, app, fake
    srv.should_exit = tg.should_exit = True


def _update(url, body, secret=SECRET):
    return httpx.post(f"{url}/telegram/webhook", json=body, headers={"X-Telegram-Bot-Api-Secret-Token": secret})


def _write(url, chat, text, kind="private", lang="en"):
    return _update(url, {"update_id": 1, "message": {"message_id": 10, "chat": {"id": chat, "type": kind},
                                                      "from": {"language_code": lang}, "text": text}})


def test_telegram_linking_reminders_and_buttons(env):
    url, app, fake = env
    tok, _, _ = _connect(url, "tg@example.com")
    assert ("getMe", {}) in fake.calls  # the bot learned its name at startup

    # "Connect Telegram" on the upload page redirects to t.me with a single-use code.
    c = httpx.Client(base_url=url)
    assert c.get("/upload/telegram").status_code == 303  # not signed in: back to the upload page
    c.post("/upload", data={"action": "login", "email": "tg@example.com", "password": PASSWORD})
    assert "Connect Telegram" in c.get("/upload?lang=en").text
    r = c.get("/upload/telegram")
    assert r.status_code == 303 and r.headers["location"].startswith("https://t.me/test_bot?start=")
    code = r.headers["location"].split("start=")[1]

    # Fake webhook calls are rejected; unlinked chats and group chats can't reach the vault.
    assert _update(url, {"message": {}}, secret="wrong").status_code == 403
    _write(url, 777, "/today", lang="tr")
    assert "bağlı değil" in fake.sent()[-1]["text"]  # unlinked chat answered in the sender's language
    before = len(fake.sent())
    _write(url, -100, f"/start {code}", kind="group")
    assert len(fake.sent()) == before

    _write(url, 555, f"/start {code}")
    assert "Connected" in fake.sent()[-1]["text"] and "Europe/Istanbul" in fake.sent()[-1]["text"]
    assert f"{url}/start" in fake.sent()[-1]["text"]  # points back to the getting-started steps
    assert c.get("/start/status").json()["telegram"] is True
    _write(url, 556, f"/start {code}")  # the code is single use
    assert "invalid" in fake.sent()[-1]["text"]

    # The task and review the coach wrote to the vault reach the bot's message from the repository's fields.
    today = datetime.now(TZ).date()
    asyncio.run(_tools(url, tok, [
        ("create_task", {"source": "tasks/pharma.md", "text": "Pharmacology autonomic: 40 questions",
                         "metadata": {"id": "pharma-autonomic", "title": "Pharmacology autonomic 40 questions",
                                      "kind": "task", "status": "active", "owner": "Ayse", "project": "exam",
                                      "due_at": today.isoformat()}}),
        ("create_task", {"source": "tasks/cardio.md", "text": "Cardiology review",
                         "metadata": {"id": "cardio", "title": "Cardiology review", "kind": "task",
                                      "status": "active", "owner": "Ayse", "project": "exam",
                                      "due_at": today.isoformat()}}),
        ("create_note", {"source": "notes/exam/endocrine/graves.md", "text": "# Graves\n\nTRAb positive.\n",
                         "metadata": {"title": "Graves mistake", "review_at": (today - timedelta(days=1)).isoformat()}}),
    ]))
    _write(url, 555, "/today")
    morning = fake.sent()[-1]["text"]
    assert "Pharmacology autonomic 40 questions" in morning and "Graves mistake" in morning

    # Scheduler: the next evening sends the morning summary + a question with buttons per task; not twice a day.
    tomorrow_evening = datetime.combine(today + timedelta(days=1), datetime.min.time(), TZ).replace(hour=22, minute=1)
    scheduler = app.state.scheduler
    assert asyncio.run(scheduler.tick(tomorrow_evening.astimezone(timezone.utc))) == 3
    assert asyncio.run(scheduler.tick(tomorrow_evening.astimezone(timezone.utc))) == 0
    with_buttons = [m for m in fake.sent() if "reply_markup" in m]
    data = {d["callback_data"] for m in with_buttons[-2:] for d in m["reply_markup"]["inline_keyboard"][0]}
    assert data == {"g|d|pharma-autonomic", "g|y|pharma-autonomic", "g|d|cardio", "g|y|cardio"}

    def press(value):
        _update(url, {"update_id": 2, "callback_query": {"id": "cq", "data": value, "message": {
            "message_id": 50, "chat": {"id": 555, "type": "private"}, "text": "Today's task"}}})
        return fake.sent("answerCallbackQuery")[-1]["text"]

    assert "done" in press("g|d|pharma-autonomic").lower()
    assert "already closed" in press("g|d|pharma-autonomic")
    assert "tomorrow" in press("g|y|cardio").lower()
    assert "→" in fake.sent("editMessageText")[-1]["text"]
    # The engine's task-update changed the tasks: one closed, the other moved to tomorrow.
    _write(url, 555, "/today")
    last = fake.sent()[-1]["text"]
    assert "Pharmacology" not in last and "Cardiology" not in last and "Graves mistake" in last

    # A photo lands in the vault and the coach sees it through the connector; over 20 MB goes to the upload page.
    _update(url, {"update_id": 3, "message": {"message_id": 11, "chat": {"id": 555, "type": "private"},
                                               "photo": [{"file_id": "small", "file_size": 10},
                                                         {"file_id": "big", "file_size": 70}]}})
    assert fake.sent("getFile")[-1] == {"file_id": "big"}
    assert "Saved: Attachments/" in fake.sent()[-1]["text"]
    out = asyncio.run(_tools(url, tok, [("list_attachments", {})]))
    assert len(_ok(out["list_attachments"][0])["attachments"]) == 1
    _update(url, {"update_id": 4, "message": {"message_id": 12, "chat": {"id": 555, "type": "private"},
                                               "document": {"file_id": "pdf", "file_name": "book.pdf",
                                                            "file_size": 50 * 1024 * 1024}}})
    assert "20 MB" in fake.sent()[-1]["text"]

    # Time, time zone, language and mute commands.
    _write(url, 555, "/time 7:00 22:00")
    assert "Example" in fake.sent()[-1]["text"]
    _write(url, 555, "/time 07:00 22:00")
    assert "07:00" in fake.sent()[-1]["text"]
    _write(url, 555, "/timezone Mars/Olympus")
    assert "Example" in fake.sent()[-1]["text"]
    _write(url, 555, "/language tr")
    assert "Türkçe" in fake.sent()[-1]["text"]
    _write(url, 555, "/mute")
    assert "durdurdum" in fake.sent()[-1]["text"]
    next_day = tomorrow_evening + timedelta(days=1)
    assert asyncio.run(scheduler.tick(next_day.replace(hour=22, minute=5).astimezone(timezone.utc))) == 0
    _write(url, 555, "/unmute")
    assert asyncio.run(scheduler.tick(next_day.replace(hour=22, minute=5).astimezone(timezone.utc))) >= 1
    assert "Günaydın" in "".join(m["text"] for m in fake.sent()[-3:]) or "Bitti mi?" in fake.sent()[-1]["text"]

    # Reminders follow the student's own time zone: 07:00 in New York is 15:00 in Istanbul.
    _write(url, 555, "/timezone America/New_York")
    ny = ZoneInfo("America/New_York")
    day3 = (next_day + timedelta(days=1)).date()
    early = datetime.combine(day3, datetime.min.time(), ny).replace(hour=6, minute=59)
    assert asyncio.run(scheduler.tick(early.astimezone(timezone.utc))) == 0
    assert asyncio.run(scheduler.tick((early + timedelta(minutes=2)).astimezone(timezone.utc))) >= 1
