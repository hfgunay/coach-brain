"""Kullanıcı başına avenoxbeyin kasası ve onun CLI'ına ince köprü.

Bu modül hafıza mantığı İÇERMEZ. Her kullanıcı için resmi `scripts/install_v3.py` ile
gerçek bir avenoxbeyin V3 kasası kurar ve kasanın kendi `beyin.py` komutlarını ve
SessionStart hook'unu çalıştırır. Arama, not/görev yazımı, revision kontrolü, tekrar
tarihleri (`review_at`), görev bitiş tarihleri (`due_at`), Companion dosyaları ve
oturum sonuçları (receipt) tamamen repodaki motordan gelir.

Sunucuya ait olan tek şey: kasayı kurmak, kullanıcıyı kendi kasasına kilitlemek ve
koç talimatını (skill) kasaya koymak.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import uuid
from pathlib import Path
from typing import Any

from mcp.server.mcpserver.exceptions import ToolError

# Repo kökü: tus-koc/tus_koc/kasa.py -> ../../ ; Docker'da TUS_KOC_BEYIN_KAYNAK ile verilir.
BEYIN_KAYNAK = Path(os.environ.get("TUS_KOC_BEYIN_KAYNAK") or Path(__file__).resolve().parents[2])
KOC_SKILL = Path(__file__).resolve().parent / "skill" / "SKILL.md"
KOC_SKILL_HEDEF = ".agents/skills/tus-koc/SKILL.md"
# Sunucuda yalnız Claude/Codex hook'ları ve çekirdek skill'ler gerekir; masaüstü başlatıcıları
# ve diğer istemci adaptörleri kasaya (dolayısıyla iPad'e eşitlenen klasöre) konmaz.
HARIC_BILESENLER = ("adapters", "launchers")
HARNESS = "claude"

_kilitler: dict[str, threading.Lock] = {}
_kilitler_kilidi = threading.Lock()


class KasaHatasi(ToolError):
    """Koça hata sonucu olarak dönen kasa hatası (sunucu hatası değil)."""


def _kilit(user_id: str) -> threading.Lock:
    with _kilitler_kilidi:
        return _kilitler.setdefault(user_id, threading.Lock())


class Kasa:
    def __init__(self, vault_root: Path, state_root: Path, user_id: str):
        if not re.fullmatch(r"[0-9a-f]{32}", user_id):
            raise KasaHatasi("Geçersiz kullanıcı.")
        self.user_id = user_id
        self.vault = (vault_root / user_id).resolve()
        self.state = (state_root / user_id).resolve()
        self.tmp = self.state / "tus-koc-tmp"

    # --- kurulum -------------------------------------------------------
    def kurulu_mu(self) -> bool:
        return (self.vault / ".beyin-version").is_file() and (self.vault / "beyin.py").is_file()

    def hazirla(self) -> None:
        """İlk kullanımda resmi installer ile kasayı kurar; koç skill'ini günceller."""
        with _kilit(self.user_id):
            if not self.kurulu_mu():
                self.vault.mkdir(parents=True, exist_ok=True)
                self.state.mkdir(parents=True, exist_ok=True)
                cmd = [sys.executable, str(BEYIN_KAYNAK / "scripts" / "install_v3.py"),
                       "--vault", str(self.vault), "--state", str(self.state)]
                for bilesen in HARIC_BILESENLER:
                    cmd += ["--exclude-component", bilesen]
                sonuc = subprocess.run(cmd, capture_output=True, text=True, timeout=180,
                                       env=self._env(), cwd=str(self.vault))
                if sonuc.returncode != 0 or not self.kurulu_mu():
                    raise KasaHatasi("Kasa kurulamadı: " + (sonuc.stdout + sonuc.stderr)[-800:])
            self._skill_koy()
            self.tmp.mkdir(parents=True, exist_ok=True)

    def _skill_koy(self) -> None:
        hedef = self.vault / KOC_SKILL_HEDEF
        icerik = KOC_SKILL.read_bytes()
        if not hedef.is_file() or hedef.read_bytes() != icerik:
            hedef.parent.mkdir(parents=True, exist_ok=True)
            hedef.write_bytes(icerik)

    def _env(self) -> dict[str, str]:
        env = {k: v for k, v in os.environ.items() if k in ("PATH", "LANG", "LC_ALL", "TZ", "SYSTEMROOT")}
        env["HOME"] = str(self.state)  # kurulum ve runtime başka kullanıcının dizinine dokunmasın
        env["PYTHONIOENCODING"] = "utf-8"
        env.setdefault("TZ", os.environ.get("TZ", "Europe/Istanbul"))
        return env

    # --- CLI -----------------------------------------------------------
    def cli(self, *args: str, girdi: dict | None = None, timeout: int = 60) -> dict[str, Any]:
        """`beyin.py --json <args>` çalıştırır. `girdi` verilirse geçici JSON dosyası `--file` olur.

        Çakışma (revision, sha) ve doğrulama hataları istisna değil sonuç olarak döner; koç
        repodaki kurala göre yeniden okuyup tekrar dener.
        """
        self.hazirla()
        cmd = [sys.executable, str(self.vault / "beyin.py"), "--vault", str(self.vault), "--state", str(self.state),
               "--json", *args]
        dosya = None
        if girdi is not None:
            dosya = self.tmp / f"{uuid.uuid4().hex}.json"
            dosya.write_text(json.dumps(girdi, ensure_ascii=False), encoding="utf-8")
            cmd += ["--file", str(dosya)]
        try:
            sonuc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=self._env(),
                                   cwd=str(self.vault))
        except subprocess.TimeoutExpired:
            raise KasaHatasi("Kasa komutu zaman aşımına uğradı.") from None
        finally:
            if dosya is not None:
                dosya.unlink(missing_ok=True)
        cikti = sonuc.stdout.strip()
        try:
            veri = json.loads(cikti) if cikti else {}
        except json.JSONDecodeError:
            veri = {"cikti": cikti[-4000:]}
        if not isinstance(veri, dict):
            veri = {"sonuc": veri}
        veri["cikis_kodu"] = sonuc.returncode
        if sonuc.returncode not in (0, 2) and "error" not in veri:
            hata = (sonuc.stderr.strip() or cikti)[-1500:] or "bilinmeyen hata"
            try:  # motor hatayı {"error": "RevisionConflict", "message": ...} olarak stderr'e yazar
                ayrintili = json.loads(hata)
            except json.JSONDecodeError:
                ayrintili = None
            if isinstance(ayrintili, dict) and "error" in ayrintili:
                veri.update(ayrintili)
            else:
                veri["error"] = hata
        return self._yollari_gizle(veri)

    def _yollari_gizle(self, veri: Any) -> Any:
        """Sunucunun mutlak yollarını (diğer kullanıcıların klasörlerinin yeri) dışarı sızdırma."""
        metin = json.dumps(veri, ensure_ascii=False)
        for yol, yerine in ((str(self.vault), "<kasa>"), (str(self.state), "<state>")):
            metin = metin.replace(json.dumps(yol)[1:-1], yerine)
        return json.loads(metin)

    # --- oturum başı -----------------------------------------------------
    def baslangic(self, oturum: str) -> str:
        """Repodaki SessionStart hook'unun ürettiği bağlamın aynısı (Companion, tarihi gelen
        tekrarlar ve görevler, Receipt session satırı)."""
        self.hazirla()
        hook = self.vault / ".claude" / "scripts" / "beyin_v3_hook.py"
        girdi = json.dumps({"hook_event_name": "SessionStart", "session_id": oturum, "cwd": str(self.vault),
                            "source": "startup"})
        try:
            sonuc = subprocess.run([sys.executable, str(hook), "--vault", str(self.vault), "--state", str(self.state),
                                    "--harness", HARNESS], input=girdi, capture_output=True, text=True, timeout=60,
                                   env=self._env(), cwd=str(self.vault))
        except subprocess.TimeoutExpired:
            raise KasaHatasi("Oturum başı bağlamı zaman aşımına uğradı.") from None
        try:
            veri = json.loads(sonuc.stdout or "{}")
        except json.JSONDecodeError:
            veri = {}
        metin = (veri.get("hookSpecificOutput") or {}).get("additionalContext") or veri.get("additionalContext") or ""
        if not metin:
            raise KasaHatasi("Oturum başı bağlamı alınamadı: " + (sonuc.stderr or sonuc.stdout)[-500:])
        return self._yollari_gizle(metin)

    # --- dosyalar ------------------------------------------------------
    def dosya_yolu(self, rel: str) -> Path:
        rel = str(rel).replace("\\", "/").strip().lstrip("/")
        parts = [p for p in rel.split("/") if p]
        if not parts or any(p in (".", "..") or p.startswith(".") for p in parts):
            raise KasaHatasi("Bu yol kullanılamaz.")
        path = (self.vault / Path(*parts)).resolve()
        if self.vault not in path.parents:
            raise KasaHatasi("Bu yol kullanılamaz.")
        return path

    def okunacak_metin(self, rel: str) -> str:
        path = self.dosya_yolu(rel)
        if not path.is_file():
            raise KasaHatasi(f"Dosya yok: {rel}")
        return path.read_text(encoding="utf-8", errors="replace")


def kaynak_hazir_mi() -> bool:
    return (BEYIN_KAYNAK / "scripts" / "install_v3.py").is_file() and (BEYIN_KAYNAK / "template").is_dir()
