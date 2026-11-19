"""The getting-started page (/start): one link a new student opens to sign up and finish setup.

A student who isn't technical won't find a custom connector setting on their own, so this page walks them through
it one step at a time and ticks each step off by itself, from what the server already knows: a connector token
exists (connected to Claude), start_session ran once (said hi to the coach), a Telegram link exists.
The page polls /start/status, so a step turns green when the student comes back from Claude or Telegram.
"""
from __future__ import annotations

import html
import json
from urllib.parse import urlencode

from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response

from .auth import SESSION_COOKIE, AccountPages, page, request_lang
from .i18n import LANGUAGES, normalize, t

CLAUDE_CONNECTORS = "https://claude.ai/settings/connectors"
CLAUDE_NEW_CHAT = "https://claude.ai/new"

_CSS = """
.lang{display:flex;gap:4px;background:#8882;border-radius:99px;padding:3px;width:max-content;margin:0 0 18px auto}
.lang a{padding:5px 12px;border-radius:99px;font-size:13px;color:var(--fg);text-decoration:none}
.lang a.on{background:var(--card);font-weight:600;box-shadow:0 1px 2px rgba(0,0,0,.12)}
.langs{display:none}
.hero{padding:8px 4px 20px}.hero h1{font-size:28px;line-height:1.2;margin:0 0 10px}
.hero p{color:var(--muted);margin:0}
.feats{list-style:none;padding:0;margin:20px 0 0}.feats li{display:flex;gap:12px;margin:0 0 14px;font-size:15px}
.feats .ic{flex:none;width:36px;height:36px;border-radius:10px;display:grid;place-items:center;background:#0b6e4f1a;
font-size:18px}
.needs{font-size:14px;color:var(--muted);text-align:center;margin:18px 0 0}
.switch{text-align:center;margin-top:16px;font-size:14px}.switch a{color:var(--acc)}
.top{display:flex;justify-content:space-between;align-items:baseline;margin:0 4px 10px}
.top h1{font-size:24px;margin:0}.top form{margin:0}
.link{background:none;border:0;padding:0;margin:0;width:auto;color:var(--muted);font-size:14px;font-weight:400;
text-decoration:underline;cursor:pointer}
.bar{height:8px;border-radius:99px;background:#8883;overflow:hidden;margin:6px 4px 4px}
.bar span{display:block;height:100%;background:var(--acc);border-radius:99px;transition:width .4s}
.count{font-size:13px;color:var(--muted);margin:0 4px 18px}
details.step{background:var(--card);border-radius:16px;margin:0 0 12px;box-shadow:0 1px 3px rgba(0,0,0,.08);
overflow:hidden}
details.step summary{list-style:none;display:flex;align-items:center;gap:12px;padding:16px 18px;cursor:pointer;
font-weight:600}
details.step summary::-webkit-details-marker{display:none}
.dot{flex:none;width:28px;height:28px;border-radius:50%;display:grid;place-items:center;font-size:14px;
border:2px solid #8886;color:var(--muted)}
.step.done .dot{background:var(--acc);border-color:var(--acc);color:var(--on-acc)}
.step.current .dot{border-color:var(--acc);color:var(--acc)}
.step.done summary .name{color:var(--muted);text-decoration:line-through;text-decoration-color:#8888}
.opt{font-weight:400;font-size:12px;color:var(--muted);border:1px solid #8885;border-radius:99px;padding:1px 8px;
margin-left:auto;white-space:nowrap}
.body{padding:0 18px 18px 58px;font-size:15px}.body ol{padding-left:18px;margin:0}.body li{margin:0 0 12px}
.copy{display:flex;gap:8px;align-items:stretch;margin-top:6px}
.copy code,.copy .msg{flex:1;display:block;padding:10px;border-radius:10px;background:#8881;font-size:14px;
word-break:break-all}
.copy .msg{word-break:normal;font-style:italic}
.copy button,.btn{width:auto;margin:0;padding:10px 14px;font-size:15px;border-radius:10px}
.btn{display:inline-block;margin-top:8px;background:var(--acc);color:var(--on-acc);text-decoration:none;font-weight:600}
.btn.ghost{background:transparent;color:var(--acc);border:1.5px solid var(--acc)}
.tip{font-size:13px;color:var(--muted);background:#8881;border-radius:10px;padding:10px 12px;margin-top:12px}
.wait{font-size:13px;color:var(--muted);margin-top:12px;display:flex;gap:8px;align-items:center}
.wait:before{content:"";width:8px;height:8px;border-radius:50%;background:var(--acc);animation:p 1.4s infinite}
@keyframes p{50%{opacity:.25}}
.done-card{background:var(--card);border-radius:16px;padding:22px;margin:0 0 12px;text-align:center;
box-shadow:0 1px 3px rgba(0,0,0,.08)}.done-card h2{margin:0 0 6px;font-size:22px}
.done-card p{color:var(--muted);margin:0 0 6px}
"""

