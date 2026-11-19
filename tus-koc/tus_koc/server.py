"""TUS Koçu uzak MCP sunucusu.

Çalıştırma:  python -m tus_koc.server
Uç noktalar:
  /mcp                 MCP (streamable HTTP, OAuth ile korunur)
  /hesap/giris         OAuth giriş ve kayıt sayfası
  /hesap/obsidian      WebDAV uygulama şifresi üretme sayfası
  /dav/                Kullanıcının Markdown klasörü (WebDAV, Basic auth)
  /saglik              Sağlık kontrolü
"""
from __future__ import annotations

import logging
from importlib import resources
from typing import Annotated, Any
from urllib.parse import urlparse

from pydantic import Field
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response
from starlette.routing import Mount

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations

from . import mufredat
from .auth import KAPSAM, HesapSayfalari, Saglayici, sayfa
from .coach import Koc
from .config import Ayarlar
from .db import DB
from .search import IndeksOnbellegi
from .vault import Vault, VaultHatasi
from .webdav import webdav_uygulamasi

log = logging.getLogger("tus_koc")

TALIMATLAR = resources.files("tus_koc").joinpath("talimatlar.md").read_text(encoding="utf-8")
KISA_TALIMAT = (
    "TUS çalışma koçunun hafızası. Her konuşmanın başında kaldigim_yer aracını çağır; anlamlı bir çalışma "
    "bittiğinde oturumu_kaydet ile kaydet. Konu anlatmadan önce notlarda_ara ile öğrencinin notlarına bak, "
    "soru sonuçlarını soru_sonucu_kaydet ile işle. Ayrıntılı koçluk talimatları için tus_kocu istemini kullan."
)

OKU = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
YAZ = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
EZ = ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=False)


