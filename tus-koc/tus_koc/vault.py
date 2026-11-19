"""Kullanıcı başına Obsidian uyumlu Markdown klasörü.

Her kullanıcının notları `<data>/vaults/<user_id>/` altında düz `.md` dosyalarıdır.
Bu klasör WebDAV ile dışarı açılır; iPad'deki Obsidian (Remotely Save eklentisi)
aynı dosyaları eşitler. Sunucu Obsidian çalıştırmaz, yalnız aynı biçimi okur/yazar:
YAML frontmatter, `[[bağlantı]]`, `[[bağlantı|takma ad]]`, `#etiket`.
"""
from __future__ import annotations

import os
import re
import tempfile
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path, PurePosixPath

import yaml

from .turkce import katla

KOC = "Koç"
PROFIL = f"{KOC}/Profil.md"
SON_OTURUM = f"{KOC}/Son Oturum.md"
ACIK_KONULAR = f"{KOC}/Açık Konular.md"
KURALLAR = f"{KOC}/Kurallar.md"
PERFORMANS = f"{KOC}/Performans.md"
PLAN = "Plan/Çalışma Planı.md"
OTURUMLAR = "Oturumlar"
KONULAR = "Konular"
ANA_SAYFA = "Başla.md"

# Koçun kendi dosyaları aramada ayrı tutulur; ders notlarıyla karışmasın.
KOC_DOSYALARI = {PROFIL, SON_OTURUM, ACIK_KONULAR, KURALLAR, PERFORMANS}

MAKS_NOT_BOYUTU = 512 * 1024

_LINK = re.compile(r"(!?)\[\[([^\[\]|#^]+)(?:#[^\[\]|]*)?(?:\^[^\[\]|]*)?(?:\|([^\[\]]*))?\]\]")
_TAG = re.compile(r"(?<![\w/#&])#([^\s#.,;:!?()\[\]{}\"'`]+)")
_CODE = re.compile(r"```.*?```|`[^`\n]*`", re.S)
_FRONTMATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?", re.S)
_YASAK_KARAKTER = re.compile(r'[\\:*?"<>|\x00-\x1f]')


class VaultHatasi(ValueError):
    pass


def nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def anahtar(ad: str) -> str:
    """Bağlantı çözümü için ad: klasörsüz, uzantısız, harf/aksan farkı yok."""
    ad = PurePosixPath(nfc(ad).strip()).name
    if ad.lower().endswith(".md"):
        ad = ad[:-3]
    return katla(ad).strip()


def dosya_adi(baslik: str) -> str:
    """Başlıktan Obsidian'ın kabul ettiği bir dosya adı üretir."""
    ad = _YASAK_KARAKTER.sub(" ", nfc(baslik)).replace("/", "-").replace("#", "").replace("^", "")
    ad = ad.replace("[", "(").replace("]", ")")
    ad = re.sub(r"\s+", " ", ad).strip(" .")
    if not ad:
        raise VaultHatasi("Başlık boş olamaz.")
    return ad[:120]


def frontmatter_ayir(text: str) -> tuple[dict, str]:
    match = _FRONTMATTER.match(text)
    if not match:
        return {}, text
    try:
        data = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        data = {}
    return (data if isinstance(data, dict) else {}), text[match.end():]


def frontmatter_yaz(meta: dict, body: str) -> str:
    if not meta:
        return body
    dump = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False, default_flow_style=None).strip()
    return f"---\n{dump}\n---\n{body.lstrip(chr(10))}"


def _liste(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in re.split(r"[,\s]+", value) if part.strip()]
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    return [str(value)]


@dataclass
class Not:
    yol: str
    baslik: str
    meta: dict
    govde: str
    baglantilar: list[str] = field(default_factory=list)
    etiketler: list[str] = field(default_factory=list)
    mtime: float = 0.0

    @property
    def anahtar(self) -> str:
        return anahtar(self.yol)


