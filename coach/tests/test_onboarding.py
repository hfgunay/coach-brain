"""The getting-started page: one link signs a student up and ticks each setup step off by itself."""
import asyncio

import httpx

from test_e2e import INVITE, PASSWORD, _connect, _tools, base  # noqa: F401 - base is the shared server fixture


def test_getting_started_walks_through_setup(base):  # noqa: F811
    c = httpx.Client(base_url=base)
    # The home page sends everyone to /start, keeping the invite in the link.
    r = c.get("/?invite=" + INVITE)
    assert r.status_code == 303 and r.headers["location"] == f"/start?invite={INVITE}"

    # Signed out: what the product is and a sign-up form; the invite from the link isn't asked again.
    r = c.get(f"/start?invite={INVITE}&lang=tr")
    assert "Seni hatırlayan çalışma koçu" in r.text and "Hesabımı aç" in r.text
    assert "id='invite'" not in r.text and f"value='{INVITE}'" in r.text
    assert "id='invite'" in c.get("/start?lang=en").text  # no invite in the link: the field is shown

    # A wrong invite shows the field again with the error.
    r = c.post("/start", data={"action": "signup", "email": "new@example.com", "password": PASSWORD,
                               "invite": "nope", "lang": "en"})
    assert r.status_code == 400 and "id='invite'" in r.text

    r = c.post("/start", data={"action": "signup", "email": "new@example.com", "password": PASSWORD,
                               "invite": INVITE, "lang": "en"})
    assert r.status_code == 303 and r.headers["location"] == "/start"
    assert c.get("/start/status").json() == {"connected": False, "chatted": False, "pending": True}

    page = c.get("/start?lang=en").text
    assert "0 of 2 steps done" in page and f"{base}/mcp" in page and "new@example.com" in page
    assert "<details class='step current' open>" in page and "Connect your coach to Claude" in page

    # The same account connects through Claude's OAuth sign-in: step 1 ticks off.
    token, _, _ = _connect(base, "new@example.com", mode="login", lang="en")
    assert c.get("/start/status").json()["connected"] is True
    assert "1 of 2 steps done" in c.get("/start").text

    # The first start_session ticks off "say hi to your coach" and the page celebrates.
    asyncio.run(_tools(base, token, [("start_session", {})]))
    assert c.get("/start/status").json() == {"connected": True, "chatted": True, "pending": False}
    page = c.get("/start").text
    assert "You're all set" in page and "2 of 2 steps done" in page

    # The upload page shares the session, and signing out ends it.
    assert "type='file'" in c.get("/upload").text
    r = c.post("/start", data={"action": "logout"})
    assert r.status_code == 303
    c.cookies.clear()  # httpx keeps a deleted cookie until told; a browser drops it
    assert c.get("/start/status").status_code == 401


def test_existing_account_signs_in(base):  # noqa: F811
    _connect(base, "old@example.com")
    c = httpx.Client(base_url=base)
    assert "I already have an account" in c.get("/start?lang=en").text
    r = c.post("/start", data={"action": "login", "email": "old@example.com", "password": "wrong-password"})
    assert r.status_code == 400
    r = c.post("/start", data={"action": "login", "email": "old@example.com", "password": PASSWORD})
    assert r.status_code == 303
    assert c.get("/start/status").json()["connected"] is True
