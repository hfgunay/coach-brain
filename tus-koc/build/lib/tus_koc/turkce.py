"""Türkçe kök bulucu.

Bu dosyadaki kök bulma kuralları avenoxai/avenoxbeyin projesinin
`template/.claude/scripts/beyin_v3.py` dosyasından olduğu gibi alınmıştır
(MIT Lisansı, Copyright (c) 2026 Avenox). Kurallar ve yorumlar orijinal haliyle
korunur; kaynakta bir düzeltme olursa buraya da taşınmalıdır.
"""
from __future__ import annotations

from collections import Counter
import functools
import re
import unicodedata


# Turkish is agglutinative, so exact token intersection loses "fark" against "farki" and
# "not" against "notlar". Every token is replaced by ONE canonical stem, with the same
# function on the query and the document side. Replacement, not expansion: the score stays
# "how many query words matched", which STRICT_MIN_SHARED and the idf weight depend on.
# A hyphenated name is the one exception (_COMPOUND): a note also counts its joined
# spelling, and a query uses that spelling only in place of a missing part (_query_compounds).
# Input reaches the stemmer already ASCII folded, so the table is written folded too.
_VOWELS = frozenset("aeiou")
_VOICELESS = frozenset("cfhkpst")
# (suffix, minimum stem length, what the character before the suffix must be). Longest
# first, peeled to a fixpoint: a fixed pass count breaks query/document symmetry, because
# "kutuphanesi" needs one more pass than "kutuphane" to reach the same stem.
# The n-buffered forms carry a stem floor of 5 because their n only ever follows a
# possessive vowel, so "cobanin" reads as coban+in while "arabanin" reads as araba+n+in.
_SUFFIXES = (
    # Verb endings (#430) peel only after l or n, which cover passive/reflexive forms:
    # kurulmali, kurulmasin, kurulur, kurulmus and kuruldu all reach "kurul". This is a
    # conservative spelling heuristic, not a voice classifier.
    ("masin", 4, "ln"), ("mesin", 4, "ln"), ("mali", 5, "ln"), ("meli", 5, "ln"),
    ("iyordu", 4, "ln"), ("uyordu", 4, "ln"), ("iyor", 4, "ln"), ("uyor", 4, "ln"),
    ("acak", 4, "ln"), ("ecek", 4, "ln"), ("acag", 4, "ln"), ("eceg", 4, "ln"),
    # Other consonant stems (#430): calisiyor, calisir, calismali, calisacak and calismis
    # reach the past tense stem "calist", which "calisti" already peels to. The bare stem
    # and the infinitive stay apart: they are how a prompt asks for an action (goster,
    # calistirmak gerekiyor), so such a prompt still matches no conjugation of its verb in
    # a note. m stays out: calismiyor is the negation, and the audit pairs it against
    # calisiyor. The aorist needs a vowel before one consonant other than d: calistir
    # (causative) and kalitedir (copula) are not calis+ir or kalited+ir.
    ("iyordu", 4, "verb"), ("uyordu", 4, "verb"), ("iyor", 4, "verb"), ("uyor", 4, "verb"),
    ("masin", 4, "verb"), ("mesin", 4, "verb"), ("mali", 5, "verb"), ("meli", 5, "verb"),
    ("acak", 4, "verb"), ("ecek", 4, "verb"), ("acag", 4, "verb"), ("eceg", 4, "verb"),
    ("mis", 4, "verb"), ("mus", 4, "verb"),
    ("ir", 5, "aorist"), ("ur", 5, "aorist"),
    ("imiz", 4, "consonant"), ("umuz", 4, "consonant"), ("iniz", 4, "consonant"), ("unuz", 4, "consonant"),
    ("nden", 5, "vowel"), ("ndan", 5, "vowel"),
    ("ten", 4, "voiceless"), ("tan", 4, "voiceless"), ("den", 4, "voiced"), ("dan", 4, "voiced"),
    ("nin", 5, "vowel"), ("nun", 5, "vowel"), ("nde", 5, "vowel"), ("nda", 5, "vowel"),
    ("miz", 4, "vowel"), ("muz", 4, "vowel"), ("niz", 4, "vowel"), ("nuz", 4, "vowel"),
    ("yla", 4, "vowel"), ("yle", 4, "vowel"),
    ("ler", 3, "any"), ("lar", 3, "any"),
    ("mak", 4, "ln"), ("mek", 4, "ln"), ("mis", 4, "ln"), ("mus", 4, "ln"),
    ("te", 4, "voiceless"), ("ta", 4, "voiceless"), ("de", 4, "voiced"), ("da", 4, "voiced"),
    ("si", 4, "vowel"), ("su", 4, "vowel"), ("ya", 4, "vowel"), ("ye", 4, "vowel"),
    ("yi", 4, "vowel"), ("yu", 4, "vowel"),
    ("in", 4, "consonant"), ("un", 4, "consonant"), ("im", 4, "consonant"), ("um", 4, "consonant"),
    ("le", 4, "consonant"), ("la", 4, "consonant"),
    # Past tense needs i or u before the l or n as well: "buildi" and "backendi" are a
    # loanword plus a possessive, not a passive verb.
    ("di", 5, "passive"), ("du", 5, "passive"), ("ma", 4, "ln"), ("me", 4, "ln"),
    # The aorist floor is 5: kurul+ur, but not the nouns sinir or kenar.
    ("ir", 5, "ln"), ("ur", 5, "ln"), ("ar", 5, "ln"), ("er", 5, "ln"),
    ("i", 4, "consonant"), ("u", 4, "consonant"), ("e", 4, "consonant"), ("a", 4, "consonant"),
)
# Keep the larger suffix table off the hot path without changing rule precedence.
_SUFFIXES_BY_LAST = {
    last: tuple(rule for rule in _SUFFIXES if rule[0][-1] == last)
    for last in {suffix[-1] for suffix, _, _ in _SUFFIXES}
}


