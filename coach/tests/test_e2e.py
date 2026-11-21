"""End to end against a real HTTP server: OAuth (DCR + PKCE), MCP tools, user isolation, WebDAV."""
import asyncio
import base64
import hashlib
import json
import re
import secrets
import shutil
import socket
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

import httpx
import httpx2
import pytest
import uvicorn

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from coach.config import Settings
from coach.server import create_app

INVITE = "test-invite"
CB = "http://localhost:9/cb"


def _port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    port = _port()
    url = f"http://127.0.0.1:{port}"
    settings = Settings(public_url=url, data_dir=Path(tmp_path_factory.mktemp("data")), host="127.0.0.1",
                        port=port, invite_codes=[INVITE])
    server = uvicorn.Server(uvicorn.Config(create_app(settings), host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        try:
            if httpx.get(f"{url}/health").status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.05)
    yield url
    server.should_exit = True
    thread.join(5)


def _connect(base, email, password="very-secret-password", mode="signup", invite=INVITE, lang="en"):
    """Mimics the OAuth flow an MCP client runs; returns (access, refresh, client_id)."""
    c = httpx.Client(base_url=base)
    meta = c.get("/.well-known/oauth-authorization-server").json()
    assert meta["registration_endpoint"].endswith("/register")
    reg = c.post("/register", json={"redirect_uris": [CB], "token_endpoint_auth_method": "none",
                                    "grant_types": ["authorization_code", "refresh_token"],
                                    "response_types": ["code"], "client_name": "test"})
    assert reg.status_code == 201, reg.text
    client_id = reg.json()["client_id"]
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    r = c.get("/authorize", params={"response_type": "code", "client_id": client_id, "redirect_uri": CB,
                                    "code_challenge": challenge, "code_challenge_method": "S256",
                                    "state": "state123", "scope": "coach", "resource": f"{base}/mcp"})
    assert r.status_code == 302, r.text
    login = urlparse(r.headers["location"])
    request_id = parse_qs(login.query)["request"][0]
    page = c.get(f"{login.path}?{login.query}&lang={lang}")
    assert page.status_code == 200 and "test (localhost)" in page.text
    assert ("Çalışma Koçu" if lang == "tr" else "Study Coach") in page.text
    r = c.post("/account/login", data={"request": request_id, "mode": mode, "email": email, "password": password,
                                       "invite": invite, "lang": lang})
    assert r.status_code == 303, r.text
    q = parse_qs(urlparse(r.headers["location"]).query)
    assert q["state"] == ["state123"]
    tok = c.post("/token", data={"grant_type": "authorization_code", "code": q["code"][0], "redirect_uri": CB,
                                 "client_id": client_id, "code_verifier": verifier, "resource": f"{base}/mcp"})
    assert tok.status_code == 200, tok.text
    # The code can't be used twice.
    again = c.post("/token", data={"grant_type": "authorization_code", "code": q["code"][0], "redirect_uri": CB,
                                   "client_id": client_id, "code_verifier": verifier})
    assert again.status_code == 400
    return tok.json()["access_token"], tok.json()["refresh_token"], client_id


async def _tools(base, token, calls):
    async with httpx2.AsyncClient(headers={"Authorization": f"Bearer {token}"}, timeout=30) as http:
        async with streamable_http_client(f"{base}/mcp", http_client=http) as (read, write):
            async with ClientSession(read, write) as s:
                await s.initialize()
                out = {"_tools": [t.name for t in (await s.list_tools()).tools]}
                for name, args in calls:
                    res = await s.call_tool(name, args)
                    first = res.content[0] if res.content else None
                    text = getattr(first, "text", "") or ""
                    data = res.structured_content or (json.loads(text) if text.startswith("{") else text)
                    if isinstance(data, dict) and set(data) == {"result"}:
                        data = data["result"]
                    out.setdefault(name, []).append({"error": res.is_error, "data": data, "type": getattr(first, "type", None),
                                                     "mime": getattr(first, "mime_type", None)})
                return out


def test_unauthenticated_request_is_rejected(base):
    r = httpx.post(f"{base}/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                   headers={"Accept": "application/json, text/event-stream"})
    assert r.status_code == 401
    assert "resource_metadata" in r.headers.get("www-authenticate", "")


def test_unknown_redirect_uri_cannot_register(base):
    r = httpx.post(f"{base}/register", json={"redirect_uris": ["https://attacker.example/cb"],
                                             "token_endpoint_auth_method": "none"})
    assert r.status_code == 400 and r.json()["error"] == "invalid_redirect_uri"


def test_signup_needs_an_invite_code(base):
    with pytest.raises(AssertionError):
        _connect(base, "noinvite@example.com", invite="wrong")


def _ok(item):
    assert item["error"] is False, item
    return item["data"]


def test_end_to_end_avenoxbeyin_vault(base):
    a_tok, a_refresh, a_client = _connect(base, "ayse@example.com", lang="tr")
    out = asyncio.run(_tools(base, a_tok, [
        ("start_session", {}),
        ("read_instructions", {"which": "study-coach"}),
        ("read_instructions", {"which": "all"}),
        ("read_instructions", {"which": "exam", "exam": "TUS"}),
        ("read_instructions", {"which": "exam", "exam": "no-such-exam"}),
        ("create_note", {"source": "notes/exam/pharmacology/digoxin-hyperkalemia.md",
                         "text": "# Digoxin and hyperkalemia\n\nDigoxin toxicity causes hyperkalemia; I mistook it "
                                 "for hypokalemia.\n",
                         "metadata": {"title": "Digoxin hyperkalemia mistake", "review_at": "2026-01-01",
                                      "tags": ["mistake", "pharmacology"]}}),
        ("create_task", {"source": "tasks/exam-pharma-autonomic.md", "text": "Pharmacology autonomic: topic + 40 questions",
                         "metadata": {"id": "exam-pharma-autonomic", "title": "Pharmacology autonomic", "kind": "task",
                                      "status": "active", "owner": "Ayse", "project": "exam",
                                      "due_at": "2026-01-02"}}),
        ("search_vault", {"query": "potassium in digoxin toxicity"}),
        ("update_task", {"id": "exam-pharma-autonomic", "expected_revision": 1, "changes": {"status": "done"}}),
        ("update_task", {"id": "exam-pharma-autonomic", "expected_revision": 1, "changes": {"status": "done"}}),
        ("read_note", {"source": "🔮 850-Companion/Threads.md"}),
        ("vault_status", {}),
        ("show_attachment", {"path": "../../session.key"}),
        ("read_note", {"source": "../../../coach.sqlite3"}),
    ]))
    first = _ok(out["start_session"][0])
    assert first["session"] and "Receipt session=" in first["context"] and "850-Companion/Core.md" in first["context"]
    assert "/vaults/" not in first["context"]
    assert "search_vault" in _ok(out["read_instructions"][0])["study-coach"]
    assert "tus" in {e["id"] for e in _ok(out["read_instructions"][1])["exams"]}
    assert "Temel Tıp Bilimleri" in _ok(out["read_instructions"][2])["exam"]
    assert out["read_instructions"][3]["error"] is True
    assert _ok(out["create_note"][0]).get("exit_code") == 0
    assert _ok(out["create_task"][0])["due_at"] == "2026-01-02"
    found = [r["source"] for r in _ok(out["search_vault"][0])["records"]]
    assert "notes/exam/pharmacology/digoxin-hyperkalemia.md" in found
    assert _ok(out["update_task"][0])["status"] == "done"
    assert out["update_task"][1]["data"]["error"] == "RevisionConflict"  # the repository's revision rule
    threads = _ok(out["read_note"][0])
    assert "Active Threads" in json.dumps(threads, ensure_ascii=False)
    assert _ok(out["vault_status"][0])["review"]["due_count"] == 1  # note whose review_at has passed
    assert out["show_attachment"][0]["error"] is True
    assert "error" in json.dumps(out["read_note"][1]["data"]) or out["read_note"][1]["error"]

    # In the next conversation the repository's own hook brings the due review.
    out2 = asyncio.run(_tools(base, a_tok, [("start_session", {})]))
    assert "Due reviews: 1" in _ok(out2["start_session"][0])["context"]

    # A second user can't see the first user's vault.
    b_tok, _, _ = _connect(base, "zeynep@example.com")
    out_b = asyncio.run(_tools(base, b_tok, [("search_vault", {"query": "digoxin hyperkalemia"}),
                                             ("read_note", {"source": "notes/exam/pharmacology/digoxin-hyperkalemia.md"})]))
    assert _ok(out_b["search_vault"][0]).get("records", []) == []
    assert _ok(out_b["read_note"][0]).get("exists") is False

    # The refresh token works and is single use.
    data = {"grant_type": "refresh_token", "refresh_token": a_refresh, "client_id": a_client}
    r = httpx.post(f"{base}/token", data=data)
    assert r.status_code == 200 and r.json()["access_token"] != a_tok
    assert httpx.post(f"{base}/token", data=data).status_code == 400


PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg==")
PASSWORD = "very-secret-password"


def test_photo_upload_and_show(base):
    tok, _, _ = _connect(base, "photo@example.com")
    c = httpx.Client(base_url=base)
    assert "Sign in" in c.get("/upload", headers={"Accept-Language": "en-US,en;q=0.9"}).text
    assert "Giriş yap" in c.get("/upload", headers={"Accept-Language": "tr-TR,tr;q=0.9,en;q=0.5"}).text
    assert c.post("/upload", data={"action": "login", "email": "photo@example.com", "password": "wrong-password"}).status_code == 400
    r = c.post("/upload", data={"action": "login", "email": "photo@example.com", "password": PASSWORD})
    assert r.status_code == 200 and "coach_session" in r.headers.get("set-cookie", "")
    r = c.post("/upload", data={"action": "upload"}, files={"file": ("question.png", PNG, "image/png")})
    assert r.status_code == 200, r.text
    path = re.findall(r"<code>([^<]+)</code>", r.text)[0]
    assert path.startswith("Attachments/") and path.endswith(".jpg")
    # A client without the cookie can't upload.
    assert httpx.post(f"{base}/upload", data={"action": "upload"},
                      files={"file": ("x.png", PNG, "image/png")}).status_code == 401
    out = asyncio.run(_tools(base, tok, [("list_attachments", {}), ("show_attachment", {"path": path})]))
    assert _ok(out["list_attachments"][0])["attachments"][0]["path"] == path
    assert out["show_attachment"][0]["type"] == "image" and out["show_attachment"][0]["mime"] == "image/jpeg"


def test_language_switch_is_remembered(base):
    c = httpx.Client(base_url=base)
    r = c.get("/upload?lang=tr", headers={"Accept-Language": "en"})
    assert "Giriş yap" in r.text and "lang=tr" in r.headers.get("set-cookie", "")
    assert "Giriş yap" in c.get("/upload", headers={"Accept-Language": "en"}).text
    assert "Sign in" in c.get("/upload?lang=en").text


def test_webdav_obsidian_sync(base):
    tok, _, _ = _connect(base, "dav@example.com")
    _connect(base, "other@example.com")
    asyncio.run(_tools(base, tok, [("start_session", {})]))  # set the vault up
    r = httpx.post(f"{base}/account/obsidian", data={"email": "dav@example.com", "password": PASSWORD})
    assert r.status_code == 200
    password = re.findall(r"<code>([^<]+)</code>", r.text)[2]
    auth = ("dav@example.com", password)
    assert httpx.request("PROPFIND", f"{base}/dav/", headers={"Depth": "1"}).status_code == 401
    assert httpx.request("PROPFIND", f"{base}/dav/", auth=("dav@example.com", PASSWORD)).status_code == 401
    root = httpx.request("PROPFIND", f"{base}/dav/", headers={"Depth": "1"}, auth=auth)
    assert root.status_code == 207 and "850-Companion" in unquote(root.text)
    # Managed engine files and hidden folders are not synced.
    assert "beyin.py" not in root.text and ".agents" not in root.text and ".claude" not in root.text
    assert httpx.get(f"{base}/dav/beyin.py", auth=auth).status_code == 404
    assert httpx.put(f"{base}/dav/.agents/skills/x/SKILL.md", content=b"x", auth=auth).status_code in (404, 409)
    # A note written in Obsidian arrives over WebDAV and shows up in the repository's search.
    assert httpx.request("MKCOL", f"{base}/dav/Topics/", auth=auth).status_code in (201, 405)
    body = "# Thyroid\n\nGraves disease has TSH receptor antibodies. [[Hyperthyroidism]]\n".encode()
    assert httpx.put(f"{base}/dav/Topics/Thyroid.md", content=body, auth=auth).status_code in (201, 204)
    out = asyncio.run(_tools(base, tok, [("search_vault", {"query": "graves disease antibodies"})]))
    assert "Topics/Thyroid.md" in [r["source"] for r in _ok(out["search_vault"][0])["records"]]
    # Another user's password can't open this vault, and path tricks don't work.
    r = httpx.post(f"{base}/account/obsidian", data={"email": "other@example.com", "password": PASSWORD})
    other = ("other@example.com", re.findall(r"<code>([^<]+)</code>", r.text)[2])
    assert httpx.get(f"{base}/dav/Topics/Thyroid.md", auth=other).status_code == 404
    assert httpx.get(f"{base}/dav/..%2F..%2Fcoach.sqlite3", auth=other).status_code in (400, 403, 404)


def test_notes_and_pdfs_go_to_the_capture_inbox(base):
    tok, _, _ = _connect(base, "docs@example.com")
    c = httpx.Client(base_url=base)
    c.post("/upload", data={"action": "login", "email": "docs@example.com", "password": PASSWORD})
    pdf = (Path(__file__).parent / "sample_notes.pdf").read_bytes()
    r = c.post("/upload", data={"action": "upload", "note": "Endocrinology lecture notes"},
               files=[("file", ("Endocrine summary.pdf", pdf, "application/pdf")),
                      ("file", ("thyroid.txt", "Thyroid storm: fever, tachycardia.\n".encode(), "text/plain"))])
    assert r.status_code == 200, r.text
    assert len(re.findall(r"000-Inbox/Yakala/[^<]+\.md", r.text)) == 2
    # Sources become searchable page by page and the card closes; the coach doesn't have to turn them into notes.
    calls = [("list_captures", {}), ("search_vault", {"query": "thyroid storm symptoms"}),
             ("read_capture", {"id": "missing-card"})]
    if shutil.which("pdftotext"):
        calls.append(("search_vault", {"query": "graves tsh receptor antibody"}))
    out = asyncio.run(_tools(base, tok, calls))
    cards = _ok(out["list_captures"][0])["kartlar"]
    assert len(cards) == 2 and all(k["durum"] == "islendi" for k in cards), cards
    assert "sources/thyroid/p0001.md" in [r["source"] for r in _ok(out["search_vault"][0])["records"]]
    assert out["read_capture"][0]["error"] is True
    if shutil.which("pdftotext"):
        assert "sources/Endocrine summary/p0001.md" in [r["source"] for r in _ok(out["search_vault"][1])["records"]]
    # The uploaded PDF stays in the vault (opens in Obsidian); the extracted raw text is in a hidden folder.
    r = httpx.post(f"{base}/account/obsidian", data={"email": "docs@example.com", "password": PASSWORD})
    auth = ("docs@example.com", re.findall(r"<code>([^<]+)</code>", r.text)[2])
    listing = httpx.request("PROPFIND", f"{base}/dav/{quote('📥 000-Inbox/Yakala/dosyalar/')}", headers={"Depth": "1"}, auth=auth)
    assert listing.status_code == 207 and ".pdf" in unquote(listing.text)
