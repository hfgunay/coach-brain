"""Gerçek HTTP sunucusuyla uçtan uca: OAuth (DCR + PKCE), MCP araçları, kullanıcı ayrımı, WebDAV."""
import asyncio
import base64
import hashlib
import json
from urllib.parse import unquote
import re
import secrets
import socket
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import httpx2
import pytest
import uvicorn

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from calisma_kocu.config import Ayarlar
from calisma_kocu.server import uygulama_kur

DAVET = "deneme-davet"
CB = "http://localhost:9/cb"


def _port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    port = _port()
    url = f"http://127.0.0.1:{port}"
    ayarlar = Ayarlar(public_url=url, data_dir=Path(tmp_path_factory.mktemp("data")), host="127.0.0.1",
                      port=port, davet_kodlari=[DAVET])
    server = uvicorn.Server(uvicorn.Config(uygulama_kur(ayarlar), host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        try:
            if httpx.get(f"{url}/saglik").status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.05)
    yield url
    server.should_exit = True
    thread.join(5)


def _baglan(base, email, sifre="cok-gizli-sifre", mod="kayit", davet=DAVET):
    """Bir MCP istemcisinin yaptığı OAuth akışını taklit eder; (access, refresh, client_id) döner."""
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
                                    "state": "durum123", "scope": "koc", "resource": f"{base}/mcp"})
    assert r.status_code == 302, r.text
    login = urlparse(r.headers["location"])
    istek = parse_qs(login.query)["istek"][0]
    page = c.get(f"{login.path}?{login.query}")
    assert page.status_code == 200 and "Çalışma Koçu" in page.text and "test (localhost)" in page.text
    r = c.post("/hesap/giris", data={"istek": istek, "mod": mod, "email": email, "sifre": sifre, "davet": davet})
    assert r.status_code == 303, r.text
    q = parse_qs(urlparse(r.headers["location"]).query)
    assert q["state"] == ["durum123"]
    tok = c.post("/token", data={"grant_type": "authorization_code", "code": q["code"][0], "redirect_uri": CB,
                                 "client_id": client_id, "code_verifier": verifier, "resource": f"{base}/mcp"})
    assert tok.status_code == 200, tok.text
    # Kod ikinci kez kullanılamaz.
    again = c.post("/token", data={"grant_type": "authorization_code", "code": q["code"][0], "redirect_uri": CB,
                                   "client_id": client_id, "code_verifier": verifier})
    assert again.status_code == 400
    return tok.json()["access_token"], tok.json()["refresh_token"], client_id


async def _araclar(base, token, calls):
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


