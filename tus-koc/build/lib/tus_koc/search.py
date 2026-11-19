"""Notlarda Türkçe kök + BM25 pasaj araması.

Fikir avenoxbeyin'deki aramadan gelir: sorgu ve not aynı kök bulucudan geçer,
böylece "yetmezliğinde" ile "yetmezlik" eşleşir. Notlar başlıklara ve yaklaşık
paragraf boyunda pasajlara bölünür; sonuç olarak pasaj döner, böylece koç uzun
bir notun tamamını değil ilgili kısmını okur.
"""
from __future__ import annotations

import math
import re
import threading
from collections import Counter
from dataclasses import dataclass

from .turkce import kokler
from .vault import KOC_DOSYALARI, Not, Vault

# Arama için anlamsız sık kelimeler (kök hali, aksansız).
DURAK = frozenset(
    "ve ile bir bu su o da de mi mu ne icin gibi daha cok en ama ya veya hem ki ise olan olarak "
    "var yok her hep sonra once kadar gore icinde uzerine nasil neden hangi kim nerede olur olm "
    "the and of to in is".split()
)

K1 = 1.4
B = 0.72
PASAJ_KARAKTER = 900


@dataclass
class Pasaj:
    yol: str
    baslik: str
    bolum: str
    metin: str
    terimler: Counter
    uzunluk: int


def _pasajlara_bol(item: Not) -> list[Pasaj]:
    out: list[Pasaj] = []
    bolum = ""
    tampon: list[str] = []

    def bosalt():
        metin = "\n".join(tampon).strip()
        tampon.clear()
        if not metin:
            return
        terms = Counter(t for t in kokler(f"{item.baslik} {bolum} {metin}") if t not in DURAK)
        # Başlık ve bölüm adı bir kez daha sayılır: "Digoksin" notundaki her pasaj o konudadır.
        terms.update(t for t in kokler(f"{item.baslik} {bolum}") if t not in DURAK)
        out.append(Pasaj(item.yol, item.baslik, bolum, metin, terms, sum(terms.values())))

    for line in item.govde.splitlines():
        heading = re.match(r"^(#{1,6})\s+(.*)", line)
        if heading:
            bosalt()
            bolum = heading.group(2).strip()
            continue
        tampon.append(line)
        if sum(len(x) for x in tampon) >= PASAJ_KARAKTER and not line.strip():
            bosalt()
    bosalt()
    if not out:  # yalnız başlıktan oluşan not da bulunabilsin
        terms = Counter(t for t in kokler(item.baslik) if t not in DURAK)
        out.append(Pasaj(item.yol, item.baslik, "", "", terms, max(1, sum(terms.values()))))
    return out


class Indeks:
    def __init__(self, notlar: list[Not]):
        self.pasajlar: list[Pasaj] = []
        for item in notlar:
            self.pasajlar.extend(_pasajlara_bol(item))
        self.df: Counter = Counter()
        for pasaj in self.pasajlar:
            self.df.update(pasaj.terimler.keys())
        self.ort = (sum(p.uzunluk for p in self.pasajlar) / len(self.pasajlar)) if self.pasajlar else 1.0

    def ara(self, sorgu: str, limit: int = 8, koc_dahil: bool = False) -> list[dict]:
        terms = [t for t in dict.fromkeys(kokler(sorgu)) if t not in DURAK]
        if not terms or not self.pasajlar:
            return []
        n = len(self.pasajlar)
        skorlar = []
        for pasaj in self.pasajlar:
            if not koc_dahil and pasaj.yol in KOC_DOSYALARI:
                continue
            skor = 0.0
            eslesen = 0
            for term in terms:
                tf = pasaj.terimler.get(term, 0)
                if not tf:
                    continue
                eslesen += 1
                idf = math.log(1 + (n - self.df[term] + 0.5) / (self.df[term] + 0.5))
                skor += idf * tf * (K1 + 1) / (tf + K1 * (1 - B + B * pasaj.uzunluk / self.ort))
            if eslesen:
                # Sorgudaki kelimelerin çoğunu karşılayan pasaj öne çıksın.
                skor *= 0.5 + 0.5 * eslesen / len(terms)
                skorlar.append((skor, pasaj))
        skorlar.sort(key=lambda x: -x[0])
        sonuc = []
        gorulen: Counter = Counter()
        for skor, pasaj in skorlar:
            if gorulen[pasaj.yol] >= 2:  # bir not sonuçları doldurmasın
                continue
            gorulen[pasaj.yol] += 1
            sonuc.append({
                "yol": pasaj.yol,
                "baslik": pasaj.baslik,
                "bolum": pasaj.bolum,
                "pasaj": pasaj.metin[:1200],
                "skor": round(skor, 3),
            })
            if len(sonuc) >= limit:
                break
        return sonuc


class IndeksOnbellegi:
    """Kullanıcı başına indeks; klasör değişince (MCP ya da WebDAV yazımı) yeniden kurulur."""

    def __init__(self, maks: int = 64):
        self._lock = threading.Lock()
        self._cache: dict[str, tuple[tuple, Indeks]] = {}
        self._maks = maks

    def al(self, vault: Vault) -> Indeks:
        imza = vault.imza()
        with self._lock:
            cached = self._cache.get(vault.user_id)
            if cached and cached[0] == imza:
                return cached[1]
        indeks = Indeks(vault.notlar())
        with self._lock:
            if len(self._cache) >= self._maks:
                self._cache.pop(next(iter(self._cache)))
            self._cache[vault.user_id] = (imza, indeks)
        return indeks
