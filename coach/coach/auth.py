"""OAuth 2.1 authorization server and the sign-in, Obsidian and upload pages.

When Claude or ChatGPT adds the connector:
1. it reads the authorization details from the /.well-known/... addresses,
2. registers itself at /register (Dynamic Client Registration),
3. sends the user to /authorize; we redirect them to the /account/login page,
4. after the user signs in with email and password we create a code and return to the client's redirect_uri,
5. the client exchanges the code for an access token at /token.
Tokens are stored in the database only as SHA-256 hashes.
"""
from __future__ import annotations

import hashlib
import hmac
import html
import json
import logging
import secrets
import time
from collections import defaultdict, deque
from urllib.parse import urlencode, urlparse

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

from mcp.server.auth.provider import (AccessToken, AuthorizationCode, AuthorizationParams, AuthorizeError,
                                      RefreshToken, RegistrationError, TokenError, construct_redirect_uri)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

from .config import Settings
from .db import DB, token_hash
from .i18n import LANGUAGES, from_accept_language, normalize, t
from .vault import VaultError

SCOPE = "coach"
REQUEST_SECONDS = 15 * 60
CODE_SECONDS = 5 * 60
LANG_COOKIE = "lang"


class Provider:
    """SQLite implementation of the mcp SDK's OAuthAuthorizationServerProvider protocol."""

    def __init__(self, db: DB, settings: Settings):
        self.db = db
        self.settings = settings

    # --- clients -----------------------------------------------------------------
    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        rows = self.db.q("SELECT data FROM oauth_clients WHERE client_id = ?", (client_id,))
        return OAuthClientInformationFull.model_validate_json(rows[0]["data"]) if rows else None

    def redirect_allowed(self, uri: str) -> bool:
        host = (urlparse(str(uri)).hostname or "").lower()
        return any(host == d or host.endswith("." + d) for d in self.settings.allowed_redirects)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        if not client_info.client_id:
            raise ValueError("missing client_id")
        for uri in client_info.redirect_uris or []:
            if not self.redirect_allowed(str(uri)):
                raise RegistrationError("invalid_redirect_uri",
                                        f"This server only connects to known apps: {urlparse(str(uri)).hostname}")
        self.db.x("INSERT OR REPLACE INTO oauth_clients (client_id, data, created) VALUES (?, ?, ?)",
                  (client_info.client_id, client_info.model_dump_json(), time.time()))

    # --- authorization -------------------------------------------------------------
    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        self.db.cleanup()
        request_id = secrets.token_urlsafe(24)
        self.db.x("INSERT INTO oauth_pending (id, client_id, params, expires) VALUES (?, ?, ?, ?)",
                  (request_id, client.client_id, params.model_dump_json(), time.time() + REQUEST_SECONDS))
        return f"{self.settings.public_url}/account/login?request={request_id}"

    def pending(self, request_id: str) -> tuple[str, AuthorizationParams] | None:
        rows = self.db.q("SELECT client_id, params, expires FROM oauth_pending WHERE id = ?", (request_id,))
        if not rows or rows[0]["expires"] < time.time():
            return None
        return rows[0]["client_id"], AuthorizationParams.model_validate_json(rows[0]["params"])

    def issue_code(self, request_id: str, user_id: str) -> str:
        """Sign-in succeeded: creates a single-use authorization code and returns the client's redirect address."""
        found = self.pending(request_id)
        if found is None:
            raise AuthorizeError("access_denied", "login_expired")
        client_id, params = found
        self.db.x("DELETE FROM oauth_pending WHERE id = ?", (request_id,))
        code = secrets.token_urlsafe(32)
        data = AuthorizationCode(
            code=code, scopes=params.scopes or [SCOPE], expires_at=time.time() + CODE_SECONDS,
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

    def _issue_tokens(self, client_id: str, user_id: str, scopes: list[str], resource: str | None) -> OAuthToken:
        now = time.time()
        access = secrets.token_urlsafe(32)
        refresh = secrets.token_urlsafe(48)
        for token, kind, seconds in ((access, "access", self.settings.access_token_seconds),
                                     (refresh, "refresh", self.settings.refresh_token_seconds)):
            self.db.x("INSERT INTO oauth_tokens (token_hash, kind, client_id, user_id, scopes, resource, expires,"
                      " created) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                      (token_hash(token), kind, client_id, user_id, json.dumps(scopes), resource, now + seconds, now))
        return OAuthToken(access_token=access, expires_in=self.settings.access_token_seconds,
                          refresh_token=refresh, scope=" ".join(scopes))

    async def exchange_authorization_code(self, client: OAuthClientInformationFull,
                                          authorization_code: AuthorizationCode) -> OAuthToken:
        deleted = self.db.x("DELETE FROM oauth_codes WHERE code_hash = ?", (token_hash(authorization_code.code),))
        if not deleted or not authorization_code.subject:
            raise TokenError("invalid_grant", "The code was already used or is invalid.")
        return self._issue_tokens(client.client_id, authorization_code.subject,
                                  authorization_code.scopes, authorization_code.resource)

    def _row(self, token: str, kind: str):
        rows = self.db.q("SELECT * FROM oauth_tokens WHERE token_hash = ? AND kind = ?", (token_hash(token), kind))
        if not rows or (rows[0]["expires"] is not None and rows[0]["expires"] < time.time()):
            return None
        return rows[0]

    async def load_refresh_token(self, client: OAuthClientInformationFull, refresh_token: str) -> RefreshToken | None:
        row = self._row(refresh_token, "refresh")
        if row is None or row["client_id"] != client.client_id:
            return None
        return RefreshToken(token=refresh_token, client_id=row["client_id"], scopes=json.loads(row["scopes"]),
                            expires_at=int(row["expires"]), resource=row["resource"], subject=row["user_id"])

    async def exchange_refresh_token(self, client: OAuthClientInformationFull, refresh_token: RefreshToken,
                                     scopes: list[str]) -> OAuthToken:
        # Refresh tokens are single use (rotation): the old one is deleted.
        deleted = self.db.x("DELETE FROM oauth_tokens WHERE token_hash = ? AND kind = 'refresh'",
                            (token_hash(refresh_token.token),))
        if not deleted or not refresh_token.subject:
            raise TokenError("invalid_grant", "Invalid refresh token.")
        return self._issue_tokens(client.client_id, refresh_token.subject, scopes or refresh_token.scopes,
                                  refresh_token.resource)

    async def load_access_token(self, token: str) -> AccessToken | None:
        row = self._row(token, "access")
        if row is None or self.db.user(row["user_id"]) is None:
            return None
        return AccessToken(token=token, client_id=row["client_id"], scopes=json.loads(row["scopes"]),
                           expires_at=int(row["expires"]), resource=row["resource"], subject=row["user_id"])

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        self.db.x("DELETE FROM oauth_tokens WHERE token_hash = ?", (token_hash(token.token),))


# --- sign-in attempt limit ---------------------------------------------------------
class RateLimiter:
    """At most 10 failed sign-ins per IP in 15 minutes."""

    def __init__(self, limit: int = 10, window: float = 900):
        self.limit, self.window = limit, window
        self._events: dict[str, deque] = defaultdict(deque)

    def blocked(self, key: str) -> bool:
        q = self._events[key]
        while q and q[0] < time.time() - self.window:
            q.popleft()
        return len(q) >= self.limit

    def fail(self, key: str) -> None:
        self._events[key].append(time.time())


# --- HTML ------------------------------------------------------------------------
_CSS = """
:root{color-scheme:light dark;--bg:#f6f5f2;--card:#fff;--fg:#1d1d1f;--muted:#6b6b70;--acc:#0b6e4f;--on-acc:#fff;--err:#b3261e}
@media (prefers-color-scheme:dark){:root{--bg:#141414;--card:#1e1e1f;--fg:#f2f2f2;--muted:#a0a0a5;--acc:#3ccf91;--on-acc:#05271a}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 -apple-system,system-ui,sans-serif}
main{max-width:420px;margin:0 auto;padding:32px 16px}
.card{background:var(--card);border-radius:16px;padding:24px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
h1{font-size:22px;margin:0 0 4px}p.muted{color:var(--muted);margin:0 0 20px;font-size:14px}
label{display:block;font-size:14px;margin:14px 0 6px;color:var(--muted)}
input{width:100%;font-size:17px;padding:12px;border-radius:10px;border:1px solid #8884;background:transparent;color:var(--fg)}
button{width:100%;margin-top:20px;font-size:17px;padding:13px;border:0;border-radius:10px;background:var(--acc);color:var(--on-acc);font-weight:600}
.err{color:var(--err);font-size:14px;margin-top:12px}.tabs{display:flex;gap:8px;margin-bottom:8px}
.tabs a{flex:1;text-align:center;padding:8px;border-radius:8px;color:var(--fg);text-decoration:none;font-size:14px}
.tabs a.on{background:#8882}code{font-size:14px;word-break:break-all;background:#8882;padding:2px 6px;border-radius:6px}
.langs{text-align:center;margin-top:16px;font-size:13px}.langs a{color:var(--muted);margin:0 6px}
"""


def request_lang(request: Request) -> str:
    """?lang= wins, then the language cookie, then the browser's Accept-Language."""
    return (normalize(request.query_params.get("lang")) or normalize(request.cookies.get(LANG_COOKIE))
            or from_accept_language(request.headers.get("accept-language")))


def page(request: Request, title: str, body: str, status: int = 200, head: str = "", bare: bool = False) -> HTMLResponse:
    """A page in the shared look. `head` adds styles or scripts; `bare` leaves out the card around the body."""
    lang = request_lang(request)
    query = {k: v for k, v in request.query_params.items() if k != "lang"}
    links = " ".join(f"<a href='?{html.escape(urlencode({**query, 'lang': code}))}'>{name}</a>"
                     for code, name in LANGUAGES.items() if code != lang)
    content = body if bare else f"<div class='card'>{body}</div>"
    response = HTMLResponse(
        f"<!doctype html><html lang='{lang}'><head><meta charset='utf-8'>"
        f"<meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title>"
        f"<style>{_CSS}</style>{head}</head><body><main>{content}"
        f"<div class='langs'>{links}</div></main></body></html>",
        status_code=status, headers={"Cache-Control": "no-store", "X-Frame-Options": "DENY"})
    if normalize(request.query_params.get("lang")):
        response.set_cookie(LANG_COOKIE, lang, max_age=365 * 24 * 3600, samesite="lax")
    return response


def _login_form(lang: str, request_id: str, mode: str, error: str = "", email: str = "",
                invite_required: bool = True, app: str = "") -> str:
    e = html.escape
    tabs = (f"<div class='tabs'><a class='{'on' if mode == 'login' else ''}' href='?request={e(request_id)}&mode=login'>"
            f"{t(lang, 'login_tab')}</a><a class='{'on' if mode == 'signup' else ''}' "
            f"href='?request={e(request_id)}&mode=signup'>{t(lang, 'signup_tab')}</a></div>")
    invite = (f"<label for='invite'>{t(lang, 'invite_code')}</label><input id='invite' name='invite' autocomplete='off' "
              "required>" if mode == "signup" and invite_required else "")
    autocomplete = "new-password" if mode == "signup" else "current-password"
    return (
        f"<h1>{t(lang, 'app_name')}</h1>"
        f"<p class='muted'>{t(lang, 'login_intro_signup' if mode == 'signup' else 'login_intro_login')}</p>"
        + (f"<p class='muted'>{t(lang, 'connecting_app')} <b>{e(app)}</b></p>" if app else "")
        + tabs
        + f"<form method='post'><input type='hidden' name='request' value='{e(request_id)}'>"
        f"<input type='hidden' name='mode' value='{e(mode)}'><input type='hidden' name='lang' value='{e(lang)}'>"
        f"<label for='email'>{t(lang, 'email')}</label><input id='email' name='email' type='email' "
        f"autocomplete='username' value='{e(email)}' required>"
        f"<label for='password'>{t(lang, 'password')}</label><input id='password' name='password' type='password' "
        f"minlength='8' autocomplete='{autocomplete}' required>{invite}"
        f"<button type='submit'>{t(lang, 'signup_button' if mode == 'signup' else 'login_button')}</button>"
        + (f"<div class='err'>{e(error)}</div>" if error else "") + "</form>"
    )


SESSION_COOKIE = "coach_session"
SESSION_SECONDS = 90 * 24 * 3600
MAX_UPLOAD = 100 * 1024 * 1024  # textbook PDFs


class AccountPages:
    def __init__(self, db: DB, provider: Provider, settings: Settings):
        self.db, self.provider, self.settings = db, provider, settings
        self.limiter = RateLimiter()
        self.telegram_enabled = False
        key = settings.data_dir / "session.key"
        if not key.exists():
            key.parent.mkdir(parents=True, exist_ok=True)
            key.write_bytes(secrets.token_bytes(32))
            key.chmod(0o600)
        self._key = key.read_bytes()

    # --- long-lived cookie for the upload page -----------------------------------------
    def _sign(self, body: str) -> str:
        return hmac.new(self._key, body.encode(), hashlib.sha256).hexdigest()

    def make_cookie(self, user_id: str) -> str:
        body = f"{user_id}.{int(time.time()) + SESSION_SECONDS}"
        return f"{body}.{self._sign(body)}"

    def set_session(self, response: Response, user_id: str) -> None:
        # Lax (not Strict) so the session survives coming back from claude.ai or t.me to the getting-started page.
        response.set_cookie(SESSION_COOKIE, self.make_cookie(user_id), max_age=SESSION_SECONDS, httponly=True,
                            samesite="lax", secure=self.settings.public_url.startswith("https://"), path="/")

    def read_cookie(self, value: str | None) -> str | None:
        try:
            user_id, expires, signature = (value or "").split(".")
        except ValueError:
            return None
        if not hmac.compare_digest(signature, self._sign(f"{user_id}.{expires}")) or int(expires) < time.time():
            return None
        return user_id if self.db.user(user_id) else None

    @property
    def invite_required(self) -> bool:
        return not self.settings.open_signup

    def _ip(self, request: Request) -> str:
        fwd = request.headers.get("fly-client-ip") or request.headers.get("x-forwarded-for", "")
        return fwd.split(",")[0].strip() or (request.client.host if request.client else "?")

    def _invite_valid(self, code: str) -> bool:
        if not self.invite_required:
            return True
        return any(secrets.compare_digest(code.strip(), c) for c in self.settings.invite_codes)

    def authenticate(self, lang: str, mode: str, email: str, password: str, invite: str) -> tuple[str | None, str]:
        """(user_id, error message)."""
        if mode == "signup":
            if len(password) < 8:
                return None, t(lang, "err_password_short")
            if "@" not in email or len(email) > 200:
                return None, t(lang, "err_email")
            if not self._invite_valid(invite):
                return None, t(lang, "err_invite")
            if self.db.user_by_email(email):
                return None, t(lang, "err_email_taken")
            return self.db.create_user(email, password, lang), ""
        user_id = self.db.login(email, password)
        return (user_id, "") if user_id else (None, t(lang, "wrong_credentials"))

    async def _app_name(self, lang: str, request_id: str) -> str:
        found = self.provider.pending(request_id)
        if found is None:
            return ""
        client = await self.provider.get_client(found[0])
        host = urlparse(str(found[1].redirect_uri)).hostname or ""
        name = (client.client_name if client and client.client_name else "") or t(lang, "app_fallback")
        return f"{name} ({host})"

    def _expired(self, request: Request, lang: str, key: str) -> Response:
        return page(request, t(lang, "expired_title"),
                    f"<h1>{t(lang, key)}</h1><p class='muted'>{t(lang, 'reconnect_hint')}</p>", 400)

    async def login(self, request: Request) -> Response:
        lang = request_lang(request)
        if request.method == "GET":
            request_id = request.query_params.get("request", "")
            mode = "signup" if request.query_params.get("mode") == "signup" else "login"
            if self.provider.pending(request_id) is None:
                return self._expired(request, lang, "request_not_found")
            return page(request, t(lang, "app_name"),
                        _login_form(lang, request_id, mode, invite_required=self.invite_required,
                                    app=await self._app_name(lang, request_id)))
        form = await request.form()
        lang = normalize(str(form.get("lang", ""))) or lang
        request_id, mode = str(form.get("request", "")), str(form.get("mode", "login"))
        email, password = str(form.get("email", "")).strip(), str(form.get("password", ""))
        ip = self._ip(request)
        if self.limiter.blocked(ip):
            return page(request, t(lang, "wait_title"),
                        _login_form(lang, request_id, mode, t(lang, "too_many_attempts"), email, self.invite_required), 429)
        if self.provider.pending(request_id) is None:
            return self._expired(request, lang, "request_expired")
        user_id, error = self.authenticate(lang, mode, email, password, str(form.get("invite", "")))
        if not user_id:
            self.limiter.fail(ip)
            return page(request, t(lang, "app_name"),
                        _login_form(lang, request_id, mode, error, email, self.invite_required,
                                    await self._app_name(lang, request_id)), 400)
        try:
            target = self.provider.issue_code(request_id, user_id)
        except AuthorizeError:
            return page(request, t(lang, "error_title"),
                        f"<h1>{t(lang, 'connect_failed')}</h1><p class='muted'>{t(lang, 'login_expired')}</p>", 400)
        return RedirectResponse(target, status_code=303)

    async def obsidian(self, request: Request) -> Response:
        """Obsidian sync details: after signing in, shows the WebDAV address and a new app password."""
        lang, e = request_lang(request), html.escape
        form_html = (
            f"<h1>{t(lang, 'obsidian_title')}</h1><p class='muted'>{t(lang, 'obsidian_intro')}</p>"
            f"<form method='post'><label for='email'>{t(lang, 'email')}</label><input id='email' name='email' "
            f"type='email' autocomplete='username' required><label for='password'>{t(lang, 'account_password')}</label>"
            "<input id='password' name='password' type='password' autocomplete='current-password' required>"
            f"<button type='submit'>{t(lang, 'obsidian_button')}</button>")
        title = t(lang, "obsidian_title")
        if request.method == "GET":
            return page(request, title, form_html + "</form>")
        form = await request.form()
        ip = self._ip(request)
        if self.limiter.blocked(ip):
            return page(request, t(lang, "wait_title"),
                        form_html + f"<div class='err'>{t(lang, 'too_many_attempts')}</div></form>", 429)
        email = str(form.get("email", "")).strip()
        user_id = self.db.login(email, str(form.get("password", "")))
        if not user_id:
            self.limiter.fail(ip)
            return page(request, title, form_html + f"<div class='err'>{t(lang, 'wrong_credentials')}</div></form>", 400)
        dav_password = self.db.reset_dav_password(user_id)
        address = f"{self.settings.public_url}/dav/"
        return page(request, title, (
            f"<h1>{t(lang, 'obsidian_settings')}</h1><p class='muted'>{t(lang, 'obsidian_settings_intro')}</p>"
            f"<label>Server Address</label><code>{e(address)}</code>"
            f"<label>Username</label><code>{e(email.lower())}</code>"
            f"<label>Password</label><code>{e(dav_password)}</code>"
            "<label>Auth Type</label><code>basic</code>"
            "<label>Depth Header Sent To Servers</label><code>auto detect</code>"))

    async def upload(self, request: Request, save) -> Response:
        """Uploads question photos and study notes (PDF, Word, text) into the vault. Remembers the phone for
        90 days after the first sign-in; on iPhone "Add to Home Screen" turns it into a one-tap upload button."""
        lang = request_lang(request)
        user_id = self.read_cookie(request.cookies.get(SESSION_COOKIE))
        title = t(lang, "upload_title")
        login_form = (
            f"<h1>{title}</h1><p class='muted'>{t(lang, 'upload_login_intro')}</p>"
            "<form method='post'><input type='hidden' name='action' value='login'>"
            f"<label for='email'>{t(lang, 'email')}</label><input id='email' name='email' type='email' "
            "autocomplete='username' required>"
            f"<label for='password'>{t(lang, 'password')}</label><input id='password' name='password' type='password' "
            "autocomplete='current-password' required>"
            f"<button type='submit'>{t(lang, 'upload_login_button')}</button>")
        upload_form = (
            f"<h1>{title}</h1><p class='muted'>{t(lang, 'upload_intro')}</p>"
            "<form method='post' enctype='multipart/form-data'><input type='hidden' name='action' value='upload'>"
            "<input type='file' name='file' accept='image/*,.pdf,.docx,.txt,.md,.csv' multiple required>"
            f"<label for='note'>{t(lang, 'upload_note')}</label>"
            f"<input id='note' name='note' placeholder='{html.escape(t(lang, 'upload_note_placeholder'))}'>"
            f"<button type='submit'>{t(lang, 'upload_button')}</button></form>"
            + (f"<p class='muted' style='margin-top:20px'>{t(lang, 'upload_telegram')} "
               f"<a href='/upload/telegram'>{t(lang, 'connect_telegram')}</a></p>" if self.telegram_enabled else ""))
        if request.method == "GET":
            return page(request, title, upload_form if user_id else login_form + "</form>")
        form = await request.form()
        if form.get("action") == "login":
            ip = self._ip(request)
            if self.limiter.blocked(ip):
                return page(request, t(lang, "wait_title"),
                            login_form + f"<div class='err'>{t(lang, 'too_many_attempts')}</div></form>", 429)
            uid = self.db.login(str(form.get("email", "")), str(form.get("password", "")))
            if not uid:
                self.limiter.fail(ip)
                return page(request, title, login_form + f"<div class='err'>{t(lang, 'wrong_credentials')}</div></form>", 400)
            response = page(request, title, upload_form)
            self.set_session(response, uid)
            return response
        if not user_id:
            return page(request, title, login_form + "</form>", 401)
        files = []
        for item in form.getlist("file"):
            if not hasattr(item, "read"):
                continue
            data = await item.read()
            if len(data) > MAX_UPLOAD:
                return page(request, title, upload_form + f"<div class='err'>{t(lang, 'upload_too_big')}</div>", 413)
            if data:
                files.append((item.filename or "photo.jpg", data))
        if not files:
            return page(request, title, upload_form + f"<div class='err'>{t(lang, 'upload_no_file')}</div>", 400)
        try:
            paths = await run_in_threadpool(save, user_id, files[:10], str(form.get("note", ""))[:300])
        except VaultError as exc:
            return page(request, title, upload_form + f"<div class='err'>{html.escape(str(exc))[:300]}</div>", 400)
        except Exception:  # noqa: BLE001 - don't show internal details (paths) to the student
            logging.getLogger(__name__).exception("upload")
            return page(request, title, upload_form + f"<div class='err'>{t(lang, 'upload_failed')}</div>", 500)
        items = "".join(f"<li><code>{html.escape(p)}</code></li>" for p in paths)
        return page(request, t(lang, "uploaded_title"),
                    f"<h1>{t(lang, 'uploaded_title')}</h1><p class='muted'>{t(lang, 'uploaded_hint')}</p>"
                    f"<ul>{items}</ul><p><a href='/upload'>{t(lang, 'upload_another')}</a></p>")
