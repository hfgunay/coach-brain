"""Telegram adaptörü: hatırlatma kanalı ve dosya gelen kutusu.

İnce tutuldu, çünkü kanal geçici olabilir: bu dosya ve `KOC_TELEGRAM_TOKEN` kaldırılınca bot
tamamen gider. Telegram'da veri tutulmaz; gelen dosyalar hemen öğrencinin kasasına yazılır.
Bot dil modeli çağırmaz: sohbet ve soru çözümü öğrencinin kendi Claude'unda kalır.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
from datetime import datetime
from typing import Any, Callable

import httpx2 as httpx
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from .config import Ayarlar
from .db import DB
from .hatirlatici import SAAT_BICIMI, SAAT_DILIMI, Mesaj, dugme_isle, sabah_mesaji
from .kasa import Kasa

log = logging.getLogger(__name__)
KANAL = "telegram"
# Bot API, botun indirebileceği dosyayı 20 MB ile sınırlar; büyük PDF'ler yükleme sayfasından gelir.
MAKS_INDIRME = 20 * 1024 * 1024
YARDIM = (
    "Ben çalışma koçunun hatırlatma botuyum.\n\n"
    "• Soru fotoğrafı, PDF ya da ders notu gönder: kasana kaydederim, Claude'da koçun görür.\n"
    "• Sabah günün tekrarlarını ve görevlerini, akşam görevlerin bitip bitmediğini sorarım.\n\n"
    "Komutlar:\n"
    "/bugun - bugünün listesini şimdi gönder\n"
    "/saat 08:30 21:30 - sabah ve akşam saatini değiştir\n"
    "/sessiz - hatırlatmaları durdur, /devam - yeniden başlat\n"
    "/ayril - bu sohbetin bağlantısını kaldır"
)


class Telegram:
    ad = KANAL

    def __init__(self, ayarlar: Ayarlar, db: DB, kasa_ac: Callable[[str], Kasa],
                 kaydet: Callable[[str, list[tuple[str, bytes]], str], list[str]]):
        self.ayarlar, self.db, self.kasa_ac, self.kaydet = ayarlar, db, kasa_ac, kaydet
        self._api = f"{ayarlar.telegram_api}/bot{ayarlar.telegram_token}"
        self._dosya_api = f"{ayarlar.telegram_api}/file/bot{ayarlar.telegram_token}"
        # Telegram her webhook isteğinde bu değeri başlıkta geri yollar; sahte istekleri ayırır.
        self.gizli = hmac.new(ayarlar.telegram_token.encode(), b"webhook", hashlib.sha256).hexdigest()
        self.kullanici_adi: str | None = None

    # --- Bot API ---------------------------------------------------------
    async def _cagir(self, metot: str, **veri: Any) -> Any:
        async with httpx.AsyncClient(timeout=30) as http:
            r = await http.post(f"{self._api}/{metot}", json=veri)
        govde = r.json()
        if not govde.get("ok"):
            raise RuntimeError(f"Telegram {metot}: {govde.get('description')}")
        return govde.get("result")

    async def kur(self) -> None:
        """Bot adını öğrenir ve webhook'u bu sunucuya yönlendirir."""
        ben = await self._cagir("getMe")
        self.kullanici_adi = ben.get("username")
        if self.ayarlar.public_url.startswith("https://"):
            await self._cagir("setWebhook", url=f"{self.ayarlar.public_url}/telegram/webhook", secret_token=self.gizli,
                              allowed_updates=["message", "callback_query"], drop_pending_updates=False)
        else:
            log.warning("Telegram webhook kurulmadı: KOC_PUBLIC_URL https değil.")

    async def gonder(self, hedef: str, mesaj: Mesaj) -> None:
        veri: dict[str, Any] = {"chat_id": hedef, "text": mesaj.metin}
        if mesaj.dugmeler:
            veri["reply_markup"] = {"inline_keyboard": [[{"text": d.etiket, "callback_data": d.veri} for d in satir]
                                                        for satir in mesaj.dugmeler]}
        await self._cagir("sendMessage", **veri)

    async def _yaz(self, hedef: Any, metin: str) -> None:
        await self.gonder(str(hedef), Mesaj(metin))

    def baglanti_adresi(self, user_id: str) -> str | None:
        if not self.kullanici_adi:
            return None
        return f"https://t.me/{self.kullanici_adi}?start={self.db.baglanti_kodu_uret(user_id)}"

    # --- webhook ---------------------------------------------------------
    async def webhook(self, request: Request) -> Response:
        if not hmac.compare_digest(request.headers.get("x-telegram-bot-api-secret-token", ""), self.gizli):
            return Response(status_code=403)
        try:
            guncelleme = await request.json()
            if "callback_query" in guncelleme:
                await self._dugme(guncelleme["callback_query"])
            elif "message" in guncelleme:
                await self._mesaj(guncelleme["message"])
        except Exception:  # noqa: BLE001 - Telegram aynı güncellemeyi tekrar tekrar göndermesin
            log.exception("telegram güncellemesi")
        return JSONResponse({"ok": True})

    async def _mesaj(self, m: dict) -> None:
        sohbet = m.get("chat") or {}
        if sohbet.get("type") != "private":
            return  # grup sohbetlerinde çalışmaz: kasa tek kişiye ait
        hedef = str(sohbet["id"])
        metin = (m.get("text") or "").strip()
        if metin.startswith("/start"):
            return await self._baslat(hedef, metin[len("/start"):].strip())
        b = self.db.baglanti(KANAL, hedef)
        if b is None:
            return await self._yaz(hedef, "Bu sohbet bir hesaba bağlı değil. Yükleme sayfasındaki "
                                          "\"Telegram'a bağla\" düğmesine bas.")
        if "photo" in m or "document" in m:
            return await self._dosya(hedef, b["user_id"], m)
        komut, *argumanlar = metin.split() or [""]
        komut = komut.split("@")[0].lower()
        if komut == "/bugun":
            kasa = self.kasa_ac(b["user_id"])
            mesaj = await asyncio.to_thread(sabah_mesaji, kasa, datetime.now(SAAT_DILIMI).date())
            return await self.gonder(hedef, mesaj or Mesaj("Bugün için tarihi gelen görev ya da tekrar yok. 🎉"))
        if komut == "/saat":
            if len(argumanlar) != 2 or not all(SAAT_BICIMI.match(a) for a in argumanlar):
                return await self._yaz(hedef, "Örnek: /saat 08:30 21:30")
            self.db.baglanti_guncelle(KANAL, hedef, sabah=argumanlar[0], aksam=argumanlar[1])
            return await self._yaz(hedef, f"Tamam: sabah {argumanlar[0]}, akşam {argumanlar[1]}.")
        if komut in ("/sessiz", "/devam"):
            self.db.baglanti_guncelle(KANAL, hedef, sessiz=int(komut == "/sessiz"))
            return await self._yaz(hedef, "Hatırlatmaları durdurdum. /devam ile açarsın." if komut == "/sessiz"
                                   else "Hatırlatmalar yeniden açık.")
        if komut == "/ayril":
            self.db.baglantiyi_kaldir(KANAL, hedef)
            return await self._yaz(hedef, "Bağlantı kaldırıldı. Kasandaki hiçbir şey silinmedi.")
        await self._yaz(hedef, "Sohbet ve soru çözümü Claude'da: koçuna orada yaz. Buraya fotoğraf ya da PDF "
                               "gönderebilirsin.\n\n" + YARDIM)

    async def _baslat(self, hedef: str, kod: str) -> None:
        user_id = self.db.baglanti_kodu_kullan(kod) if kod else None
        if user_id is None:
            if self.db.baglanti(KANAL, hedef):
                return await self._yaz(hedef, YARDIM)
            return await self._yaz(hedef, "Bağlantı kodu geçersiz ya da süresi dolmuş. Yükleme sayfasından "
                                          "\"Telegram'a bağla\" düğmesine yeniden bas.")
        simdi = datetime.now(SAAT_DILIMI)
        self.db.baglan(user_id, KANAL, hedef, self.ayarlar.sabah_saati, self.ayarlar.aksam_saati,
                       simdi.date().isoformat(), simdi.strftime("%H:%M"))
        await self._yaz(hedef, f"Bağlandı! ✅ Sabah {self.ayarlar.sabah_saati} ve akşam {self.ayarlar.aksam_saati}"
                               f" yazacağım.\n\n" + YARDIM)

    async def _dosya(self, hedef: str, user_id: str, m: dict) -> None:
        if "photo" in m:
            bilgi = max(m["photo"], key=lambda p: p.get("file_size", 0))
            ad = f"telegram-{m.get('message_id', 'foto')}.jpg"
        else:
            bilgi = m["document"]
            ad = bilgi.get("file_name") or f"telegram-{m.get('message_id', 'dosya')}"
        if bilgi.get("file_size", 0) > MAKS_INDIRME:
            return await self._yaz(hedef, "Telegram botları 20 MB'tan büyük dosyayı alamıyor. Bunu yükleme "
                                          f"sayfasından gönder: {self.ayarlar.public_url}/yukle")
        dosya = await self._cagir("getFile", file_id=bilgi["file_id"])
        async with httpx.AsyncClient(timeout=120) as http:
            r = await http.get(f"{self._dosya_api}/{dosya['file_path']}")
        r.raise_for_status()
        yollar = await asyncio.to_thread(self.kaydet, user_id, [(ad, r.content)], (m.get("caption") or "")[:300])
        await self._yaz(hedef, "Kaydettim: " + ", ".join(yollar) + "\n\nClaude'da koçuna \"yüklediğime bakalım\" yaz.")

    async def _dugme(self, cq: dict) -> None:
        hedef = str(((cq.get("message") or {}).get("chat") or {}).get("id", ""))
        b = self.db.baglanti(KANAL, hedef)
        if b is None:
            cevap = "Bu sohbet bir hesaba bağlı değil."
        else:
            kasa = self.kasa_ac(b["user_id"])
            cevap = await asyncio.to_thread(dugme_isle, kasa, str(cq.get("data", "")), datetime.now(SAAT_DILIMI).date())
        await self._cagir("answerCallbackQuery", callback_query_id=cq["id"], text=cevap[:190])
        mesaj = cq.get("message") or {}
        if mesaj.get("message_id"):
            await self._cagir("editMessageText", chat_id=hedef, message_id=mesaj["message_id"],
                              text=f"{mesaj.get('text', '')}\n\n→ {cevap}")