def not_coz(yol: str, text: str, mtime: float = 0.0) -> Not:
    meta, govde = frontmatter_ayir(text)
    temiz = _CODE.sub(" ", govde)
    baglantilar = []
    for match in _LINK.finditer(temiz):
        hedef = match.group(2).strip()
        if hedef and hedef not in baglantilar:
            baglantilar.append(hedef)
    for value in _liste(meta.get("ilgili")) + _liste(meta.get("related")):
        hedef = value.strip("[]")
        if hedef and hedef not in baglantilar:
            baglantilar.append(hedef)
    etiketler = []
    for tag in _liste(meta.get("tags")) + _liste(meta.get("etiketler")) + _TAG.findall(temiz):
        tag = tag.lstrip("#")
        if tag and not tag.isdigit() and tag not in etiketler:
            etiketler.append(tag)
    baslik = str(meta.get("title") or meta.get("baslik") or PurePosixPath(yol).stem)
    return Not(yol=yol, baslik=baslik, meta=meta, govde=govde, baglantilar=baglantilar,
               etiketler=etiketler, mtime=mtime)


class Vault:
    def __init__(self, root: Path, user_id: str):
        if not re.fullmatch(r"[0-9a-f]{32}", user_id):
            raise VaultHatasi("Geçersiz kullanıcı.")
        self.user_id = user_id
        self.dir = (root / user_id).resolve()
        self.dir.mkdir(parents=True, exist_ok=True)

    # --- yollar --------------------------------------------------------
    def guvenli_yol(self, rel: str) -> tuple[str, Path]:
        rel = nfc(str(rel)).replace("\\", "/").strip().strip("/")
        if not rel:
            raise VaultHatasi("Not yolu boş.")
        if not rel.lower().endswith(".md"):
            rel += ".md"
        parts = PurePosixPath(rel).parts
        if any(p in ("", ".", "..") or p.startswith(".") for p in parts):
            raise VaultHatasi("Bu yol kullanılamaz.")
        path = (self.dir / Path(*parts)).resolve()
        if self.dir not in path.parents:
            raise VaultHatasi("Bu yol kullanılamaz.")
        return "/".join(parts), path

    # --- okuma/yazma ---------------------------------------------------
    def var_mi(self, rel: str) -> bool:
        return self.guvenli_yol(rel)[1].is_file()

    def oku(self, rel: str) -> str:
        _, path = self.guvenli_yol(rel)
        if not path.is_file():
            raise VaultHatasi(f"Not bulunamadı: {rel}")
        return path.read_text(encoding="utf-8", errors="replace")

    def oku_veya_bos(self, rel: str) -> str:
        try:
            return self.oku(rel)
        except VaultHatasi:
            return ""

    def yaz(self, rel: str, text: str) -> str:
        rel, path = self.guvenli_yol(rel)
        data = text.encode("utf-8")
        if len(data) > MAKS_NOT_BOYUTU:
            raise VaultHatasi("Not çok büyük (512 KB sınırı). Konuyu birkaç nota bölün.")
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".yaz-", suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        return rel

    def tum_dosyalar(self) -> list[tuple[str, Path, float]]:
        out = []
        for current, dirs, files in os.walk(self.dir):
            dirs[:] = sorted(d for d in dirs if not d.startswith("."))
            for name in sorted(files):
                if name.startswith(".") or not name.lower().endswith(".md"):
                    continue
                path = Path(current) / name
                try:
                    stat = path.stat()
                except OSError:
                    continue
                if stat.st_size > MAKS_NOT_BOYUTU:
                    continue
                rel = nfc(path.relative_to(self.dir).as_posix())
                out.append((rel, path, stat.st_mtime))
        return out

    def notlar(self) -> list[Not]:
        out = []
        for rel, path, mtime in self.tum_dosyalar():
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            out.append(not_coz(rel, text, mtime))
        return out

    def imza(self) -> tuple:
        """Klasör değişti mi? Arama indeksinin önbelleği bunu anahtar olarak kullanır."""
        files = self.tum_dosyalar()
        return (len(files), max((m for _, _, m in files), default=0.0), hash(tuple(r for r, _, _ in files)))

    def bul(self, ad: str) -> str | None:
        """Obsidian gibi: önce tam yol, sonra yalnız dosya adı (harf farkı gözetmeden)."""
        try:
            rel, path = self.guvenli_yol(ad)
            if path.is_file():
                return rel
        except VaultHatasi:
            pass
        key = anahtar(ad)
        adaylar = [rel for rel, _, _ in self.tum_dosyalar() if anahtar(rel) == key]
        if not adaylar:
            return None
        return sorted(adaylar, key=lambda r: (r.count("/"), r))[0]

    # --- iskelet -------------------------------------------------------
    def hazirla(self) -> None:
        """İlk kullanımda koç dosyalarını ve ana sayfayı oluşturur; var olana dokunmaz."""
        bugun = datetime.now().strftime("%Y-%m-%d")
        iskelet = {
            PROFIL: frontmatter_yaz(
                {"type": "koc-profil", "ad": "", "sinav_tarihi": "", "hedef": "", "gunluk_saat": 6,
                 "guclu_dersler": [], "zayif_dersler": [], "created": bugun},
                "# Öğrenci profili\n\nKoç bu notu öğrenciyi tanıdıkça günceller.\n\n"
                "## Çalışma alışkanlıkları\n\n## Motivasyon ve dikkat\n\n## Notlar\n"),
            SON_OTURUM: "# Son oturumlar\n\nEn yeni oturum en üstte.\n",
            ACIK_KONULAR: "# Açık konular\n\nYarım kalan, tekrar dönülecek konular.\n\n## Açık\n\n## Kapananlar\n",
            KURALLAR: "# Koç kuralları\n\nÖğrencinin koça verdiği kalıcı talimatlar.\n\n",
            PERFORMANS: "# Performans\n\nHenüz soru sonucu kaydedilmedi.\n",
            ANA_SAYFA: (
                "# TUS Çalışma Kasası\n\n"
                f"- [[Profil]] · [[Son Oturum]] · [[Açık Konular]] · [[Kurallar]]\n"
                "- [[Performans]] · [[Çalışma Planı]]\n\n"
                "Ders notları `Konular/<Ders>/` altında, oturum kayıtları `Oturumlar/` altında.\n"),
        }
        for rel, text in iskelet.items():
            if not self.var_mi(rel):
                self.yaz(rel, text)


