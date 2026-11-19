"""Koçun iş mantığı. MCP araçları bu sınıfın ince sarmalayıcılarıdır.

Hafıza düzeni avenoxbeyin'in Companion dosyalarından uyarlanmıştır:
Core -> Profil, Last-Session -> Son Oturum, Threads -> Açık Konular, Kurallar -> Kurallar.
Tümü kullanıcının Markdown klasöründe, Obsidian'da okunabilir halde durur.
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from . import mufredat
from .db import DB
from .search import IndeksOnbellegi
from .turkce import katla
from .vault import (ACIK_KONULAR, KONULAR, KURALLAR, OTURUMLAR, PERFORMANS, PLAN, PROFIL, SON_OTURUM,
                    Vault, VaultHatasi, dosya_adi, frontmatter_ayir, frontmatter_yaz, grafik_kur, not_coz)

SAAT_DILIMI = ZoneInfo("Europe/Istanbul")
SON_OTURUM_KART = 8  # Son Oturum dosyasında tutulan kart sayısı; eskiler günlük dosyada durur.
PROFIL_ALANLARI = ("ad", "sinav_tarihi", "hedef", "gunluk_saat", "guclu_dersler", "zayif_dersler")


def simdi() -> datetime:
    return datetime.now(SAAT_DILIMI)


def konu_anahtari(ders: str, konu: str) -> str:
    return f"{katla(ders).strip()}::{katla(konu).strip()}"


def _tarih(value) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return None


def _bolum(text: str, baslik: str) -> tuple[int, int] | None:
    """`## baslik` bölümünün (başlangıç, bitiş) karakter aralığı."""
    match = re.search(rf"^## {re.escape(baslik)}[ \t]*\n", text, re.M)
    if not match:
        return None
    nxt = re.search(r"^## ", text[match.end():], re.M)
    return match.end(), match.end() + nxt.start() if nxt else len(text)


def _kirp(text: str, limit: int) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[:limit].rsplit("\n", 1)[0] + "\n…(kırpıldı, tamamı için not_oku)"


def _serpistir(agirliklar: dict[str, int]) -> list[str]:
    """Ağırlıklı, aynı dersi arka arkaya koymayan sıra (smooth weighted round-robin)."""
    toplam = sum(agirliklar.values())
    akim = {d: 0 for d in agirliklar}
    out = []
    for _ in range(toplam):
        for d, w in agirliklar.items():
            akim[d] += w
        secilen = max(akim, key=lambda d: akim[d])
        akim[secilen] -= toplam
        out.append(secilen)
    return out


class Koc:
    def __init__(self, vault: Vault, db: DB, onbellek: IndeksOnbellegi):
        self.v = vault
        self.db = db
        self.onbellek = onbellek
        self.v.hazirla()

    # --- başlangıç -----------------------------------------------------
    def kaldigim_yer(self) -> dict:
        now = simdi()
        meta, govde = frontmatter_ayir(self.v.oku_veya_bos(PROFIL))
        sinav = _tarih(meta.get("sinav_tarihi"))
        son = self.v.oku_veya_bos(SON_OTURUM)
        kartlar = re.split(r"^(?=## )", son, flags=re.M)[1:]
        acik = self.v.oku_veya_bos(ACIK_KONULAR)
        rng = _bolum(acik, "Açık")
        plan = self.v.oku_veya_bos(PLAN)
        bugun_plan = ""
        match = re.search(rf"^## {now.date().isoformat()}.*?(?=^## |\Z)", plan, re.M | re.S)
        if match:
            bugun_plan = match.group(0).strip()
        istat = self.konu_istatistikleri()
        return {
            "simdi": now.strftime("%Y-%m-%d %H:%M"),
            "gun": ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"][now.weekday()],
            "profil": {k: meta.get(k) for k in PROFIL_ALANLARI},
            "profil_notlari": _kirp(govde, 1500),
            "profil_eksik": [k for k in ("ad", "sinav_tarihi", "gunluk_saat") if not meta.get(k)],
            "sinava_kalan_gun": (sinav - now.date()).days if sinav else None,
            "son_oturumlar": [_kirp(k, 900) for k in kartlar[:2]],
            "acik_konular": _kirp(acik[rng[0]:rng[1]], 1500) if rng else "",
            "kurallar": _kirp(self.v.oku_veya_bos(KURALLAR), 1500),
            "bugunun_plani": bugun_plan,
            "zayif_konular": self._zayif(istat, 5),
            "tekrari_gelenler": [k for k in istat if k["tekrar_zamani"]][:8],
            "not_sayisi": len(self.v.tum_dosyalar()),
        }

    # --- notlar --------------------------------------------------------
    def ara(self, sorgu: str, limit: int = 8, koc_dahil: bool = False) -> list[dict]:
        return self.onbellek.al(self.v).ara(sorgu, max(1, min(limit, 25)), koc_dahil)

    def not_oku(self, ad: str) -> dict:
        yol = self.v.bul(ad)
        if yol is None:
            raise VaultHatasi(f"'{ad}' adlı not yok. notlarda_ara ile benzerini arayın.")
        item = not_coz(yol, self.v.oku(yol))
        return {"yol": yol, "baslik": item.baslik, "meta": item.meta, "icerik": item.govde,
                "baglantilar": item.baglantilar, "etiketler": item.etiketler}

    def not_yaz(self, baslik: str, icerik: str, ders: str | None = None, klasor: str | None = None,
                etiketler: list[str] | None = None, mod: str = "olustur") -> dict:
        if mod not in ("olustur", "uzerine_yaz", "sona_ekle"):
            raise VaultHatasi("mod: olustur, uzerine_yaz ya da sona_ekle olmalı.")
        mevcut = self.v.bul(baslik) if mod != "olustur" else None
        if mevcut is None:
            ders = mufredat.ders_normalle(ders) if ders else None
            if klasor:
                hedef = f"{klasor.strip('/')}/{dosya_adi(baslik)}.md"
            elif ders:
                hedef = f"{KONULAR}/{dosya_adi(ders)}/{dosya_adi(baslik)}.md"
            else:
                hedef = f"{KONULAR}/{dosya_adi(baslik)}.md"
            if self.v.var_mi(hedef) or (mod == "olustur" and self.v.bul(baslik)):
                if mod == "olustur":
                    raise VaultHatasi(f"'{baslik}' notu zaten var. Eklemek için mod='sona_ekle',"
                                      " değiştirmek için mod='uzerine_yaz' kullanın.")
            yol = hedef
        else:
            yol = mevcut
        bugun = simdi().strftime("%Y-%m-%d")
        if mod == "sona_ekle" and self.v.var_mi(yol):
            meta, govde = frontmatter_ayir(self.v.oku(yol))
            govde = govde.rstrip() + "\n\n" + icerik.strip() + "\n"
        else:
            meta = frontmatter_ayir(self.v.oku(yol))[0] if self.v.var_mi(yol) else {}
            meta.setdefault("created", bugun)
            govde = icerik.strip() + "\n"
            if not re.match(r"^# ", govde):
                govde = f"# {baslik.strip()}\n\n{govde}"
        meta["modified"] = bugun
        if ders:
            meta["ders"] = mufredat.ders_normalle(ders)
        if etiketler:
            mevcut_etiket = [str(t) for t in (meta.get("tags") or [])]
            meta["tags"] = list(dict.fromkeys(mevcut_etiket + [t.lstrip("#").replace(" ", "-") for t in etiketler]))
        yol = self.v.yaz(yol, frontmatter_yaz(meta, govde))
        return {"yol": yol, "durum": "kaydedildi"}

    def notlari_listele(self, klasor: str | None = None, limit: int = 100) -> list[dict]:
        out = []
        prefix = (klasor or "").strip("/")
        for rel, _, mtime in self.v.tum_dosyalar():
            if prefix and not rel.startswith(prefix + "/"):
                continue
            out.append({"yol": rel, "degisti": datetime.fromtimestamp(mtime, SAAT_DILIMI).strftime("%Y-%m-%d")})
        out.sort(key=lambda r: r["degisti"], reverse=True)
        return out[:limit]

    def konu_iliskileri(self, konu: str) -> dict:
        notlar = self.v.notlar()
        grafik = grafik_kur(notlar)
        yol = self.v.bul(konu)
        by_yol = {n.yol: n for n in notlar}
        if yol is None:
            # Notu yok ama başka notlar bu ada bağlanıyor olabilir.
            key = katla(konu).strip()
            bahseden = [y for y, hedefler in grafik.cozulemeyen.items() if any(katla(h) == key for h in hedefler)]
            return {"konu": konu, "notu_var": False, "bu_konuya_baglananlar": bahseden,
                    "oneri": "Bu konunun notu yok; not_yaz ile açılabilir." if bahseden else "Bu adla not ya da bağlantı yok."}
        item = by_yol[yol]
        ikinci = defaultdict(int)
        for komsu in grafik.giden.get(yol, []) + grafik.gelen.get(yol, []):
            for uzak in grafik.giden.get(komsu, []) + grafik.gelen.get(komsu, []):
                if uzak != yol:
                    ikinci[uzak] += 1
        dogrudan = set(grafik.giden.get(yol, [])) | set(grafik.gelen.get(yol, []))
        ortak_etiket = []
        if item.etiketler:
            for other in notlar:
                if other.yol != yol and set(other.etiketler) & set(item.etiketler):
                    ortak_etiket.append({"yol": other.yol, "ortak": sorted(set(other.etiketler) & set(item.etiketler))})
        return {
            "konu": item.baslik,
            "yol": yol,
            "notu_var": True,
            "ders": item.meta.get("ders"),
            "baglandigi": grafik.giden.get(yol, []),
            "ona_baglananlar": grafik.gelen.get(yol, []),
            "notu_olmayan_baglantilar": grafik.cozulemeyen.get(yol, []),
            "iki_adim_uzak": [y for y, _ in sorted(ikinci.items(), key=lambda x: -x[1]) if y not in dogrudan][:10],
            "ortak_etiketli": ortak_etiket[:10],
        }

    # --- soru sonuçları ve istatistik ------------------------------------
    def soru_sonucu_kaydet(self, ders: str, konu: str, dogru: int, yanlis: int, bos: int = 0,
                           kaynak: str | None = None, aciklama: str | None = None, tarih: str | None = None) -> dict:
        if min(dogru, yanlis, bos) < 0 or dogru + yanlis + bos == 0 or dogru + yanlis + bos > 1000:
            raise VaultHatasi("Soru sayıları 0 ile 1000 arasında olmalı ve toplam en az 1 olmalı.")
        ders = mufredat.ders_normalle(ders)
        gun = _tarih(tarih) or simdi().date()
        self.db.sonuc_ekle(self.v.user_id, tarih=gun.isoformat(), ders=ders, konu=konu.strip(),
                           konu_key=konu_anahtari(ders, konu), dogru=dogru, yanlis=yanlis, bos=bos,
                           kaynak=kaynak, aciklama=aciklama)
        istat = self.konu_istatistikleri()
        self._performans_yaz(istat)
        bu = next((k for k in istat if k["anahtar"] == konu_anahtari(ders, konu)), None)
        return {"kaydedildi": True, "konu_durumu": bu}

    def konu_istatistikleri(self) -> list[dict]:
        bugun = simdi().date()
        gruplar: dict[str, list] = defaultdict(list)
        for row in self.db.sonuclar(self.v.user_id):
            gruplar[row["konu_key"]].append(row)
        out = []
        for key, rows in gruplar.items():
            dogru = sum(r["dogru"] for r in rows)
            yanlis = sum(r["yanlis"] for r in rows)
            bos = sum(r["bos"] for r in rows)
            toplam = dogru + yanlis + bos
            # Az soruda yanıltmasın diye düzleştirilmiş başarı (Laplace).
            basari = (dogru + 1) / (toplam + 2)
            son = rows[-3:]
            son_toplam = sum(r["dogru"] + r["yanlis"] + r["bos"] for r in son)
            son_basari = sum(r["dogru"] for r in son) / son_toplam if son_toplam else basari
            son_tarih = max(_tarih(r["tarih"]) for r in rows)
            aralik = 1 if basari < 0.5 else 2 if basari < 0.65 else 4 if basari < 0.75 else 7 if basari < 0.85 else 14
            gecen = (bugun - son_tarih).days
            ders = rows[-1]["ders"]
            agirlik = mufredat.agirlik(ders)
            skor = (1 - basari) * (1 + agirlik / 4) + (0.25 if gecen >= aralik else 0) \
                + max(0.0, basari - son_basari) * 0.5
            out.append({
                "anahtar": key, "ders": ders, "konu": rows[-1]["konu"],
                "toplam_soru": toplam, "dogru": dogru, "yanlis": yanlis, "bos": bos,
                "basari_yuzde": round(100 * dogru / toplam) if toplam else 0,
                "son_basari_yuzde": round(100 * son_basari),
                "son_calisma": son_tarih.isoformat(), "gecen_gun": gecen,
                "tekrar_araligi_gun": aralik, "tekrar_zamani": gecen >= aralik,
                "zayiflik": round(skor, 3),
            })
        out.sort(key=lambda k: -k["zayiflik"])
        return out

    @staticmethod
    def _zayif(istat: list[dict], limit: int, ders: str | None = None) -> list[dict]:
        rows = [k for k in istat if not ders or k["ders"] == ders]
        return [{k: r[k] for k in ("ders", "konu", "basari_yuzde", "toplam_soru", "gecen_gun", "tekrar_zamani")}
                for r in rows[:limit]]

    def zayif_konular(self, limit: int = 10, ders: str | None = None) -> dict:
        istat = self.konu_istatistikleri()
        ders = mufredat.ders_normalle(ders) if ders else None
        ders_ozet = defaultdict(lambda: [0, 0])
        for k in istat:
            ders_ozet[k["ders"]][0] += k["dogru"]
            ders_ozet[k["ders"]][1] += k["toplam_soru"]
        calisilan = {k["ders"] for k in istat}
        return {
            "zayif_konular": self._zayif(istat, max(1, min(limit, 50)), ders),
            "ders_basarilari": {d: round(100 * v[0] / v[1]) for d, v in ders_ozet.items() if v[1]},
            "hic_soru_cozulmemis_dersler": [d for d in mufredat.DERSLER if d not in calisilan],
        }

    def _performans_yaz(self, istat: list[dict]) -> None:
        satirlar = ["# Performans", "", f"Güncellendi: {simdi().strftime('%Y-%m-%d %H:%M')}", "",
                    "| Ders | Konu | Soru | Başarı | Son çalışma | Tekrar |", "| --- | --- | --- | --- | --- | --- |"]
        for k in sorted(istat, key=lambda r: (r["ders"], r["konu"])):
            satirlar.append(f"| {k['ders']} | [[{k['konu']}]] | {k['toplam_soru']} | %{k['basari_yuzde']} | "
                            f"{k['son_calisma']} | {'zamanı geldi' if k['tekrar_zamani'] else str(k['tekrar_araligi_gun']) + ' gün'} |")
        satirlar += ["", "## En zayıf 10 konu", ""]
        satirlar += [f"{i}. {k['ders']} · [[{k['konu']}]] · %{k['basari_yuzde']}"
                     for i, k in enumerate(istat[:10], 1)]
        self.v.yaz(PERFORMANS, "\n".join(satirlar) + "\n")

    # --- oturum hafızası -------------------------------------------------
    def oturumu_kaydet(self, ozet: str, calisilan_konular: list[str] | None = None,
                       sonraki_adim: str | None = None, etiket: str | None = None,
                       sure_dakika: int | None = None, ruh_hali: str | None = None) -> dict:
        now = simdi()
        konular = [k.strip() for k in (calisilan_konular or []) if k.strip()]
        baslik = f"## {now.strftime('%Y-%m-%d %H:%M')} · {(etiket or 'çalışma').strip()}"
        satirlar = [baslik, "", ozet.strip(), ""]
        if konular:
            satirlar.append("- Konular: " + ", ".join(f"[[{k}]]" for k in konular))
        if sure_dakika:
            satirlar.append(f"- Süre: {sure_dakika} dk")
        if ruh_hali:
            satirlar.append(f"- Durum: {ruh_hali.strip()}")
        if sonraki_adim:
            satirlar.append(f"- Sıradaki adım: {sonraki_adim.strip()}")
        kart = "\n".join(satirlar).rstrip() + "\n"

        son = self.v.oku_veya_bos(SON_OTURUM) or "# Son oturumlar\n"
        parcalar = re.split(r"^(?=## )", son, flags=re.M)
        bas, kartlar = parcalar[0], parcalar[1:]
        kartlar = [kart + "\n"] + kartlar
        self.v.yaz(SON_OTURUM, bas.rstrip() + "\n\n" + "".join(k.rstrip() + "\n\n" for k in kartlar[:SON_OTURUM_KART]))

        gunluk = f"{OTURUMLAR}/{now.strftime('%Y-%m-%d')}.md"
        mevcut = self.v.oku_veya_bos(gunluk) or frontmatter_yaz(
            {"type": "oturum", "date": now.strftime("%Y-%m-%d")}, f"# {now.strftime('%Y-%m-%d')} oturumları\n")
        self.v.yaz(gunluk, mevcut.rstrip() + "\n\n" + kart.replace("## ", "### ", 1))
        return {"kaydedildi": True, "son_oturum": SON_OTURUM, "gunluk": gunluk}

    def acik_konu_guncelle(self, baslik: str, durum: str = "acik", aciklama: str | None = None) -> dict:
        if durum not in ("acik", "kapandi"):
            raise VaultHatasi("durum: acik ya da kapandi olmalı.")
        text = self.v.oku_veya_bos(ACIK_KONULAR) or "# Açık konular\n\n## Açık\n\n## Kapananlar\n"
        for bolum in ("Açık", "Kapananlar"):
            if _bolum(text, bolum) is None:
                text = text.rstrip() + f"\n\n## {bolum}\n"
        key = katla(baslik).strip()
        satirlar = text.split("\n")
        satirlar = [s for s in satirlar
                    if not (re.match(r"^- \[[ x]\] ", s) and katla(s[6:].split(" — ")[0]).strip() == key)]
        text = "\n".join(satirlar)
        tarih = simdi().strftime("%Y-%m-%d")
        isaret = "x" if durum == "kapandi" else " "
        satir = f"- [{isaret}] {baslik.strip()}" + (f" — {aciklama.strip()}" if aciklama else "") + f" ({tarih})"
        hedef = "Kapananlar" if durum == "kapandi" else "Açık"
        start, end = _bolum(text, hedef)
        govde = text[start:end].rstrip("\n")
        yeni = (govde + "\n" if govde.strip() else "\n") + satir + "\n\n"
        text = text[:start] + yeni + text[end:].lstrip("\n")
        self.v.yaz(ACIK_KONULAR, text.rstrip() + "\n")
        return {"kaydedildi": True, "durum": durum}

    def kural_ekle(self, kural: str) -> dict:
        text = self.v.oku_veya_bos(KURALLAR) or "# Koç kuralları\n\n"
        satir = f"- {kural.strip()} ({simdi().strftime('%Y-%m-%d')})"
        if katla(kural.strip()) in katla(text):
            return {"kaydedildi": False, "neden": "Bu kural zaten var."}
        self.v.yaz(KURALLAR, text.rstrip() + "\n" + satir + "\n")
        return {"kaydedildi": True}

    def profili_guncelle(self, alanlar: dict, notlar: str | None = None) -> dict:
        meta, govde = frontmatter_ayir(self.v.oku_veya_bos(PROFIL))
        for key, value in alanlar.items():
            if key not in PROFIL_ALANLARI or value is None:
                continue
            if key == "sinav_tarihi":
                gun = _tarih(value)
                if gun is None:
                    raise VaultHatasi("sinav_tarihi YYYY-AA-GG biçiminde olmalı.")
                value = gun.isoformat()
            if key in ("guclu_dersler", "zayif_dersler"):
                value = [mufredat.ders_normalle(v) for v in value]
            meta[key] = value
        meta["modified"] = simdi().strftime("%Y-%m-%d")
        if notlar:
            rng = _bolum(govde, "Notlar")
            ek = f"- {notlar.strip()} ({meta['modified']})\n"
            if rng:
                govde = govde[:rng[1]].rstrip("\n") + "\n" + ek + "\n" + govde[rng[1]:].lstrip("\n")
            else:
                govde = govde.rstrip() + "\n\n## Notlar\n" + ek
        self.v.yaz(PROFIL, frontmatter_yaz(meta, govde))
        return {"kaydedildi": True, "profil": {k: meta.get(k) for k in PROFIL_ALANLARI}}

    # --- çalışma planı ---------------------------------------------------
    def calisma_plani(self, gun_sayisi: int = 7, gunluk_saat: float | None = None,
                      baslangic: str | None = None, kaydet: bool = True) -> dict:
        gun_sayisi = max(1, min(gun_sayisi, 28))
        meta, _ = frontmatter_ayir(self.v.oku_veya_bos(PROFIL))
        saat = float(gunluk_saat or meta.get("gunluk_saat") or 6)
        saat = max(1.0, min(saat, 14.0))
        bas = _tarih(baslangic) or simdi().date()
        sinav = _tarih(meta.get("sinav_tarihi"))
        kalan = (sinav - bas).days if sinav else None
        if kalan is None or kalan > 90:
            evre, oranlar = "konu çalışma", (0.6, 0.15, 0.25)
        elif kalan > 30:
            evre, oranlar = "konu + soru", (0.45, 0.2, 0.35)
        else:
            evre, oranlar = "tekrar + deneme", (0.2, 0.4, 0.4)

        istat = self.konu_istatistikleri()
        calisilan = {k["anahtar"] for k in istat}
        # Yeni konu sırası: ağırlığı yüksek derslerden, henüz soru çözülmemiş konular, dersler sırayla.
        kuyruklar = {d: [k for k in bilgi["konular"] if konu_anahtari(d, k) not in calisilan]
                     for d, bilgi in mufredat.DERSLER.items()}
        zayif_tercih = set(mufredat.ders_normalle(d) for d in (meta.get("zayif_dersler") or []))
        dongu = _serpistir({d: mufredat.agirlik(d) + (2 if d in zayif_tercih else 0) for d in mufredat.DERSLER})
        zayiflar = [k for k in istat if k["basari_yuzde"] < 75 or k["tekrar_zamani"]]

        gunler = []
        di = zi = 0
        for i in range(gun_sayisi):
            gun = bas + timedelta(days=i)
            deneme_gunu = evre != "konu çalışma" and gun.weekday() == 6
            bloklar = []
            if deneme_gunu:
                bloklar.append({"tur": "deneme", "sure_saat": min(saat, 4.0),
                                "is": "Tam deneme (Temel + Klinik), ardından yanlış analizi"})
                bloklar.append({"tur": "analiz", "sure_saat": max(0.5, saat - 4.0),
                                "is": "Denemedeki yanlışları soru_sonucu_kaydet ile konu konu işle"})
            else:
                yeni_s, tekrar_s, soru_s = (round(saat * o * 2) / 2 for o in oranlar)
                if yeni_s:
                    for _ in range(len(dongu)):
                        ders = dongu[di % len(dongu)]
                        di += 1
                        if kuyruklar[ders]:
                            konu = kuyruklar[ders].pop(0)
                            bloklar.append({"tur": "konu", "ders": ders, "konu": konu, "sure_saat": yeni_s,
                                            "is": f"{ders} · {konu}: konu çalış, kısa not al"})
                            break
                if tekrar_s and zayiflar:
                    k = zayiflar[zi % len(zayiflar)]
                    zi += 1
                    bloklar.append({"tur": "tekrar", "ders": k["ders"], "konu": k["konu"], "sure_saat": tekrar_s,
                                    "is": f"{k['ders']} · {k['konu']} tekrarı (%{k['basari_yuzde']} başarı)"})
                elif tekrar_s:
                    soru_s += tekrar_s
                if soru_s:
                    hedef = bloklar[0] if bloklar else None
                    konu_adi = f"{hedef['ders']} · {hedef['konu']}" if hedef and hedef.get("konu") else "karışık"
                    bloklar.append({"tur": "soru", "sure_saat": soru_s,
                                    "is": f"Soru çözümü ({konu_adi}), sonuçları kaydet"})
            gunler.append({"tarih": gun.isoformat(), "gun": ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"][gun.weekday()],
                           "bloklar": bloklar})

        md = [f"# Çalışma planı", "", f"- Oluşturuldu: {simdi().strftime('%Y-%m-%d %H:%M')}",
              f"- Evre: {evre}", f"- Günlük hedef: {saat:g} saat"]
        if kalan is not None:
            md.append(f"- Sınava kalan: {kalan} gün")
        md.append("")
        for g in gunler:
            md += [f"## {g['tarih']} {g['gun']}", ""]
            for b in g["bloklar"]:
                metin = b["is"]
                if b.get("konu"):
                    metin = metin.replace(b["konu"], f"[[{b['konu']}]]", 1)
                md.append(f"- [ ] {b['sure_saat']:g} sa · {metin}")
            md.append("")
        markdown = "\n".join(md)
        if kaydet:
            self.v.yaz(PLAN, markdown)
        return {"evre": evre, "sinava_kalan_gun": kalan, "gunluk_saat": saat, "gunler": gunler,
                "kaydedildi": PLAN if kaydet else None, "markdown": markdown}
