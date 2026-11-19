"""Kanaldan bağımsız hatırlatma çekirdeği.

Bu modül de hafıza mantığı içermez: ne hatırlatılacağı öğrencinin avenoxbeyin kasasından gelir.
- tarihi gelen tekrarlar: motorun `triage` çıktısındaki `review.due` (notların `review_at` alanı)
- günü gelen görevler: `tasks/` altındaki görev kayıtları (`due_at`, `status`)
- düğmeyle verilen cevap: motorun `task-update` komutu (revision kontrolüyle)

Mesajı nereye göndereceğini bilmez. Telegram, ileride WhatsApp ya da kendi uygulamamız `Kanal`
protokolünü uygulayan ince bir adaptördür; kanalı değiştirmek bu dosyaya dokunmaz.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, Protocol
from zoneinfo import ZoneInfo

from .db import DB
from .kasa import Kasa

log = logging.getLogger(__name__)
SAAT_DILIMI = ZoneInfo("Europe/Istanbul")
ACIK_DURUMLAR = {"active", "waiting"}
SAAT_BICIMI = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


@dataclass
class Dugme:
    etiket: str
    veri: str  # kanal geri gönderir; Telegram'da en fazla 64 bayt


@dataclass
class Mesaj:
    metin: str
    dugmeler: list[list[Dugme]] = field(default_factory=list)


class Kanal(Protocol):
    ad: str

    async def gonder(self, hedef: str, mesaj: Mesaj) -> None: ...


# --- kasadan okuma -----------------------------------------------------------
def _on_bilgi(path: Path) -> dict:
    """Markdown ön bilgisini okur. Motor görevleri JSON, notları basit YAML yazar."""
    try:
        metin = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}
    if not metin.startswith("---"):
        return {}
    son = metin.find("\n---", 3)
    if son < 0:
        return {}
    govde = metin[3:son].strip()
    if govde.startswith("{"):
        try:
            veri = json.loads(govde)
            return veri if isinstance(veri, dict) else {}
        except json.JSONDecodeError:
            return {}
    veri = {}
    for satir in govde.splitlines():
        if ":" in satir and not satir.startswith((" ", "-")):
            k, v = satir.split(":", 1)
            veri[k.strip()] = v.strip().strip('"').strip("'")
    return veri


def _gorev_kayitlari(kasa: Kasa) -> list[dict]:
    kok = kasa.vault / "tasks"
    out = []
    for path in (kok.rglob("*.md") if kok.is_dir() else []):
        fm = _on_bilgi(path)
        if fm.get("kind") == "task" and fm.get("id"):
            out.append({"id": str(fm["id"]), "baslik": str(fm.get("title") or path.stem),
                        "due_at": str(fm.get("due_at") or "")[:10], "status": fm.get("status"),
                        "revision": fm.get("revision")})
    return out


def gorevler(kasa: Kasa, bugun: date) -> list[dict]:
    """Günü gelmiş ya da geçmiş açık görevler, en eski önce."""
    out = [g for g in _gorev_kayitlari(kasa)
           if g["status"] in ACIK_DURUMLAR and g["due_at"] and g["due_at"] <= bugun.isoformat()]
    return sorted(out, key=lambda g: (g["due_at"], g["id"]))


def tekrarlar(kasa: Kasa) -> list[dict]:
    """Motorun triage çıktısındaki tarihi gelen tekrarlar, başlıklarıyla."""
    triage = kasa.cli("triage")
    out = []
    for kayit in (triage.get("review") or {}).get("due", []):
        kaynak = kayit.get("source") or ""
        try:
            baslik = _on_bilgi(kasa.dosya_yolu(kaynak)).get("title")
        except Exception:  # noqa: BLE001 - başlık bulunamazsa dosya adı yeter
            baslik = None
        out.append({"kaynak": kaynak, "baslik": baslik or Path(kaynak).stem, "gecikme": kayit.get("days_overdue", 0)})
    return out


# --- mesajlar ----------------------------------------------------------------
def sabah_mesaji(kasa: Kasa, bugun: date) -> Mesaj | None:
    tekrar, gorev = tekrarlar(kasa), gorevler(kasa, bugun)
    if not tekrar and not gorev:
        return None
    satirlar = ["Günaydın! Bugün seni bekleyenler:"]
    if gorev:
        satirlar.append(f"\n📋 Görevler ({len(gorev)})")
        satirlar += [f"• {g['baslik']}" + (" (gecikti)" if g["due_at"] < bugun.isoformat() else "") for g in gorev[:8]]
    if tekrar:
        satirlar.append(f"\n🔁 Tekrar zamanı gelenler ({len(tekrar)})")
        satirlar += [f"• {t['baslik']}" for t in tekrar[:8]]
    satirlar.append("\nBaşlamak için Claude'da koçuna \"başlayalım\" yaz.")
    return Mesaj("\n".join(satirlar))


def aksam_mesajlari(kasa: Kasa, bugun: date) -> list[Mesaj]:
    out = []
    for g in gorevler(kasa, bugun):
        dugmeler = []
        if len(f"g|d|{g['id']}".encode()) <= 64:
            dugmeler = [[Dugme("✅ Bitti", f"g|d|{g['id']}"), Dugme("➡️ Yarına kaldı", f"g|y|{g['id']}")]]
        out.append(Mesaj(f"Bugünkü görev: {g['baslik']}\nBitti mi?", dugmeler))
    return out


def dugme_isle(kasa: Kasa, veri: str, bugun: date) -> str:
    """Düğme cevabını motorun task-update komutuyla işler; revision çakışırsa bir kez yeniden okur."""
    try:
        tur, eylem, gorev_id = veri.split("|", 2)
    except ValueError:
        return "Bu düğme artık geçerli değil."
    if tur != "g" or eylem not in ("d", "y"):
        return "Bu düğme artık geçerli değil."
    for _ in range(2):
        gorev = next((g for g in _gorev_kayitlari(kasa) if g["id"] == gorev_id), None)
        if gorev is None:
            return "Bu görev bulunamadı."
        if gorev["status"] not in ACIK_DURUMLAR:
            return "Bu görev zaten kapanmış."
        degisiklik = ({"status": "done"} if eylem == "d" else
                      {"due_at": (max(bugun, date.fromisoformat(gorev["due_at"] or bugun.isoformat())) + timedelta(days=1)).isoformat()})
        sonuc = kasa.cli("task-update", girdi={"id": gorev_id, "expected_revision": gorev["revision"],
                                               "changes": degisiklik})
        if not sonuc.get("error"):
            return "Harika, bitti olarak işaretledim. 👏" if eylem == "d" else "Tamam, yarına aldım."
        if sonuc.get("error") != "RevisionConflict":
            log.warning("task-update başarısız: %s", sonuc)
            return "Kaydedemedim; koçuna söylersen o güncellesin."
    return "Görev bu arada değişmiş; koçuna söylersen o güncellesin."


# --- zamanlayıcı -------------------------------------------------------------
class Zamanlayici:
    """Her dakika bağlı kullanıcılara bakar; sabah ve akşam saatini geçen ve o gün gönderilmemiş
    mesajları gönderir. Tek kopya çalışan sunucu için tasarlandı (db.py ile aynı varsayım)."""

    def __init__(self, db: DB, kanallar: dict[str, Kanal], kasa_ac: Callable[[str], Kasa]):
        self.db, self.kanallar, self.kasa_ac = db, kanallar, kasa_ac

    async def calis(self, aralik: float = 60) -> None:
        while True:
            try:
                await self.tur(datetime.now(SAAT_DILIMI))
            except Exception:  # noqa: BLE001 - döngü durmasın
                log.exception("hatırlatma turu")
            await asyncio.sleep(aralik)

    async def tur(self, simdi: datetime) -> int:
        """Gönderilmesi gereken mesajları gönderir; gönderilen mesaj sayısını döndürür."""
        bugun, saat = simdi.date().isoformat(), simdi.strftime("%H:%M")
        sayi = 0
        for b in self.db.baglantilar():
            kanal = self.kanallar.get(b["kanal"])
            if kanal is None or b["sessiz"]:
                continue
            for zaman, son_alan in (("sabah", "son_sabah"), ("aksam", "son_aksam")):
                if saat < b[zaman] or b[son_alan] == bugun:
                    continue
                self.db.baglanti_gonderildi(b["user_id"], b["kanal"], son_alan, bugun)  # çökse de tekrar atma
                kasa = self.kasa_ac(b["user_id"])
                mesajlar = await asyncio.to_thread(
                    lambda: [m for m in [sabah_mesaji(kasa, simdi.date())] if m] if zaman == "sabah"
                    else aksam_mesajlari(kasa, simdi.date()))
                for m in mesajlar:
                    await kanal.gonder(b["hedef"], m)
                    sayi += 1
        return sayi
