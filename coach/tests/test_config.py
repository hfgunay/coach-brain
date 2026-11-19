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
