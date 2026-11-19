import string

from coach.i18n import LANGUAGES, MESSAGES, from_accept_language, normalize, t


def test_every_message_exists_in_every_language_with_the_same_placeholders():
    for key, entry in MESSAGES.items():
        assert set(entry) == set(LANGUAGES), key
        fields = {lang: {f for _, f, _, _ in string.Formatter().parse(text) if f} for lang, text in entry.items()}
        assert len({frozenset(v) for v in fields.values()}) == 1, key


def test_language_detection():
    assert from_accept_language("tr-TR,tr;q=0.9,en-US;q=0.8") == "tr"
    assert from_accept_language("de-DE,de;q=0.9,en;q=0.5") == "en"
    assert from_accept_language("de-DE") == "en"
    assert from_accept_language(None) == "en"
    assert normalize("TR_tr") == "tr" and normalize("fr") is None


def test_fallback_to_default():
    assert t(None, "app_name") == "Study Coach"
    assert t("tr", "app_name") == "Çalışma Koçu"
