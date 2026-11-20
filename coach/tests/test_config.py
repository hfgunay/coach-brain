from coach.config import Settings, _public_url

D = Settings.public_url


def test_missing_scheme_gets_https():
    assert _public_url({"COACH_PUBLIC_URL": "coach.up.railway.app/"}, D) == "https://coach.up.railway.app"


def test_full_url_is_kept():
    assert _public_url({"COACH_PUBLIC_URL": " https://coach.example.com/ "}, D) == "https://coach.example.com"


def test_local_address_uses_http():
    assert _public_url({"COACH_PUBLIC_URL": "localhost:8000"}, D) == "http://localhost:8000"


def test_railway_domain_fallback():
    assert _public_url({"RAILWAY_PUBLIC_DOMAIN": "x.up.railway.app"}, D) == "https://x.up.railway.app"
    assert _public_url({}, D) == D


def test_reads_coach_variables():
    s = Settings.from_env({"COACH_TELEGRAM_TOKEN": "t", "COACH_PUBLIC_URL": "x.up.railway.app",
                           "COACH_MORNING_TIME": "08:00", "COACH_INVITE_CODES": "a, b", "COACH_TIMEZONE": "Europe/Berlin"})
    assert s.telegram_token == "t" and s.public_url == "https://x.up.railway.app"
    assert s.morning_time == "08:00" and s.invite_codes == ["a", "b"] and s.timezone == "Europe/Berlin"


def test_defaults():
    s = Settings.from_env({})
    assert (s.morning_time, s.evening_time) == ("09:00", "22:00")


def test_old_names_are_ignored():
    assert Settings.from_env({"KOC_TELEGRAM_TOKEN": "t"}).telegram_token == ""


def test_old_oauth_scope_is_migrated(tmp_path):
    import json
    from coach.db import DB
    db = DB(tmp_path / "coach.sqlite3")
    db.x("INSERT INTO oauth_tokens (token_hash, kind, client_id, user_id, scopes, resource, expires, created)"
         " VALUES ('h', 'access', 'c', 'u', '[\"koc\"]', NULL, NULL, 0)")
    db.x("INSERT INTO oauth_clients (client_id, data, created) VALUES ('c', ?, 0)",
         (json.dumps({"client_id": "c", "scope": "koc", "redirect_uris": ["https://claude.ai/cb"]}),))
    db = DB(tmp_path / "coach.sqlite3")
    assert json.loads(db.q("SELECT scopes FROM oauth_tokens")[0]["scopes"]) == ["coach"]
    assert json.loads(db.q("SELECT data FROM oauth_clients")[0]["data"])["scope"] == "coach"
