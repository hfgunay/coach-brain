"""TUS ders listesi ve planlama ağırlıkları.

Ağırlıklar soru sayısı DEĞİLDİR; plan dağıtırken kullanılan göreli önemdir
(sınavda ders başına düşen soru payına kabaca göre). Güncel soru dağılımı her
dönem ÖSYM kılavuzundan doğrulanmalı ve gerekirse burada düzeltilmelidir.
"""
from __future__ import annotations

from .turkce import katla

DERSLER: dict[str, dict] = {
    # Temel Tıp Bilimleri Testi
    "Anatomi": {"test": "Temel", "agirlik": 2, "konular": [
        "Üst ekstremite", "Alt ekstremite", "Toraks", "Abdomen", "Pelvis ve perine", "Baş ve boyun",
        "Nöroanatomi", "Kranial sinirler"]},
    "Fizyoloji": {"test": "Temel", "agirlik": 2, "konular": [
        "Hücre ve membran fizyolojisi", "Sinir-kas", "Kardiyovasküler", "Solunum", "Böbrek ve asit-baz",
        "Gastrointestinal", "Endokrin", "Merkezi sinir sistemi"]},
    "Histoloji ve Embriyoloji": {"test": "Temel", "agirlik": 1, "konular": [
        "Epitel ve bağ dokusu", "Kas ve sinir dokusu", "Organ histolojisi", "Gametogenez ve fertilizasyon",
        "Embriyonik dönem", "Organ gelişimi ve anomaliler"]},
    "Biyokimya": {"test": "Temel", "agirlik": 3, "konular": [
        "Aminoasit ve proteinler", "Enzimler", "Karbonhidrat metabolizması", "Lipid metabolizması",
        "Aminoasit metabolizması", "Nükleotid metabolizması", "Vitaminler", "Moleküler biyoloji ve genetik",
        "Hormonlar ve sinyal iletimi"]},
    "Mikrobiyoloji": {"test": "Temel", "agirlik": 3, "konular": [
        "Genel bakteriyoloji", "Gram pozitif bakteriler", "Gram negatif bakteriler", "Mikobakteriler",
        "Viroloji", "Hepatit virüsleri", "Mikoloji", "Parazitoloji", "İmmünoloji"]},
    "Patoloji": {"test": "Temel", "agirlik": 3, "konular": [
        "Hücre hasarı ve adaptasyon", "İnflamasyon ve onarım", "Hemodinamik bozukluklar", "Neoplazi",
        "Genetik hastalıklar", "İmmün sistem hastalıkları", "Kardiyovasküler patoloji", "Solunum patolojisi",
        "GİS ve karaciğer patolojisi", "Böbrek patolojisi", "Hematopatoloji", "Endokrin patoloji",
        "Kemik ve yumuşak doku", "Santral sinir sistemi patolojisi"]},
    "Farmakoloji": {"test": "Temel", "agirlik": 3, "konular": [
        "Farmakokinetik", "Farmakodinamik", "Otonom sinir sistemi ilaçları", "Kardiyovasküler ilaçlar",
        "MSS ilaçları", "Analjezik ve antiinflamatuvarlar", "Antimikrobiyaller", "Antineoplastikler",
        "Endokrin ilaçlar", "Toksikoloji"]},
    # Klinik Tıp Bilimleri Testi
    "Dahiliye": {"test": "Klinik", "agirlik": 4, "konular": [
        "Kardiyoloji", "Göğüs hastalıkları", "Gastroenteroloji", "Hepatoloji", "Nefroloji",
        "Endokrinoloji", "Hematoloji", "Onkoloji", "Romatoloji", "Enfeksiyon hastalıkları",
        "Sıvı-elektrolit"]},
    "Pediatri": {"test": "Klinik", "agirlik": 3, "konular": [
        "Büyüme-gelişme", "Yenidoğan", "Beslenme", "Aşılar", "Çocuk enfeksiyonları", "Çocuk kardiyolojisi",
        "Çocuk nefrolojisi", "Metabolik hastalıklar", "Çocuk hematoloji-onkoloji", "Çocuk nörolojisi",
        "Genetik sendromlar"]},
    "Genel Cerrahi": {"test": "Klinik", "agirlik": 3, "konular": [
        "Sıvı-elektrolit ve şok", "Travma", "Yanık", "Cerrahi enfeksiyon", "Meme", "Tiroid ve paratiroid",
        "Mide ve duodenum", "İnce ve kalın barsak", "Hepatobilier ve pankreas", "Fıtıklar", "Cerrahi onkoloji"]},
    "Kadın Hastalıkları ve Doğum": {"test": "Klinik", "agirlik": 2, "konular": [
        "Menstrüel siklus", "Gebelik fizyolojisi", "Antenatal takip", "Gebelik komplikasyonları",
        "Doğum eylemi", "Jinekolojik onkoloji", "İnfertilite", "Kontrasepsiyon", "Menopoz"]},
    "Küçük Stajlar": {"test": "Klinik", "agirlik": 3, "konular": [
        "Nöroloji", "Psikiyatri", "Dermatoloji", "Göz", "KBB", "Ortopedi", "Üroloji", "Radyoloji",
        "Anesteziyoloji", "Kalp-damar cerrahisi", "Göğüs cerrahisi", "Beyin cerrahisi",
        "Plastik cerrahi", "Fizik tedavi", "Halk sağlığı", "Acil tıp"]},
}

_TAKMA = {
    "dahiliye": "Dahiliye", "ic hastaliklari": "Dahiliye", "iç hastalıkları": "Dahiliye",
    "kadin dogum": "Kadın Hastalıkları ve Doğum", "kadın doğum": "Kadın Hastalıkları ve Doğum",
    "kadin hastaliklari": "Kadın Hastalıkları ve Doğum", "kd": "Kadın Hastalıkları ve Doğum",
    "cerrahi": "Genel Cerrahi", "genel cerrahi": "Genel Cerrahi",
    "pediatri": "Pediatri", "cocuk": "Pediatri", "çocuk": "Pediatri",
    "histoloji": "Histoloji ve Embriyoloji", "embriyoloji": "Histoloji ve Embriyoloji",
    "mikro": "Mikrobiyoloji", "farma": "Farmakoloji", "biyokim": "Biyokimya", "pato": "Patoloji",
    "kucuk stajlar": "Küçük Stajlar", "küçük stajlar": "Küçük Stajlar",
}
_KATLI = {katla(k): v for k, v in _TAKMA.items()} | {katla(k): k for k in DERSLER}
# Küçük stajlardaki branş adı tek başına yazılırsa da tanınsın (örn. "Nöroloji").
_KATLI |= {katla(konu): "Küçük Stajlar" for konu in DERSLER["Küçük Stajlar"]["konular"]}


def ders_normalle(ad: str) -> str:
    """Kullanıcının yazdığı ders adını listedeki ada çevirir; tanınmazsa olduğu gibi bırakır."""
    key = katla(ad).strip()
    return _KATLI.get(key, ad.strip())


def agirlik(ders: str) -> int:
    return DERSLER.get(ders, {}).get("agirlik", 2)