@dataclass
class Grafik:
    giden: dict[str, list[str]]  # not yolu -> çözülen hedef yolları
    gelen: dict[str, list[str]]  # not yolu -> ona bağlanan yollar
    cozulemeyen: dict[str, list[str]]  # not yolu -> henüz notu olmayan bağlantılar


def grafik_kur(notlar: list[Not]) -> Grafik:
    by_key: dict[str, str] = {}
    for item in sorted(notlar, key=lambda n: (n.yol.count("/"), n.yol)):
        by_key.setdefault(item.anahtar, item.yol)
        by_key.setdefault(katla(item.yol[:-3]), item.yol)
        alias = item.meta.get("aliases") or item.meta.get("takma_adlar")
        for value in _liste(alias) if isinstance(alias, str) else (alias or []):
            by_key.setdefault(katla(str(value)), item.yol)
    giden: dict[str, list[str]] = {}
    gelen: dict[str, list[str]] = {}
    cozulemeyen: dict[str, list[str]] = {}
    for item in notlar:
        for hedef in item.baglantilar:
            yol = by_key.get(katla(hedef.strip()).removesuffix(".md")) or by_key.get(anahtar(hedef))
            if yol is None:
                cozulemeyen.setdefault(item.yol, []).append(hedef)
            elif yol != item.yol:
                giden.setdefault(item.yol, [])
                if yol not in giden[item.yol]:
                    giden[item.yol].append(yol)
                    gelen.setdefault(yol, []).append(item.yol)
    return Grafik(giden=giden, gelen=gelen, cozulemeyen=cozulemeyen)
