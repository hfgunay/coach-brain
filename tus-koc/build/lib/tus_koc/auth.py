"""OAuth 2.1 yetkilendirme sunucusu ve giriş/kayıt sayfaları.

Claude ve ChatGPT bağlayıcı eklerken:
1. /.well-known/... adreslerinden yetkilendirme bilgisini okur,
2. /register ile kendini kaydeder (Dynamic Client Registration),
3. kullanıcıyı /authorize'a gönderir; biz onu /hesap/giris sayfasına yönlendiririz,
4. kullanıcı e-posta ve şifreyle girince kod üretip istemcinin redirect_uri'sine döneriz,
5. istemci /token ile kodu erişim belirtecine çevirir.
Belirteçler veritabanında yalnız SHA-256 özetiyle tutulur.
"""
from __future__ import annotations

import html
import json
import secrets
import time
from collections import defaultdict, deque

from pydantic import AnyUrl
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

from mcp.server.auth.provider import (AccessToken, AuthorizationCode, AuthorizationParams, AuthorizeError,
                                      RefreshToken, TokenError, construct_redirect_uri)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

from .config import Ayarlar
from .db import DB, token_hash

KAPSAM = "koc"
ISTEK_SURESI = 15 * 60
KOD_SURESI = 5 * 60


class Saglayici:
    """mcp SDK'nın OAuthAuthorizationServerProvider protokolünün SQLite uygulaması."""

    def __init__(self, db: DB, ayarlar: Ayarlar):
        self.db = db
        self.ayarlar = ayarlar

    # --- istemciler ----------------------------------------------------
    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        rows = self.db.q("SELECT data FROM oauth_clients WHERE client_id = ?", (client_id,))
        return OAuthClientInformationFull.model_validate_json(rows[0]["data"]) if rows else None

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        if not client_info.client_id:
            raise ValueError("client_id yok")
        self.db.x("INSERT OR REPLACE INTO oauth_clients (client_id, data, created) VALUES (?, ?, ?)",
                  (client_info.client_id, client_info.model_dump_json(), time.time()))

    # --- yetkilendirme ---------------------------------------------------
    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        self.db.temizle()
        istek = secrets.token_urlsafe(24)
        self.db.x("INSERT INTO oauth_pending (id, client_id, params, expires) VALUES (?, ?, ?, ?)",
                  (istek, client.client_id, params.model_dump_json(), time.time() + ISTEK_SURESI))
        return f"{self.ayarlar.public_url}/hesap/giris?istek={istek}"

    def bekleyen(self, istek: str) -> tuple[str, AuthorizationParams] | None:
        rows = self.db.q("SELECT client_id, params, expires FROM oauth_pending WHERE id = ?", (istek,))
        if not rows or rows[0]["expires"] < time.time():
            return None
        return rows[0]["client_id"], AuthorizationParams.model_validate_json(rows[0]["params"])

    def kodu_ver(self, istek: str, user_id: str) -> str:
        """Giriş başarılı: tek kullanımlık yetki kodu üretip istemciye dönülecek adresi verir."""
        found = self.bekleyen(istek)
        if found is None:
            raise AuthorizeError("access_denied", "Giriş isteğinin süresi doldu, bağlayıcıyı yeniden bağlayın.")
        client_id, params = found
        self.db.x("DELETE FROM oauth_pending WHERE id = ?", (istek,))
        code = secrets.token_urlsafe(32)
        data = AuthorizationCode(
            code=code, scopes=params.scopes or [KAPSAM], expires_at=time.time() + KOD_SURESI,
            client_id=client_id, code_challenge=params.code_challenge, redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            resource=params.resource, subject=user_id,
        )
        self.db.x("INSERT INTO oauth_codes (code_hash, data, expires) VALUES (?, ?, ?)",
                  (token_hash(code), data.model_dump_json(), data.expires_at))
        return construct_redirect_uri(str(params.redirect_uri), code=code, state=params.state)

    async def load_authorization_code(self, client: OAuthClientInformationFull,
                                      authorization_code: str) -> AuthorizationCode | None:
        rows = self.db.q("SELECT data FROM oauth_codes WHERE code_hash = ?", (token_hash(authorization_code),))
        if not rows:
            return None
        code = AuthorizationCode.model_validate_json(rows[0]["data"])
        if code.client_id != client.client_id or code.expires_at < time.time():
            return None
        return code.model_copy(update={"code": authorization_code})

    def _belirtec_ver(self, client_id: str, user_id: str, scopes: list[str], resource: str | None) -> OAuthToken:
        now = time.time()
        access = secrets.token_urlsafe(32)
        refresh = secrets.token_urlsafe(48)
        for token, kind, sure in ((access, "access", self.ayarlar.access_token_saniye),
                                  (refresh, "refresh", self.ayarlar.refresh_token_saniye)):
            self.db.x("INSERT INTO oauth_tokens (token_hash, kind, client_id, user_id, scopes, resource, expires,"
                      " created) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                      (token_hash(token), kind, client_id, user_id, json.dumps(scopes), resource, now + sure, now))
        return OAuthToken(access_token=access, expires_in=self.ayarlar.access_token_saniye,
                          refresh_token=refresh, scope=" ".join(scopes))

    async def exchange_authorization_code(self, client: OAuthClientInformationFull,
                                          authorization_code: AuthorizationCode) -> OAuthToken:
        deleted = self.db.x("DELETE FROM oauth_codes WHERE code_hash = ?", (token_hash(authorization_code.code),))
        if not deleted or not authorization_code.subject:
            raise TokenError("invalid_grant", "Kod kullanılmış ya da geçersiz.")
        return self._belirtec_ver(client.client_id, authorization_code.subject,
                                  authorization_code.scopes, authorization_code.resource)

    def _satir(self, token: str, kind: str):
        rows = self.db.q("SELECT * FROM oauth_tokens WHERE token_hash = ? AND kind = ?", (token_hash(token), kind))
        if not rows or (rows[0]["expires"] is not None and rows[0]["expires"] < time.time()):
            return None
        return rows[0]

    async def load_refresh_token(self, client: OAuthClientInformationFull, refresh_token: str) -> RefreshToken | None:
        row = self._satir(refresh_token, "refresh")
        if row is None or row["client_id"] != client.client_id:
            return None
        return RefreshToken(token=refresh_token, client_id=row["client_id"], scopes=json.loads(row["scopes"]),
                            expires_at=int(row["expires"]), resource=row["resource"], subject=row["user_id"])

    async def exchange_refresh_token(self, client: OAuthClientInformationFull, refresh_token: RefreshToken,
                                     scopes: list[str]) -> OAuthToken:
        # Yenileme belirteci tek kullanımlık (rotation): eskisi silinir.
        deleted = self.db.x("DELETE FROM oauth_tokens WHERE token_hash = ? AND kind = 'refresh'",
                            (token_hash(refresh_token.token),))
        if not deleted or not refresh_token.subject:
            raise TokenError("invalid_grant", "Yenileme belirteci geçersiz.")
        return self._belirtec_ver(client.client_id, refresh_token.subject, scopes or refresh_token.scopes,
                                  refresh_token.resource)

    async def load_access_token(self, token: str) -> AccessToken | None:
        row = self._satir(token, "access")
        if row is None or self.db.kullanici(row["user_id"]) is None:
            return None
        return AccessToken(token=token, client_id=row["client_id"], scopes=json.loads(row["scopes"]),
                           expires_at=int(row["expires"]), resource=row["resource"], subject=row["user_id"])

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        self.db.x("DELETE FROM oauth_tokens WHERE token_hash = ?", (token_hash(token.token),))


# --- giriş denemesi sınırı -------------------------------------------------
class Sinirlayici:
    """IP başına 15 dakikada en çok 10 hatalı giriş."""

    def __init__(self, limit: int = 10, pencere: float = 900):
        self.limit, self.pencere = limit, pencere
        self._olaylar: dict[str, deque] = defaultdict(deque)

    def engelli(self, anahtar: str) -> bool:
        q = self._olaylar[anahtar]
        while q and q[0] < time.time() - self.pencere:
            q.popleft()
        return len(q) >= self.limit

    def hata(self, anahtar: str) -> None:
        self._olaylar[anahtar].append(time.time())


# --- HTML ----------------------------------------------------------------
_CSS = """
:root{color-scheme:light dark;--bg:#f6f5f2;--card:#fff;--fg:#1d1d1f;--muted:#6b6b70;--acc:#0b6e4f;--err:#b3261e}
@media (prefers-color-scheme:dark){:root{--bg:#141414;--card:#1e1e1f;--fg:#f2f2f2;--muted:#a0a0a5;--acc:#3ccf91}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 -apple-system,system-ui,sans-serif}
main{max-width:420px;margin:0 auto;padding:32px 16px}
.card{background:var(--card);border-radius:16px;padding:24px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
h1{font-size:22px;margin:0 0 4px}p.muted{color:var(--muted);margin:0 0 20px;font-size:14px}
label{display:block;font-size:14px;margin:14px 0 6px;color:var(--muted)}
input{width:100%;font-size:17px;padding:12px;border-radius:10px;border:1px solid #8884;background:transparent;color:var(--fg)}
button{width:100%;margin-top:20px;font-size:17px;padding:13px;border:0;border-radius:10px;background:var(--acc);color:#fff;font-weight:600}
.err{color:var(--err);font-size:14px;margin-top:12px}.tabs{display:flex;gap:8px;margin-bottom:8px}
.tabs a{flex:1;text-align:center;padding:8px;border-radius:8px;color:var(--fg);text-decoration:none;font-size:14px}
.tabs a.on{background:#8882}code{font-size:14px;word-break:break-all;background:#8882;padding:2px 6px;border-radius:6px}
"""


def sayfa(baslik: str, govde: str, status: int = 200) -> HTMLResponse:
    return HTMLResponse(
        f"<!doctype html><html lang='tr'><head><meta charset='utf-8'>"
        f"<meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(baslik)}</title>"
        f"<style>{_CSS}</style></head><body><main><div class='card'>{govde}</div></main></body></html>",
        status_code=status, headers={"Cache-Control": "no-store", "X-Frame-Options": "DENY"})


def _form(istek: str, mod: str, hata: str = "", email: str = "", davet_gerekli: bool = True) -> str:
    e = html.escape
    sekme = (f"<div class='tabs'><a class='{'on' if mod == 'giris' else ''}' href='?istek={e(istek)}&mod=giris'>Giriş</a>"
             f"<a class='{'on' if mod == 'kayit' else ''}' href='?istek={e(istek)}&mod=kayit'>Yeni hesap</a></div>")
    davet = ("<label for='davet'>Davet kodu</label><input id='davet' name='davet' autocomplete='off' required>"
             if mod == "kayit" and davet_gerekli else "")
    sifre_ac = "new-password" if mod == "kayit" else "current-password"
    return (
        f"<h1>TUS Koçu</h1><p class='muted'>Koçun notlarına erişmek için {'hesap aç' if mod == 'kayit' else 'giriş yap'}."
        f" Bu bilgiler yalnız bu sunucuda tutulur.</p>{sekme}"
        f"<form method='post'><input type='hidden' name='istek' value='{e(istek)}'>"
        f"<input type='hidden' name='mod' value='{e(mod)}'>"
        f"<label for='email'>E-posta</label><input id='email' name='email' type='email' autocomplete='username'"
        f" value='{e(email)}' required>"
        f"<label for='sifre'>Şifre</label><input id='sifre' name='sifre' type='password' minlength='8'"
        f" autocomplete='{sifre_ac}' required>{davet}"
        f"<button type='submit'>{'Hesap aç ve bağlan' if mod == 'kayit' else 'Giriş yap ve bağlan'}</button>"
        + (f"<div class='err'>{e(hata)}</div>" if hata else "") + "</form>"
    )


class HesapSayfalari:
    def __init__(self, db: DB, saglayici: Saglayici, ayarlar: Ayarlar):
        self.db, self.saglayici, self.ayarlar = db, saglayici, ayarlar
        self.sinir = Sinirlayici()

    @property
    def davet_gerekli(self) -> bool:
        return not self.ayarlar.acik_kayit

    def _ip(self, request: Request) -> str:
        fwd = request.headers.get("fly-client-ip") or request.headers.get("x-forwarded-for", "")
        return fwd.split(",")[0].strip() or (request.client.host if request.client else "?")

    def _davet_gecerli(self, kod: str) -> bool:
        if not self.davet_gerekli:
            return True
        return any(secrets.compare_digest(kod.strip(), k) for k in self.ayarlar.davet_kodlari)

    def kimlik_dogrula(self, mod: str, email: str, sifre: str, davet: str) -> tuple[str | None, str]:
        """(user_id, hata mesajı)."""
        if mod == "kayit":
            if len(sifre) < 8:
                return None, "Şifre en az 8 karakter olmalı."
            if "@" not in email or len(email) > 200:
                return None, "Geçerli bir e-posta yazın."
            if not self._davet_gecerli(davet):
                return None, "Davet kodu geçersiz."
            if self.db.kullanici_email(email):
                return None, "Bu e-postayla hesap var, Giriş sekmesini kullanın."
            return self.db.kullanici_olustur(email, sifre), ""
        user_id = self.db.giris(email, sifre)
        return (user_id, "") if user_id else (None, "E-posta ya da şifre hatalı.")

    async def giris(self, request: Request) -> Response:
        if request.method == "GET":
            istek = request.query_params.get("istek", "")
            mod = "kayit" if request.query_params.get("mod") == "kayit" else "giris"
            if self.saglayici.bekleyen(istek) is None:
                return sayfa("Süre doldu", "<h1>Bağlantı isteği bulunamadı</h1><p class='muted'>Claude ya da ChatGPT"
                             " uygulamasına dönüp bağlayıcıyı yeniden bağlayın.</p>", 400)
            return sayfa("TUS Koçu · Giriş", _form(istek, mod, davet_gerekli=self.davet_gerekli))
        form = await request.form()
        istek, mod = str(form.get("istek", "")), str(form.get("mod", "giris"))
        email, sifre, davet = str(form.get("email", "")).strip(), str(form.get("sifre", "")), str(form.get("davet", ""))
        ip = self._ip(request)
        if self.sinir.engelli(ip):
            return sayfa("Bekleyin", _form(istek, mod, "Çok fazla deneme. 15 dakika sonra tekrar deneyin.", email,
                                           self.davet_gerekli), 429)
        if self.saglayici.bekleyen(istek) is None:
            return sayfa("Süre doldu", "<h1>Bağlantı isteğinin süresi doldu</h1><p class='muted'>Uygulamaya dönüp"
                         " bağlayıcıyı yeniden bağlayın.</p>", 400)
        user_id, hata = self.kimlik_dogrula(mod, email, sifre, davet)
        if not user_id:
            self.sinir.hata(ip)
            return sayfa("TUS Koçu · Giriş", _form(istek, mod, hata, email, self.davet_gerekli), 400)
        try:
            hedef = self.saglayici.kodu_ver(istek, user_id)
        except AuthorizeError as exc:
            return sayfa("Hata", f"<h1>Bağlanamadı</h1><p class='muted'>{html.escape(exc.error_description or '')}</p>", 400)
        return RedirectResponse(hedef, status_code=303)

    async def obsidian(self, request: Request) -> Response:
        """Obsidian eşitleme bilgisi: girişten sonra WebDAV adresi ve yeni uygulama şifresi gösterilir."""
        e = html.escape
        form_html = (
            "<h1>Obsidian eşitleme</h1><p class='muted'>iPad'deki Obsidian'ın <b>Remotely Save</b> eklentisi için"
            " WebDAV bilgilerini alın. Her seferinde yeni şifre üretilir, eskisi geçersiz olur.</p>"
            "<form method='post'><label for='email'>E-posta</label><input id='email' name='email' type='email'"
            " autocomplete='username' required><label for='sifre'>Hesap şifresi</label><input id='sifre' name='sifre'"
            " type='password' autocomplete='current-password' required><button type='submit'>Bilgileri göster</button>")
        if request.method == "GET":
            return sayfa("Obsidian eşitleme", form_html + "</form>")
        form = await request.form()
        ip = self._ip(request)
        if self.sinir.engelli(ip):
            return sayfa("Bekleyin", form_html + "<div class='err'>Çok fazla deneme, 15 dakika bekleyin.</div></form>", 429)
        email = str(form.get("email", "")).strip()
        user_id = self.db.giris(email, str(form.get("sifre", "")))
        if not user_id:
            self.sinir.hata(ip)
            return sayfa("Obsidian eşitleme", form_html + "<div class='err'>E-posta ya da şifre hatalı.</div></form>", 400)
        dav_sifre = self.db.dav_sifresi_yenile(user_id)
        adres = f"{self.ayarlar.public_url}/dav/"
        return sayfa("Obsidian eşitleme", (
            "<h1>Remotely Save ayarları</h1><p class='muted'>Remotely Save → Remote Service: <b>Webdav</b> seçin ve"
            " aşağıdakileri girin. Bu şifre bir daha gösterilmez.</p>"
            f"<label>Server Address</label><code>{e(adres)}</code>"
            f"<label>Username</label><code>{e(email.lower())}</code>"
            f"<label>Password</label><code>{e(dav_sifre)}</code>"
            "<label>Auth Type</label><code>basic</code>"
            "<label>Depth Header Sent To Servers</label><code>supports depth=infinity</code>"))