def test_yetkisiz_istek_reddedilir(base):
    r = httpx.post(f"{base}/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                   headers={"Accept": "application/json, text/event-stream"})
    assert r.status_code == 401
    assert "resource_metadata" in r.headers.get("www-authenticate", "")


def test_tanimadik_donus_adresi_kaydedilemez(base):
    r = httpx.post(f"{base}/register", json={"redirect_uris": ["https://saldirgan.example/cb"],
                                             "token_endpoint_auth_method": "none"})
    assert r.status_code == 400 and r.json()["error"] == "invalid_redirect_uri"


def test_davet_kodu_olmadan_kayit_olunmaz(base):
    with pytest.raises(AssertionError):
        _baglan(base, "davetsiz@ornek.com", davet="yanlis")


def _ok(item):
    assert item["error"] is False, item
    return item["data"]


def test_uctan_uca_avenoxbeyin_kasasi(base):
    a_tok, a_refresh, a_client = _baglan(base, "ayse@ornek.com")
    out = asyncio.run(_araclar(base, a_tok, [
        ("kaldigim_yer", {}),
        ("talimatlari_oku", {"hangisi": "calisma-kocu"}),
        ("not_olustur", {"kaynak": "notes/tus/farmakoloji/digoksin-hiperkalemi.md",
                         "metin": "# Digoksin ve hiperkalemi\n\nDigoksin toksisitesinde hiperkalemi olur; soruyu "
                                  "hipokalemi sanıp yanlış yaptım.\n",
                         "metadata": {"title": "Digoksin hiperkalemi hatası", "review_at": "2026-01-01",
                                      "tags": ["hata", "farmakoloji"]}}),
        ("gorev_olustur", {"kaynak": "tasks/tus-farma-otonom.md", "metin": "Farmakoloji otonom: konu + 40 soru",
                           "metadata": {"id": "tus-farma-otonom", "title": "Farmakoloji otonom", "kind": "task",
                                        "status": "active", "owner": "Ayşe", "project": "tus",
                                        "due_at": "2026-01-02"}}),
        ("kasada_ara", {"sorgu": "digoksinin toksisitesinde potasyum yüksekliği"}),
        ("gorev_guncelle", {"id": "tus-farma-otonom", "beklenen_revision": 1, "degisiklikler": {"status": "done"}}),
        ("gorev_guncelle", {"id": "tus-farma-otonom", "beklenen_revision": 1, "degisiklikler": {"status": "done"}}),
        ("not_oku", {"kaynak": "🔮 850-Companion/Threads.md"}),
        ("kasa_durumu", {}),
        ("eki_goster", {"yol": "../../oturum.key"}),
        ("not_oku", {"kaynak": "../../../calisma_kocu.sqlite3"}),
    ]))
    ilk = _ok(out["kaldigim_yer"][0])
    assert ilk["oturum"] and "Receipt session=" in ilk["baglam"] and "850-Companion/Core.md" in ilk["baglam"]
    assert "<kasa>" not in ilk["baglam"] or "/vaults/" not in ilk["baglam"]
    assert "kasada_ara" in _ok(out["talimatlari_oku"][0])["calisma-kocu"]
    assert _ok(out["not_olustur"][0]).get("cikis_kodu") == 0
    assert _ok(out["gorev_olustur"][0])["due_at"] == "2026-01-02"
    bulunan = [r["source"] for r in _ok(out["kasada_ara"][0])["records"]]
    assert "notes/tus/farmakoloji/digoksin-hiperkalemi.md" in bulunan
    assert _ok(out["gorev_guncelle"][0])["status"] == "done"
    assert out["gorev_guncelle"][1]["data"]["error"] == "RevisionConflict"  # repo'nun revision kuralı
    threads = _ok(out["not_oku"][0])
    assert "Active Threads" in json.dumps(threads, ensure_ascii=False)
    assert _ok(out["kasa_durumu"][0])["review"]["due_count"] == 1  # review_at tarihi geçmiş not
    assert out["eki_goster"][0]["error"] is True
    assert "error" in json.dumps(out["not_oku"][1]["data"]) or out["not_oku"][1]["error"]

    # Sonraki sohbette repo'nun kendi hook'u tarihi gelen tekrarı getirir.
    out2 = asyncio.run(_araclar(base, a_tok, [("kaldigim_yer", {})]))
    assert "Due reviews: 1" in _ok(out2["kaldigim_yer"][0])["baglam"]

    # İkinci kullanıcı birincinin kasasını göremez.
    b_tok, _, _ = _baglan(base, "zeynep@ornek.com")
    out_b = asyncio.run(_araclar(base, b_tok, [("kasada_ara", {"sorgu": "digoksin hiperkalemi"}),
                                               ("not_oku", {"kaynak": "notes/tus/farmakoloji/digoksin-hiperkalemi.md"})]))
    assert _ok(out_b["kasada_ara"][0]).get("records", []) == []
    assert _ok(out_b["not_oku"][0]).get("exists") is False

    # Yenileme belirteci döner ve tek kullanımlıktır.
    data = {"grant_type": "refresh_token", "refresh_token": a_refresh, "client_id": a_client}
    r = httpx.post(f"{base}/token", data=data)
    assert r.status_code == 200 and r.json()["access_token"] != a_tok
    assert httpx.post(f"{base}/token", data=data).status_code == 400


PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg==")


def test_fotograf_yukleme_ve_gosterme(base):
    tok, _, _ = _baglan(base, "foto@ornek.com")
    c = httpx.Client(base_url=base)
    assert "Giriş yap" in c.get("/yukle").text
    assert c.post("/yukle", data={"islem": "giris", "email": "foto@ornek.com", "sifre": "yanlis-sifre"}).status_code == 400
    r = c.post("/yukle", data={"islem": "giris", "email": "foto@ornek.com", "sifre": "cok-gizli-sifre"})
    assert r.status_code == 200 and "calisma_kocu_oturum" in r.headers.get("set-cookie", "")
    r = c.post("/yukle", data={"islem": "yukle"}, files={"dosya": ("soru.png", PNG, "image/png")})
    assert r.status_code == 200, r.text
    yol = re.findall(r"<code>([^<]+)</code>", r.text)[0]
    assert yol.startswith("Ekler/") and yol.endswith(".jpg")
    # Çerezsiz istemci yükleyemez.
    assert httpx.post(f"{base}/yukle", data={"islem": "yukle"},
                      files={"dosya": ("x.png", PNG, "image/png")}).status_code == 401
    out = asyncio.run(_araclar(base, tok, [("ekleri_listele", {}), ("eki_goster", {"yol": yol})]))
    assert _ok(out["ekleri_listele"][0])["ekler"][0]["yol"] == yol
    assert out["eki_goster"][0]["type"] == "image" and out["eki_goster"][0]["mime"] == "image/jpeg"


def test_webdav_obsidian_esitleme(base):
    tok, _, _ = _baglan(base, "dav@ornek.com")
    _baglan(base, "baska@ornek.com")
    asyncio.run(_araclar(base, tok, [("kaldigim_yer", {})]))  # kasa kurulsun
    r = httpx.post(f"{base}/hesap/obsidian", data={"email": "dav@ornek.com", "sifre": "cok-gizli-sifre"})
    assert r.status_code == 200
    sifre = re.findall(r"<code>([^<]+)</code>", r.text)[2]
    auth = ("dav@ornek.com", sifre)
    assert httpx.request("PROPFIND", f"{base}/dav/", headers={"Depth": "1"}).status_code == 401
    assert httpx.request("PROPFIND", f"{base}/dav/", auth=("dav@ornek.com", "cok-gizli-sifre")).status_code == 401
    kok = httpx.request("PROPFIND", f"{base}/dav/", headers={"Depth": "1"}, auth=auth)
    assert kok.status_code == 207 and "850-Companion" in unquote(kok.text)
    # Yönetilen çalışma dosyaları ve gizli klasörler eşitlenmez.
    assert "beyin.py" not in kok.text and ".agents" not in kok.text and ".claude" not in kok.text
    assert httpx.get(f"{base}/dav/beyin.py", auth=auth).status_code == 404
    assert httpx.put(f"{base}/dav/.agents/skills/x/SKILL.md", content=b"x", auth=auth).status_code in (404, 409)
    # Obsidian'da yazılmış not WebDAV ile gelir ve repo'nun aramasında çıkar.
    assert httpx.request("MKCOL", f"{base}/dav/Konular/", auth=auth).status_code in (201, 405)
    body = "# Tiroid\n\nGraves hastalığında TSH reseptör antikoru vardır. [[Hipertiroidi]]\n".encode()
    assert httpx.put(f"{base}/dav/Konular/Tiroid.md", content=body, auth=auth).status_code in (201, 204)
    out = asyncio.run(_araclar(base, tok, [("kasada_ara", {"sorgu": "graves hastalığı antikorları"})]))
    assert "Konular/Tiroid.md" in [r["source"] for r in _ok(out["kasada_ara"][0])["records"]]
    # Başka kullanıcının şifresi bu kasayı açamaz, yol hilesi de çalışmaz.
    r = httpx.post(f"{base}/hesap/obsidian", data={"email": "baska@ornek.com", "sifre": "cok-gizli-sifre"})
    baska = ("baska@ornek.com", re.findall(r"<code>([^<]+)</code>", r.text)[2])
    assert httpx.get(f"{base}/dav/Konular/Tiroid.md", auth=baska).status_code == 404
    assert httpx.get(f"{base}/dav/..%2F..%2Fcalisma_kocu.sqlite3", auth=baska).status_code in (400, 403, 404)