def uygulama_kur(ayarlar: Ayarlar | None = None):
    ayarlar = ayarlar or Ayarlar.ortamdan()
    db = DB(ayarlar.db_path)
    saglayici = Saglayici(db, ayarlar)
    hesap = HesapSayfalari(db, saglayici, ayarlar)
    onbellek = IndeksOnbellegi()

    mcp = MCPServer(
        name="tus-koc",
        title="TUS Koçu",
        description="TUS çalışma koçu için kalıcı hafıza: notlar, oturumlar, zayıf konular ve çalışma planı.",
        instructions=KISA_TALIMAT,
        version="0.1.0",
        auth_server_provider=saglayici,
        auth=AuthSettings(
            issuer_url=ayarlar.public_url,
            resource_server_url=f"{ayarlar.public_url}/mcp",
            validate_token_resource=False,
            client_registration_options=ClientRegistrationOptions(
                enabled=True, valid_scopes=[KAPSAM], default_scopes=[KAPSAM]),
            revocation_options=RevocationOptions(enabled=True),
            required_scopes=[KAPSAM],
        ),
    )

    def koc() -> Koc:
        token = get_access_token()
        if token is None or not token.subject:
            raise VaultHatasi("Oturum bulunamadı; bağlayıcıyı yeniden bağlayın.")
        return Koc(Vault(ayarlar.vault_root, token.subject), db, onbellek)

    # --- araçlar ---------------------------------------------------------
    @mcp.tool(title="Kaldığım yer", annotations=OKU)
    def kaldigim_yer() -> dict[str, Any]:
        """Konuşmanın başında çağır. Öğrenci profili, sınava kalan gün, son oturum kartları, açık konular,
        koç kuralları, bugünün planı, zayıf konular ve tekrar zamanı gelen konuları döndürür."""
        return koc().kaldigim_yer()

    @mcp.tool(title="Notlarda ara", annotations=OKU)
    def notlarda_ara(
        sorgu: Annotated[str, Field(description="Aranacak konu ya da soru, doğal Türkçe. Örn: 'digoksin toksisitesi'")],
        limit: Annotated[int, Field(description="En çok kaç pasaj dönsün (1-25)")] = 8,
        koc_dosyalari_dahil: Annotated[bool, Field(description="Profil, oturum ve kural dosyaları da aransın mı")] = False,
    ) -> dict[str, Any]:
        """Öğrencinin notlarında Türkçe ek ve çekimleri tanıyan arama yapar, ilgili pasajları döndürür.
        Konu anlatmadan önce öğrencinin kendi notlarına bakmak için kullan."""
        return {"sonuclar": koc().ara(sorgu, limit, koc_dosyalari_dahil)}

    @mcp.tool(title="Not oku", annotations=OKU)
    def not_oku(
        ad: Annotated[str, Field(description="Not adı (örn. 'Digoksin') ya da yolu (örn. 'Konular/Farmakoloji/Digoksin.md')")],
    ) -> dict[str, Any]:
        """Bir notun tamamını, bağlantılarını ve etiketlerini okur."""
        return koc().not_oku(ad)

    @mcp.tool(title="Not yaz", annotations=EZ)
    def not_yaz(
        baslik: Annotated[str, Field(description="Notun başlığı; dosya adı olur. Örn: 'Digoksin'")],
        icerik: Annotated[str, Field(description="Markdown içerik. İlgili konuları [[Konu adı]] biçiminde bağla.")],
        ders: Annotated[str | None, Field(description="TUS dersi, örn. 'Farmakoloji'. Not Konular/<Ders>/ altına yazılır.")] = None,
        etiketler: Annotated[list[str] | None, Field(description="Etiketler, örn. ['yüksek-verim', 'çıkmış-soru']")] = None,
        mod: Annotated[str, Field(description="olustur (varsa hata), sona_ekle (var olan nota ekler) ya da uzerine_yaz")] = "olustur",
        klasor: Annotated[str | None, Field(description="Özel klasör; verilmezse ders klasörü kullanılır")] = None,
    ) -> dict[str, Any]:
        """Öğrencinin kasasına Obsidian uyumlu Markdown not yazar ya da var olan nota ekler."""
        return koc().not_yaz(baslik, icerik, ders=ders, klasor=klasor, etiketler=etiketler, mod=mod)

    @mcp.tool(title="Notları listele", annotations=OKU)
    def notlari_listele(
        klasor: Annotated[str | None, Field(description="Örn. 'Konular/Farmakoloji'; boşsa tüm notlar")] = None,
        limit: Annotated[int, Field(description="En çok kaç not")] = 100,
    ) -> dict[str, Any]:
        """Kasadaki notları son değişiklik sırasıyla listeler."""
        return {"notlar": koc().notlari_listele(klasor, max(1, min(limit, 500)))}

    @mcp.tool(title="Konu ilişkileri", annotations=OKU)
    def konu_iliskileri(
        konu: Annotated[str, Field(description="Konu ya da not adı")],
    ) -> dict[str, Any]:
        """Notlardaki [[bağlantılar]] ve etiketlerden konunun ilişkili olduğu konuları çıkarır: bağlandıkları,
        ona bağlananlar, iki adım uzaktakiler ve henüz notu açılmamış bağlantılar."""
        return koc().konu_iliskileri(konu)

    @mcp.tool(title="Soru sonucu kaydet", annotations=YAZ)
    def soru_sonucu_kaydet(
        ders: Annotated[str, Field(description="TUS dersi, örn. 'Biyokimya'")],
        konu: Annotated[str, Field(description="Konu, örn. 'Lipid metabolizması'")],
        dogru: Annotated[int, Field(description="Doğru sayısı")],
        yanlis: Annotated[int, Field(description="Yanlış sayısı")],
        bos: Annotated[int, Field(description="Boş sayısı")] = 0,
        kaynak: Annotated[str | None, Field(description="Soru kaynağı, örn. 'çıkmış 2019' ya da 'deneme 3'")] = None,
        aciklama: Annotated[str | None, Field(description="Yanlışların kısa nedeni")] = None,
        tarih: Annotated[str | None, Field(description="YYYY-AA-GG; boşsa bugün")] = None,
    ) -> dict[str, Any]:
        """Bir soru bloğunun sonucunu kaydeder; konu başarısı, tekrar zamanı ve Performans notu güncellenir."""
        return koc().soru_sonucu_kaydet(ders, konu, dogru, yanlis, bos, kaynak, aciklama, tarih)

    @mcp.tool(title="Zayıf konular", annotations=OKU)
    def zayif_konular(
        limit: Annotated[int, Field(description="Kaç konu")] = 10,
        ders: Annotated[str | None, Field(description="Yalnız bu ders")] = None,
    ) -> dict[str, Any]:
        """Soru sonuçlarına göre en zayıf konuları, ders başarılarını ve hiç çalışılmamış dersleri döndürür.
        Başarı düşükse, tekrar zamanı geldiyse ya da son denemelerde düşüş varsa konu üste çıkar."""
        return koc().zayif_konular(limit, ders)

    @mcp.tool(title="Çalışma planı oluştur", annotations=EZ)
    def calisma_plani_olustur(
        gun_sayisi: Annotated[int, Field(description="Kaç günlük plan (1-28)")] = 7,
        gunluk_saat: Annotated[float | None, Field(description="Günlük çalışma saati; boşsa profildeki değer")] = None,
        baslangic: Annotated[str | None, Field(description="YYYY-AA-GG; boşsa bugün")] = None,
        kaydet: Annotated[bool, Field(description="Plan/Çalışma Planı.md dosyasına yazılsın mı")] = True,
    ) -> dict[str, Any]:
        """Sınava kalan süre, ders ağırlıkları, zayıf konular ve tekrar zamanlarına göre günlük bloklu plan üretir.
        Sonucu öğrenciyle konuşup gerekirse düzelt ve not_yaz ile güncelle."""
        return koc().calisma_plani(gun_sayisi, gunluk_saat, baslangic, kaydet)

    @mcp.tool(title="Oturumu kaydet", annotations=YAZ)
    def oturumu_kaydet(
        ozet: Annotated[str, Field(description="2-4 cümlelik özet: ne çalışıldı, ne anlaşıldı, nerede zorlanıldı")],
        calisilan_konular: Annotated[list[str] | None, Field(description="Konu adları")] = None,
        sonraki_adim: Annotated[str | None, Field(description="Bir sonraki oturumda ilk yapılacak iş")] = None,
        etiket: Annotated[str | None, Field(description="Kısa etiket, örn. 'farmakoloji soru'")] = None,
        sure_dakika: Annotated[int | None, Field(description="Çalışma süresi")] = None,
        ruh_hali: Annotated[str | None, Field(description="Öğrencinin durumu, örn. 'yorgun ama motive'")] = None,
    ) -> dict[str, Any]:
        """Anlamlı bir çalışma bitince çağır. Son Oturum dosyasının en üstüne kart açar ve günün oturum notuna ekler;
        bir sonraki konuşmada kaldigim_yer bunu getirir."""
        return koc().oturumu_kaydet(ozet, calisilan_konular, sonraki_adim, etiket, sure_dakika, ruh_hali)

    @mcp.tool(title="Açık konu güncelle", annotations=YAZ)
    def acik_konu_guncelle(
        baslik: Annotated[str, Field(description="Konu başlığı, örn. 'Otonom farmakolojisi ikinci yarı'")],
        durum: Annotated[str, Field(description="acik ya da kapandi")] = "acik",
        aciklama: Annotated[str | None, Field(description="Kısa not")] = None,
    ) -> dict[str, Any]:
        """Yarım kalan ya da tekrar dönülecek konuyu Açık Konular listesine ekler veya kapatır."""
        return koc().acik_konu_guncelle(baslik, durum, aciklama)

    @mcp.tool(title="Kural ekle", annotations=YAZ)
    def kural_ekle(
        kural: Annotated[str, Field(description="Öğrencinin kalıcı talimatı, örn. 'Cevapları madde madde ve kısa ver'")],
    ) -> dict[str, Any]:
        """Öğrenci koçu düzelttiğinde ya da kalıcı bir tercih söylediğinde kural olarak kaydeder."""
        return koc().kural_ekle(kural)

    @mcp.tool(title="Profili güncelle", annotations=YAZ)
    def profili_guncelle(
        ad: Annotated[str | None, Field(description="Öğrencinin adı")] = None,
        sinav_tarihi: Annotated[str | None, Field(description="YYYY-AA-GG")] = None,
        hedef: Annotated[str | None, Field(description="Hedef branş ya da puan")] = None,
        gunluk_saat: Annotated[float | None, Field(description="Günlük çalışma saati")] = None,
        guclu_dersler: Annotated[list[str] | None, Field(description="Güçlü dersler")] = None,
        zayif_dersler: Annotated[list[str] | None, Field(description="Zayıf dersler")] = None,
        notlar: Annotated[str | None, Field(description="Profile eklenecek serbest not (alışkanlık, motivasyon)")] = None,
    ) -> dict[str, Any]:
        """Öğrenci profilini (Koç/Profil.md) günceller. Yalnız verilen alanlar değişir."""
        alanlar = {"ad": ad, "sinav_tarihi": sinav_tarihi, "hedef": hedef, "gunluk_saat": gunluk_saat,
                   "guclu_dersler": guclu_dersler, "zayif_dersler": zayif_dersler}
        return koc().profili_guncelle(alanlar, notlar)

    @mcp.tool(title="TUS müfredatı", annotations=OKU)
    def tus_mufredati(
        ders: Annotated[str | None, Field(description="Yalnız bu dersin konuları")] = None,
    ) -> dict[str, Any]:
        """TUS derslerini, ana konu başlıklarını ve planlama ağırlıklarını döndürür. Ders ve konu adlarını
        kaydederken bu adları kullan."""
        if ders:
            ad = mufredat.ders_normalle(ders)
            return {ad: mufredat.DERSLER.get(ad, {})}
        return {"dersler": mufredat.DERSLER,
                "not": "Ağırlıklar göreli önemdir, soru sayısı değildir; güncel dağılım ÖSYM kılavuzundan doğrulanmalı."}

    @mcp.prompt(name="tus_kocu", title="TUS koçu", description="TUS çalışma koçunun tam talimatları")
    def tus_kocu() -> str:
        return TALIMATLAR

    # --- HTTP rotaları -----------------------------------------------------
    @mcp.custom_route("/hesap/giris", methods=["GET", "POST"])
    async def giris(request: Request) -> Response:
        return await hesap.giris(request)

    @mcp.custom_route("/hesap/obsidian", methods=["GET", "POST"])
    async def obsidian(request: Request) -> Response:
        return await hesap.obsidian(request)

    @mcp.custom_route("/saglik", methods=["GET"])
    async def saglik(request: Request) -> Response:
        db.q("SELECT 1")
        return JSONResponse({"durum": "iyi"})

    @mcp.custom_route("/", methods=["GET"])
    async def ana(request: Request) -> Response:
        return sayfa("TUS Koçu", (
            "<h1>TUS Koçu</h1><p class='muted'>Bu bir MCP sunucusudur. Claude ya da ChatGPT'ye özel bağlayıcı olarak"
            f" ekleyin:</p><code>{ayarlar.public_url}/mcp</code>"
            "<p class='muted' style='margin-top:20px'>Obsidian ile eşitlemek için "
            "<a href='/hesap/obsidian'>Obsidian eşitleme</a> sayfasını açın.</p>"))

    host = urlparse(ayarlar.public_url).netloc
    guvenlik = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[host, "localhost:*", "127.0.0.1:*", *ayarlar.izinli_hostlar],
        allowed_origins=[ayarlar.public_url, "https://claude.ai", "https://chatgpt.com",
                         "http://localhost:*", "http://127.0.0.1:*"],
    )
    app = mcp.streamable_http_app(transport_security=guvenlik, host=ayarlar.host)
    app.router.routes.append(Mount("/dav", app=webdav_uygulamasi(db, ayarlar.vault_root)))
    return app


def main() -> None:
    import uvicorn

    ayarlar = Ayarlar.ortamdan()
    logging.basicConfig(level=logging.INFO)
    uvicorn.run(uygulama_kur(ayarlar), host=ayarlar.host, port=ayarlar.port, proxy_headers=True,
                forwarded_allow_ips="*")


if __name__ == "__main__":
    main()
