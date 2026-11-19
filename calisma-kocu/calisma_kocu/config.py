"""Ortam değişkenlerinden okunan ayarlar."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _list(value: str | None) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


@dataclass(frozen=True)
class Ayarlar:
    # Sunucunun dışarıdan görünen adresi, örn. https://koc.ornek.com (sonunda / yok).
    public_url: str = "http://localhost:8000"
    # Veritabanı ve kullanıcı klasörlerinin durduğu kalıcı disk.
    data_dir: Path = Path("./data")
    host: str = "0.0.0.0"
    port: int = 8000
    # Boş değilse kayıt olurken bu kodlardan biri istenir (kapalı beta için).
    davet_kodlari: list[str] = field(default_factory=list)
    # true ise davet kodu olmadan herkes kayıt olabilir.
    acik_kayit: bool = False
    access_token_saniye: int = 24 * 3600
    refresh_token_saniye: int = 90 * 24 * 3600
    # Kayıtlı istemcilerin dönüş adresleri yalnız bu alan adlarına (ve alt alan adlarına) gidebilir.
    # Saldırganın kendi adresine yönlenen bir bağlantıyla öğrencinin hesabına erişmesini engeller.
    izinli_yonlendirmeler: list[str] = field(default_factory=lambda: [
        "claude.ai", "claude.com", "anthropic.com", "chatgpt.com", "openai.com", "localhost", "127.0.0.1"])
    # Arkada bir ters vekil (Caddy, Fly) varsa ek Host başlıkları.
    izinli_hostlar: list[str] = field(default_factory=list)
    # Telegram hatırlatma botu (BotFather anahtarı). Boşsa bot kapalıdır.
    telegram_token: str = ""
    telegram_api: str = "https://api.telegram.org"
    # Yeni bağlanan öğrencinin varsayılan hatırlatma saatleri (Europe/Istanbul); bottan değiştirilebilir.
    sabah_saati: str = "08:30"
    aksam_saati: str = "21:30"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "calisma_kocu.sqlite3"

    @property
    def vault_root(self) -> Path:
        return self.data_dir / "vaults"

    @property
    def state_root(self) -> Path:
        """avenoxbeyin runtime state'i (indeks, kilitler); kasanın ve WebDAV'ın dışında."""
        return self.data_dir / "state"

    @classmethod
    def ortamdan(cls) -> "Ayarlar":
        env = os.environ
        return cls(
            public_url=env.get("KOC_PUBLIC_URL", cls.public_url).rstrip("/"),
            data_dir=Path(env.get("KOC_DATA_DIR", "./data")),
            host=env.get("KOC_HOST", cls.host),
            port=int(env.get("PORT", env.get("KOC_PORT", cls.port))),
            davet_kodlari=_list(env.get("KOC_DAVET_KODLARI")),
            acik_kayit=env.get("KOC_ACIK_KAYIT", "").lower() in ("1", "true", "evet"),
            izinli_hostlar=_list(env.get("KOC_IZINLI_HOSTLAR")),
            telegram_token=env.get("KOC_TELEGRAM_TOKEN", "").strip(),
            telegram_api=env.get("KOC_TELEGRAM_API", cls.telegram_api).rstrip("/"),
            sabah_saati=env.get("KOC_SABAH_SAATI", cls.sabah_saati),
            aksam_saati=env.get("KOC_AKSAM_SAATI", cls.aksam_saati),
            **({"izinli_yonlendirmeler": _list(env["KOC_IZINLI_YONLENDIRMELER"])}
               if env.get("KOC_IZINLI_YONLENDIRMELER") else {}),
        )
