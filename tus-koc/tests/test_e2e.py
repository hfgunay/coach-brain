"""Gerçek HTTP sunucusuyla uçtan uca: OAuth (DCR + PKCE), MCP araçları, kullanıcı ayrımı, WebDAV."""
import asyncio
import base64
import hashlib
import json
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

from tus_koc.config import Ayarlar
from tus_koc.server import uygulama_kur

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
    assert page.status_code == 200 and "TUS Koçu" in page.text and "test (localhost)" in page.text
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
                    text = res.content[0].text if res.content else ""
                    out.setdefault(name, []).append(
                        {"error": res.is_error, "data": res.structured_content or (json.loads(text) if text.startswith("{") else text)})
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


def test_uctan_uca(base):
    a_tok, a_refresh, a_client = _baglan(base, "ayse@ornek.com")
    out = asyncio.run(_araclar(base, a_tok, [
        ("kaldigim_yer", {}),
        ("not_yaz", {"baslik": "Digoksin", "icerik": "Digoksin toksisitesinde [[Hiperkalemi]] olur.",
                     "ders": "Farmakoloji"}),
        ("notlarda_ara", {"sorgu": "digoksinin toksisitesi"}),
        ("soru_sonucu_kaydet", {"ders": "Farmakoloji", "konu": "Otonom", "dogru": 5, "yanlis": 5}),
        ("oturumu_kaydet", {"ozet": "Digoksin çalışıldı.", "calisilan_konular": ["Digoksin"]}),
        ("not_oku", {"ad": "../../etc/passwd"}),
    ]))
    assert {"kaldigim_yer", "notlarda_ara", "not_yaz", "oturumu_kaydet", "calisma_plani_olustur"} <= set(out["_tools"])
    assert out["kaldigim_yer"][0]["data"]["profil_eksik"]
    assert out["notlarda_ara"][0]["data"]["sonuclar"][0]["yol"] == "Konular/Farmakoloji/Digoksin.md"
    assert out["not_oku"][0]["error"] is True

    # İkinci kullanıcı birinci kullanıcının notunu göremez.
    b_tok, _, _ = _baglan(base, "zeynep@ornek.com")
    out_b = asyncio.run(_araclar(base, b_tok, [("notlarda_ara", {"sorgu": "digoksin"}),
                                               ("not_oku", {"ad": "Digoksin"})]))
    assert out_b["notlarda_ara"][0]["data"]["sonuclar"] == []
    assert out_b["not_oku"][0]["error"] is True

    # Aynı hesaba yeniden giriş aynı kasayı açar.
    a2_tok, _, _ = _baglan(base, "ayse@ornek.com", mod="giris")
    out_a2 = asyncio.run(_araclar(base, a2_tok, [("kaldigim_yer", {})]))
    assert "Digoksin" in out_a2["kaldigim_yer"][0]["data"]["son_oturumlar"][0]

    # Yenileme belirteci döner ve tek kullanımlıktır.
    data = {"grant_type": "refresh_token", "refresh_token": a_refresh, "client_id": a_client}
    r = httpx.post(f"{base}/token", data=data)
    assert r.status_code == 200 and r.json()["access_token"] != a_tok
    assert httpx.post(f"{base}/token", data=data).status_code == 400


def test_webdav_obsidian_esitleme(base):
    tok, _, _ = _baglan(base, "dav@ornek.com")
    _baglan(base, "baska@ornek.com")
    r = httpx.post(f"{base}/hesap/obsidian", data={"email": "dav@ornek.com", "sifre": "cok-gizli-sifre"})
    assert r.status_code == 200
    sifre = re.findall(r"<code>([^<]+)</code>", r.text)[2]
    auth = ("dav@ornek.com", sifre)
    assert httpx.request("PROPFIND", f"{base}/dav/", headers={"Depth": "1"}).status_code == 401
    assert httpx.request("PROPFIND", f"{base}/dav/", auth=("dav@ornek.com", "cok-gizli-sifre")).status_code == 401
    # Obsidian'da yazılmış bir not WebDAV ile gelir...
    assert httpx.request("MKCOL", f"{base}/dav/Konular/", auth=auth).status_code in (201, 405)
    body = "# Tiroid\n\nGraves hastalığında TSH reseptör antikoru vardır. [[Hipertiroidi]]\n".encode()
    assert httpx.put(f"{base}/dav/Konular/Tiroid.md", content=body, auth=auth).status_code in (201, 204)
    listing = httpx.request("PROPFIND", f"{base}/dav/Konular/", headers={"Depth": "1"}, auth=auth)
    assert listing.status_code == 207 and "Tiroid.md" in listing.text
    # ...ve koç aynı notu arar.
    out = asyncio.run(_araclar(base, tok, [("notlarda_ara", {"sorgu": "graves hastalığı antikorları"}),
                                          ("konu_iliskileri", {"konu": "Tiroid"})]))
    assert out["notlarda_ara"][0]["data"]["sonuclar"][0]["yol"] == "Konular/Tiroid.md"
    assert out["konu_iliskileri"][0]["data"]["notu_olmayan_baglantilar"] == ["Hipertiroidi"]
    # Koçun yazdığı dosyalar da WebDAV'da görünür.
    assert "Profil.md" in httpx.request("PROPFIND", f"{base}/dav/Ko%C3%A7/", headers={"Depth": "1"}, auth=auth).text
    # Başka kullanıcının şifresi bu kasayı açamaz, yol hilesi de çalışmaz.
    r = httpx.post(f"{base}/hesap/obsidian", data={"email": "baska@ornek.com", "sifre": "cok-gizli-sifre"})
    baska = ("baska@ornek.com", re.findall(r"<code>([^<]+)</code>", r.text)[2])
    assert httpx.get(f"{base}/dav/Konular/Tiroid.md", auth=baska).status_code == 404
    assert httpx.get(f"{base}/dav/..%2F..%2Ftus_koc.sqlite3", auth=baska).status_code in (400, 403, 404)
