"""Telegram adaptörü ve hatırlatma çekirdeği: sahte Bot API ile uçtan uca."""
import asyncio
import hashlib
import hmac
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pytest
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from calisma_kocu.config import Ayarlar
from calisma_kocu.hatirlatici import SAAT_DILIMI
from calisma_kocu.server import uygulama_kur
from test_e2e import DAVET, PNG, _araclar, _baglan, _ok, _port  # noqa: F401 (DAVET fixture'da)

TOKEN = "123:ABC"
GIZLI = hmac.new(TOKEN.encode(), b"webhook", hashlib.sha256).hexdigest()


class SahteTelegram:
    def __init__(self):
        self.cagrilar: list[tuple[str, dict]] = []

    def gonderilen(self, metot="sendMessage"):
        return [v for m, v in self.cagrilar if m == metot]

    async def api(self, request: Request):
        metot = request.path_params["metot"]
        veri = await request.json()
        self.cagrilar.append((metot, veri))
        sonuc = {"getMe": {"username": "deneme_bot"},
                 "getFile": {"file_path": "photos/soru.png"}}.get(metot, {"message_id": len(self.cagrilar)})
        return JSONResponse({"ok": True, "result": sonuc})

    async def dosya(self, request: Request):
        return Response(PNG, media_type="image/png")

    def uygulama(self):
        return Starlette(routes=[Route(f"/bot{TOKEN}/{{metot}}", self.api, methods=["POST"]),
                                 Route(f"/file/bot{TOKEN}/{{yol:path}}", self.dosya)])


def _sunucu(app, port):
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    return server


@pytest.fixture(scope="module")
def ortam(tmp_path_factory):
    sahte = SahteTelegram()
    tg_port, port = _port(), _port()
    tg = _sunucu(sahte.uygulama(), tg_port)
    url = f"http://127.0.0.1:{port}"
    ayarlar = Ayarlar(public_url=url, data_dir=Path(tmp_path_factory.mktemp("tg")), host="127.0.0.1", port=port,
                      davet_kodlari=[DAVET], telegram_token=TOKEN, telegram_api=f"http://127.0.0.1:{tg_port}")
    app = uygulama_kur(ayarlar)
    srv = _sunucu(app, port)
    yield url, app, sahte
    srv.should_exit = tg.should_exit = True


def _guncelle(url, govde, gizli=GIZLI):
    return httpx.post(f"{url}/telegram/webhook", json=govde, headers={"X-Telegram-Bot-Api-Secret-Token": gizli})


def _yaz(url, sohbet, metin, tur="private"):
    return _guncelle(url, {"update_id": 1, "message": {"message_id": 10, "chat": {"id": sohbet, "type": tur},
                                                         "text": metin}})