_JS = """
document.addEventListener('click', e => {
  const b = e.target.closest('[data-copy]'); if (!b) return;
  const text = document.getElementById(b.dataset.copy).textContent.trim();
  const done = () => { const old = b.textContent; b.textContent = b.dataset.ok;
                       setTimeout(() => b.textContent = old, 1800); };
  if (navigator.clipboard) navigator.clipboard.writeText(text).then(done, () => {});
  else { const r = document.createRange(); r.selectNodeContents(document.getElementById(b.dataset.copy));
         getSelection().removeAllRanges(); getSelection().addRange(r); document.execCommand('copy'); done(); }
});
const holder = document.getElementById('state'), state = holder && holder.dataset.state;
async function check() {
  if (!state || document.hidden) return;
  try {
    const r = await fetch('/start/status', {credentials: 'same-origin', cache: 'no-store'});
    if (r.ok && JSON.stringify(await r.json()) !== state) location.reload();
  } catch (_) {}
}
if (state && JSON.parse(state).pending) { setInterval(check, 4000); document.addEventListener('visibilitychange', check); }
"""


def _language_switch(request: Request, lang: str) -> str:
    """A visible language choice at the top; the chosen language is remembered in a cookie (see page())."""
    keep = {k: v for k, v in request.query_params.items() if k != "lang"}
    links = []
    for code, name in LANGUAGES.items():
        query = html.escape(urlencode({**keep, "lang": code}))
        links.append(f"<a class='{'on' if code == lang else ''}' href='?{query}'>{name}</a>")
    return f"<nav class='lang'>{''.join(links)}</nav>"


