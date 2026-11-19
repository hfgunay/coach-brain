from calisma_kocu.config import Ayarlar, _adres

V = Ayarlar.public_url


def test_sema_unutulursa_https_eklenir():
    assert _adres({"KOC_PUBLIC_URL": "koc.up.railway.app/"}, V) == "https://koc.up.railway.app"


def test_tam_adres_degismez():
    assert _adres({"KOC_PUBLIC_URL": " https://koc.ornek.com/ "}, V) == "https://koc.ornek.com"


def test_yerel_adres_http():
    assert _adres({"KOC_PUBLIC_URL": "localhost:8000"}, V) == "http://localhost:8000"


def test_railway_alan_adi_yedek():
    assert _adres({"RAILWAY_PUBLIC_DOMAIN": "x.up.railway.app"}, V) == "https://x.up.railway.app"
    assert _adres({}, V) == V


def test_ingilizce_degisken_adlari():
    a = Ayarlar.ortamdan({"COACH_TELEGRAM_TOKEN": "yeni", "KOC_TELEGRAM_TOKEN": "eski",
                          "COACH_PUBLIC_URL": "x.up.railway.app", "KOC_SABAH_SAATI": "09:00"})
    assert a.telegram_token == "yeni"
    assert a.public_url == "https://x.up.railway.app"
    assert a.sabah_saati == "09:00"