def test_telegram_baglama_hatirlatma_ve_dugmeler(ortam):
    url, app, sahte = ortam
    tok, _, _ = _baglan(url, "tg@ornek.com")
    assert ("getMe", {}) in sahte.cagrilar  # bot açılışta adını öğrendi

    # Yükleme sayfasındaki "Telegram'a bağla" tek kullanımlık kodla t.me'ye yönlendirir.
    c = httpx.Client(base_url=url)
    assert c.get("/yukle/telegram").status_code == 303  # girişsiz: yükleme sayfasına
    c.post("/yukle", data={"islem": "giris", "email": "tg@ornek.com", "sifre": "cok-gizli-sifre"})
    assert "Telegram'a bağla" in c.get("/yukle").text
    r = c.get("/yukle/telegram")
    assert r.status_code == 303 and r.headers["location"].startswith("https://t.me/deneme_bot?start=")
    kod = r.headers["location"].split("start=")[1]

    # Sahte webhook isteği reddedilir; bağlı olmayan sohbet ve grup sohbeti kasaya erişemez.
    assert _guncelle(url, {"message": {}}, gizli="yanlis").status_code == 403
    _yaz(url, 777, "/bugun")
    assert "bağlı değil" in sahte.gonderilen()[-1]["text"]
    once = len(sahte.gonderilen())
    _yaz(url, -100, f"/start {kod}", tur="group")
    assert len(sahte.gonderilen()) == once

    _yaz(url, 555, f"/start {kod}")
    assert "Bağlandı" in sahte.gonderilen()[-1]["text"]
    _yaz(url, 556, f"/start {kod}")  # kod tek kullanımlık
    assert "geçersiz" in sahte.gonderilen()[-1]["text"]

    # Koçun kasaya yazdığı görev ve tekrar, botun mesajına repodaki alanlardan gelir.
    bugun = datetime.now(SAAT_DILIMI).date()
    asyncio.run(_araclar(url, tok, [
        ("gorev_olustur", {"kaynak": "tasks/farma.md", "metin": "Farmakoloji otonom: 40 soru",
                           "metadata": {"id": "farma-otonom", "title": "Farmakoloji otonom 40 soru", "kind": "task",
                                        "status": "active", "owner": "Ayşe", "project": "sinav",
                                        "due_at": bugun.isoformat()}}),
        ("gorev_olustur", {"kaynak": "tasks/kardiyo.md", "metin": "Kardiyoloji tekrar",
                           "metadata": {"id": "kardiyo", "title": "Kardiyoloji tekrar", "kind": "task",
                                        "status": "active", "owner": "Ayşe", "project": "sinav",
                                        "due_at": bugun.isoformat()}}),
        ("not_olustur", {"kaynak": "notes/sinav/endokrin/graves.md", "metin": "# Graves\n\nTRAb pozitif.\n",
                         "metadata": {"title": "Graves hatası", "review_at": (bugun - timedelta(days=1)).isoformat()}}),
    ]))
    _yaz(url, 555, "/bugun")
    sabah = sahte.gonderilen()[-1]["text"]
    assert "Farmakoloji otonom 40 soru" in sabah and "Graves hatası" in sabah

    # Zamanlayıcı: ertesi akşam sabah özeti + her görev için düğmeli soru; aynı gün tekrar göndermez.
    yarin_aksam = datetime.combine(bugun + timedelta(days=1), datetime.min.time(), SAAT_DILIMI).replace(hour=21, minute=31)
    assert asyncio.run(app.state.zamanlayici.tur(yarin_aksam)) == 3
    assert asyncio.run(app.state.zamanlayici.tur(yarin_aksam)) == 0
    dugmeli = [m for m in sahte.gonderilen() if "reply_markup" in m]
    veriler = {d["callback_data"] for m in dugmeli[-2:] for d in m["reply_markup"]["inline_keyboard"][0]}
    assert veriler == {"g|d|farma-otonom", "g|y|farma-otonom", "g|d|kardiyo", "g|y|kardiyo"}

    def bas(veri):
        _guncelle(url, {"update_id": 2, "callback_query": {"id": "cq", "data": veri, "message": {
            "message_id": 50, "chat": {"id": 555, "type": "private"}, "text": "Bugünkü görev"}}})
        return sahte.gonderilen("answerCallbackQuery")[-1]["text"]

    assert "bitti" in bas("g|d|farma-otonom").lower()
    assert "zaten kapanmış" in bas("g|d|farma-otonom")
    assert "yarına" in bas("g|y|kardiyo").lower()
    assert "→" in sahte.gonderilen("editMessageText")[-1]["text"]
    # Görevler motorun task-update'i ile değişti: biri kapandı, öteki yarına kaydı.
    _yaz(url, 555, "/bugun")
    son = sahte.gonderilen()[-1]["text"]
    assert "Farmakoloji" not in son and "Kardiyoloji" not in son and "Graves hatası" in son

    # Fotoğraf kasaya düşer, koç bağlayıcıdan görür; 20 MB üstü yükleme sayfasına yönlendirilir.
    _guncelle(url, {"update_id": 3, "message": {"message_id": 11, "chat": {"id": 555, "type": "private"},
                                                 "photo": [{"file_id": "kucuk", "file_size": 10},
                                                           {"file_id": "buyuk", "file_size": 70}]}})
    assert sahte.gonderilen("getFile")[-1] == {"file_id": "buyuk"}
    assert "Kaydettim: Ekler/" in sahte.gonderilen()[-1]["text"]
    out = asyncio.run(_araclar(url, tok, [("ekleri_listele", {})]))
    assert len(_ok(out["ekleri_listele"][0])["ekler"]) == 1
    _guncelle(url, {"update_id": 4, "message": {"message_id": 12, "chat": {"id": 555, "type": "private"},
                                                 "document": {"file_id": "pdf", "file_name": "kitap.pdf",
                                                              "file_size": 50 * 1024 * 1024}}})
    assert "20 MB" in sahte.gonderilen()[-1]["text"]

    # Saat ve sessiz komutları.
    _yaz(url, 555, "/saat 7:00 22:00")
    assert "Örnek" in sahte.gonderilen()[-1]["text"]
    _yaz(url, 555, "/saat 07:00 22:00")
    assert "07:00" in sahte.gonderilen()[-1]["text"]
    _yaz(url, 555, "/sessiz")
    ertesi = yarin_aksam + timedelta(days=1)
    assert asyncio.run(app.state.zamanlayici.tur(ertesi.replace(hour=22, minute=5))) == 0
    _yaz(url, 555, "/devam")
    assert asyncio.run(app.state.zamanlayici.tur(ertesi.replace(hour=22, minute=5))) >= 1