class GettingStarted:
    def __init__(self, pages: AccountPages, public_url: str):
        self.pages, self.db, self.public_url = pages, pages.db, public_url

    def _status(self, user_id: str) -> dict:
        s = self.db.onboarding(user_id)
        if not self.pages.telegram_enabled:
            s.pop("telegram")
        # "pending" keeps the page polling until every step it can tick off by itself is done.
        s["pending"] = not all(s.values())
        return s

    async def status(self, request: Request) -> Response:
        user_id = self.pages.read_cookie(request.cookies.get(SESSION_COOKIE))
        if not user_id:
            return JSONResponse({"error": "signed out"}, status_code=401)
        return JSONResponse(self._status(user_id), headers={"Cache-Control": "no-store"})

    async def start(self, request: Request) -> Response:
        lang = request_lang(request)
        user_id = self.pages.read_cookie(request.cookies.get(SESSION_COOKIE))
        if request.method == "GET":
            if user_id:
                if normalize(request.query_params.get("lang")):
                    # Picking a language here also switches the Telegram bot's language.
                    self.db.x("UPDATE users SET lang = ? WHERE id = ?", (lang, user_id))
                    self.db.x("UPDATE channel_links SET lang = ? WHERE user_id = ?", (lang, user_id))
                return self._steps(request, lang, user_id)
            mode = "login" if request.query_params.get("mode") == "login" else "signup"
            return self._welcome(request, lang, mode, invite=request.query_params.get("invite", ""))

        form = await request.form()
        lang = normalize(str(form.get("lang", ""))) or lang
        action = str(form.get("action", ""))
        if action == "logout":
            response = RedirectResponse("/start?mode=login", status_code=303)
            response.delete_cookie(SESSION_COOKIE, path="/")
            return response
        mode = "login" if action == "login" else "signup"
        email, password = str(form.get("email", "")).strip(), str(form.get("password", ""))
        invite = str(form.get("invite", ""))
        ip = self.pages._ip(request)
        if self.pages.limiter.blocked(ip):
            return self._welcome(request, lang, mode, invite, email, t(lang, "too_many_attempts"), 429)
        uid, error = self.pages.authenticate(lang, mode, email, password, invite)
        if not uid:
            self.pages.limiter.fail(ip)
            return self._welcome(request, lang, mode, invite, email, error, 400)
        response = RedirectResponse("/start", status_code=303)
        self.pages.set_session(response, uid)
        return response

    # --- signed out: what this is + sign up ----------------------------------------------
    def _welcome(self, request: Request, lang: str, mode: str, invite: str = "", email: str = "",
                 error: str = "", status: int = 200) -> Response:
        e = html.escape
        signup = mode == "signup"
        # An invite that came in the link is carried along silently; a wrong one shows the field again.
        show_invite = signup and self.pages.invite_required and (not invite or bool(error))
        invite_field = (
            f"<label for='invite'>{t(lang, 'invite_code')}</label>"
            f"<input id='invite' name='invite' autocomplete='off' value='{e(invite)}' required>" if show_invite
            else f"<input type='hidden' name='invite' value='{e(invite)}'>")
        other = "login" if signup else "signup"
        switch_query = f"?mode={other}" + (f"&invite={e(invite)}" if invite else "")
        form = (
            "<div class='card'><form method='post'>"
            f"<input type='hidden' name='action' value='{mode}'><input type='hidden' name='lang' value='{lang}'>"
            f"<label for='email'>{t(lang, 'email')}</label>"
            f"<input id='email' name='email' type='email' autocomplete='username' value='{e(email)}' required>"
            f"<label for='password'>{t(lang, 'password')}</label><input id='password' name='password' "
            f"type='password' minlength='8' autocomplete='{'new-password' if signup else 'current-password'}' "
            f"required>{invite_field if signup else ''}"
            f"<button type='submit'>{t(lang, 'ob_signup_button' if signup else 'upload_login_button')}</button>"
            + (f"<div class='err'>{e(error)}</div>" if error else "")
            + (f"<p class='muted' style='margin:12px 0 0'>{t(lang, 'ob_remember_hint')}</p>" if signup else "")
            + f"</form><div class='switch'><a href='{switch_query}'>"
            f"{t(lang, 'ob_have_account' if signup else 'ob_new_account')}</a></div></div>")
        hero = (
            f"<div class='hero'><h1>{t(lang, 'ob_hero')}</h1><p>{t(lang, 'ob_hero_sub')}</p>"
            "<ul class='feats'>"
            f"<li><span class='ic'>🧠</span><span>{t(lang, 'ob_feat_memory')}</span></li>"
            f"<li><span class='ic'>📸</span><span>{t(lang, 'ob_feat_mistakes')}</span></li>"
            f"<li><span class='ic'>📅</span><span>{t(lang, 'ob_feat_plan')}</span></li></ul></div>")
        needs = f"<p class='needs'>{t(lang, 'ob_needs')}</p>" if signup else ""
        return page(request, t(lang, "app_name"), _language_switch(request, lang) + hero + form + needs, status,
                    head=f"<style>{_CSS}</style>", bare=True)

    # --- signed in: the checklist ------------------------------------------------------------
    def _steps(self, request: Request, lang: str, user_id: str) -> Response:
        e = html.escape
        status = self._status(user_id)
        user = self.db.user(user_id)
        name = t(lang, "app_name")
        connector = f"{self.public_url}/mcp"

        def copy(element_id: str, text: str, cls: str = "code") -> str:
            tag = "code" if cls == "code" else "div class='msg'"
            close = "code" if cls == "code" else "div"
            return (f"<div class='copy'><{tag} id='{element_id}'>{e(text)}</{close}>"
                    f"<button type='button' data-copy='{element_id}' data-ok='{e(t(lang, 'ob_copied'))}'>"
                    f"{t(lang, 'ob_copy')}</button></div>")

        steps = [
            ("connected", t(lang, "ob_step_connect"), False, (
                f"<ol><li>{t(lang, 'ob_connect_1')}{copy('mcp-url', connector)}</li>"
                f"<li>{t(lang, 'ob_connect_2')}<br><a class='btn' href='{CLAUDE_CONNECTORS}' target='_blank' "
                f"rel='noopener'>{t(lang, 'ob_open_connectors')} ↗</a></li>"
                f"<li>{t(lang, 'ob_connect_3', name=e(name))}</li>"
                f"<li>{t(lang, 'ob_connect_4', email=e(user['email']))}</li></ol>"
                f"<div class='tip'>📱 {t(lang, 'ob_connect_tip')}</div>")),
            ("chatted", t(lang, "ob_step_chat"), False, (
                f"<ol><li>{t(lang, 'ob_chat_1', name=e(name))}</li>"
                f"<li>{t(lang, 'ob_chat_2')}{copy('first-msg', t(lang, 'ob_first_message'), 'msg')}"
                f"<a class='btn' href='{CLAUDE_NEW_CHAT}' target='_blank' rel='noopener'>"
                f"{t(lang, 'ob_open_claude')} ↗</a></li></ol>"
                f"<div class='tip'>🔓 {t(lang, 'ob_chat_tip')}</div>")),
        ]
        if "telegram" in status:
            steps.append(("telegram", t(lang, "ob_step_telegram"), True, (
                f"<p style='margin-top:0'>{t(lang, 'ob_telegram_1')}</p>"
                f"<a class='btn' href='/upload/telegram'>{t(lang, 'connect_telegram')} ↗</a>"
                f"<p class='muted' style='margin:10px 0 0'>{t(lang, 'ob_telegram_2')}</p>")))
        steps.append((None, t(lang, "ob_step_upload"), True, (
            f"<p style='margin-top:0'>{t(lang, 'ob_upload_1')}</p>"
            f"<a class='btn ghost' href='/upload'>{t(lang, 'ob_open_upload')}</a>"
            f"<div class='tip'>📲 {t(lang, 'ob_upload_2')}</div>")))

        tracked = [k for k, *_ in steps if k]
        done = sum(1 for k in tracked if status[k])
        current = next((k for k in tracked if not status[k]), None)
        cards = []
        for number, (key, title, optional, body) in enumerate(steps, 1):
            finished = bool(key and status[key])
            cls = "done" if finished else "current" if key == current else ""
            # Required steps stay waiting until the server sees them done.
            wait = f"<div class='wait'>{t(lang, 'ob_waiting')}</div>" if key == "connected" and not finished else ""
            cards.append(
                f"<details class='step {cls}'{' open' if key == current else ''}><summary>"
                f"<span class='dot'>{'✓' if finished else number}</span><span class='name'>{title}</span>"
                + (f"<span class='opt'>{t(lang, 'ob_optional')}</span>" if optional else "")
                + f"</summary><div class='body'>{body}{wait}</div></details>")
        finished_all = status["connected"] and status["chatted"]
        celebrate = (f"<div class='done-card'><h2>{t(lang, 'ob_done_title')}</h2><p>{t(lang, 'ob_done_text')}</p>"
                     f"<a class='btn' href='{CLAUDE_NEW_CHAT}' target='_blank' rel='noopener'>"
                     f"{t(lang, 'ob_open_claude')} ↗</a></div>" if finished_all else "")
        percent = round(100 * done / len(tracked))
        body = (
            _language_switch(request, lang) + f"<div class='top'><h1>{t(lang, 'ob_hello')}</h1>"
            "<form method='post'><input type='hidden' name='action' value='logout'>"
            f"<button class='link' type='submit'>{t(lang, 'ob_sign_out')}</button></form></div>"
            f"<div class='bar'><span style='width:{percent}%'></span></div>"
            f"<p class='count'>{t(lang, 'ob_progress', done=done, total=len(tracked))}</p>"
            + celebrate + "".join(cards))
        # The status the page was drawn with; the script reloads when the server reports something new.
        state = e(json.dumps(status, separators=(",", ":")))
        return page(request, t(lang, "ob_title"),
                    body + f"<div id='state' hidden data-state='{state}'></div><script>{_JS}</script>",
                    head=f"<style>{_CSS}</style>", bare=True)