# Vowel loss (#430): a few roots drop their last vowel before a vowel suffix, so peeling
# "metni" stops at "metn" while "metin" stays whole. The peeled short form is mapped back
# to the root, on both sides. Forms that are often another word stay out: resmi (official)
# for resim, emre (the name Emre) for emir, and al-in (take) for alin.
_VOWEL_LOSS = {
    "sehr": "sehir", "fikr": "fikir", "beyn": "beyin", "metn": "metin", "kism": "kisim",
    "hukm": "hukum", "nehr": "nehir", "zihn": "zihin", "vakt": "vakit", "nesl": "nesil",
    "seyr": "seyir", "haps": "hapis", "keyf": "keyif", "kayb": "kayip", "kayd": "kayit",
    "nakd": "nakit", "cism": "cisim", "zulm": "zulum", "kahr": "kahir", "sekl": "sekil",
    "gonl": "gonul", "gogs": "gogus",
    # A three-letter loss stops above the stem floor, so each surviving form is listed.
    "ismi": "isim", "ismin": "isim", "isme": "isim", "akli": "akil", "aklin": "akil",
    "akla": "akil", "agzi": "agiz", "agzin": "agiz", "agza": "agiz", "oglu": "ogul",
    "oglun": "ogul", "omru": "omur", "omrun": "omur", "emri": "emir", "emrin": "emir",
}
# These short forms are also another word, which the suffix that reached them tells apart:
# devri and devrinde come from devir, devre and devreye (circuit, activation) end in e and
# devrim (revolution) in im; burnu and burnundan come from burun, while English burn takes
# no suffix; karni comes from karin, karne (report card) ends in e.
_VOWEL_LOSS_AFTER = {
    "devr": ("devir", frozenset(("i", "in", "iniz"))),
    "burn": ("burun", frozenset(("u", "un", "um", "umuz", "unuz"))),
    "karn": ("karin", frozenset(("i", "in", "im", "imiz", "iniz"))),
}


def _attaches(stem, gate):
    previous = stem[-1]
    if gate == "vowel":
        return previous in _VOWELS
    if gate == "consonant":
        return previous not in _VOWELS
    if gate == "voiceless":
        return previous in _VOICELESS
    if gate == "voiced":
        return previous not in _VOICELESS
    if gate == "ln":
        return previous in "ln"
    if gate == "passive":
        return previous in "ln" and stem[-2] in "iu"
    if gate == "verb":
        return previous not in _VOWELS and previous not in "lnm"
    if gate == "aorist":
        return previous not in _VOWELS and previous not in "lnmd" and stem[-2] in _VOWELS
    return True


def _harmonizes(stem, suffix):
    """Weak vowel harmony: only an unambiguous last vowel (a/e) can decide."""
    tone = next((c for c in suffix if c in _VOWELS), "")
    if tone not in ("a", "e"):
        return True
    for character in reversed(stem):
        if character in _VOWELS:
            return character not in ("a", "e") or character == tone
    return True


@functools.lru_cache(maxsize=16384)
def _stem(word):
    last = ""
    # Words under 5 characters are already stems; peeling them merges unrelated roots.
    while len(word) >= 5:
        # Claude ends in the spelling of a Turkish locative suffix. Preserve the
        # name after peeling a real suffix, without scanning past folded vowels
        # (tarihte, hakime and kabulde need the existing weak harmony rule).
        if word == "claude":
            break
        for suffix, floor, gate in _SUFFIXES_BY_LAST.get(word[-1], ()):
            if not word.endswith(suffix):
                continue
            stem = word[:-len(suffix)]
            if len(stem) < floor or not _attaches(stem, gate) or not _harmonizes(stem, suffix):
                continue
            if gate in ("verb", "aorist"):
                # The past tense stem: t after a voiceless consonant, d otherwise. A d before
                # a vowel suffix is a softened t (kaydediyor, kaydetti).
                if stem[-1] == "d" and suffix[0] in _VOWELS:
                    stem = stem[:-1] + "t"
                return stem + ("t" if stem[-1] in _VOICELESS else "d")
            word, last = stem, suffix
            break
        else:
            break
    word = _VOWEL_LOSS.get(word, word)
    if word in _VOWEL_LOSS_AFTER and last in _VOWEL_LOSS_AFTER[word][1]:
        word = _VOWEL_LOSS_AFTER[word][0]
    # Consonant softening: kitap/kitabi and ornek/ornegi (soft g is already folded to g).
    # A b or g after a vowel goes back to p or k on every stem, peeled or not, so both
    # sides agree. d is left alone: past tense stems like "dened" would land on "denet".
    if len(word) >= 4 and word[-1] in "bg" and word[-2] in _VOWELS:
        word = word[:-1] + ("p" if word[-1] == "b" else "k")
    return word


def _fold(text):
    """The casefolded, accent-free text that _token_counts reads words from."""
    text = unicodedata.normalize("NFKD", str(text).casefold())
    return "".join(c for c in text if not unicodedata.combining(c)).replace("ı", "i")



_WORD = re.compile(r"[a-z0-9]+")


def kokler(text: str) -> list[str]:
    """Metindeki her kelimenin kökü, sırası korunarak (arama ve indeks aynı fonksiyonu kullanır)."""
    return [_stem(word) for word in _WORD.findall(_fold(text))]


def kok_sayilari(text: str) -> Counter:
    return Counter(kokler(text))


def katla(text: str) -> str:
    """Büyük/küçük harf ve aksan farkını kaldırır (ı -> i, ş -> s ...)."""
    return _fold(text)
