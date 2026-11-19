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
