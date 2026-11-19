from datetime import timedelta

import pytest

from tus_koc import coach as coach_mod
from tus_koc.vault import ACIK_KONULAR, KURALLAR, PERFORMANS, PLAN, PROFIL, SON_OTURUM, VaultHatasi, grafik_kur


def test_ilk_acilista_iskelet_ve_kaldigim_yer(koc):
    durum = koc.kaldigim_yer()
    assert set(durum["profil_eksik"]) == {"ad", "sinav_tarihi"}
    assert durum["sinava_kalan_gun"] is None
    for yol in (PROFIL, SON_OTURUM, ACIK_KONULAR, KURALLAR, "Başla.md"):
        assert koc.v.var_mi(yol)


def test_turkce_ekleri_tanir(koc):
    koc.not_yaz("Kalp yetmezliği", "Kalp yetmezliğinde digoksin pozitif inotroptur.\n\n[[Digoksin]] toksisitesinde"
                " hiperkalemi görülür.", ders="dahiliye")
    koc.not_yaz("Lipid metabolizması", "Beta oksidasyon mitokondride olur.", ders="Biyokimya")
    sonuc = koc.ara("yetmezlikte digoksinin etkisi")
    assert sonuc and sonuc[0]["yol"] == "Konular/Dahiliye/Kalp yetmezliği.md"
    assert koc.ara("mitokondriyal oksidasyonlar")[0]["baslik"] == "Lipid metabolizması"


def test_not_yazma_modlari(koc):
    koc.not_yaz("Digoksin", "Na/K ATPaz inhibitörü.", ders="Farmakoloji", etiketler=["yüksek verim"])
    with pytest.raises(VaultHatasi):
        koc.not_yaz("digoksin", "tekrar")
    koc.not_yaz("Digoksin", "## Toksisite\nGörme bozukluğu.", mod="sona_ekle", etiketler=["çıkmış-soru"])
    oku = koc.not_oku("DİGOKSİN")
    assert "Na/K ATPaz" in oku["icerik"] and "Görme bozukluğu" in oku["icerik"]
    assert oku["meta"]["tags"] == ["yüksek-verim", "çıkmış-soru"]
    assert oku["meta"]["ders"] == "Farmakoloji"


@pytest.mark.parametrize("yol", ["../disari", ".obsidian/app", "a/../../b", "Konular/.gizli"])
def test_klasor_disina_cikilamaz(koc, yol):
    with pytest.raises(VaultHatasi):
        koc.v.guvenli_yol(yol)


def test_mutlak_yol_kasa_icine_baglanir(koc):
    rel, path = koc.v.guvenli_yol("/etc/passwd")
    assert rel == "etc/passwd.md" and koc.v.dir in path.parents


def test_konu_iliskileri_obsidian_baglantilarindan(koc):
    koc.not_yaz("Digoksin", "Bkz [[Kalp yetmezliği]] ve [[Hiperkalemi|K yüksekliği]]. #farmakoloji", ders="Farmakoloji")
    koc.not_yaz("Kalp yetmezliği", "Tedavide [[ACE inhibitörleri]].", ders="Dahiliye")
    koc.not_yaz("ACE inhibitörleri", "Öksürük yapar. #farmakoloji", ders="Farmakoloji")
    rel = koc.konu_iliskileri("digoksin")
    assert rel["baglandigi"] == ["Konular/Dahiliye/Kalp yetmezliği.md"]
    assert rel["notu_olmayan_baglantilar"] == ["Hiperkalemi"]
    assert "Konular/Farmakoloji/ACE inhibitörleri.md" in rel["iki_adim_uzak"] or \
        any(x["yol"].endswith("ACE inhibitörleri.md") for x in rel["ortak_etiketli"])
    yok = koc.konu_iliskileri("Hiperkalemi")
    assert yok["notu_var"] is False and yok["bu_konuya_baglananlar"] == ["Konular/Farmakoloji/Digoksin.md"]


def test_kod_blogundaki_baglanti_sayilmaz(koc):
    koc.not_yaz("A", "`[[B]]` ve\n```\n[[C]]\n```\n[[D]]")
    g = grafik_kur(koc.v.notlar())
    assert g.cozulemeyen["Konular/A.md"] == ["D"]


def test_oturum_karti_en_uste_ve_kirpilir(koc):
    for i in range(coach_mod.SON_OTURUM_KART + 3):
        koc.oturumu_kaydet(f"özet {i}", ["Digoksin"], sonraki_adim="otonom", etiket=f"e{i}")
    metin = koc.v.oku(SON_OTURUM)
    assert metin.count("\n## ") == coach_mod.SON_OTURUM_KART
    assert metin.index(f"özet {coach_mod.SON_OTURUM_KART + 2}") < metin.index("özet 5")
    durum = koc.kaldigim_yer()
    assert durum["son_oturumlar"][0].startswith("## ") and "[[Digoksin]]" in durum["son_oturumlar"][0]
    gunluk = koc.v.oku(f"Oturumlar/{coach_mod.simdi():%Y-%m-%d}.md")
    assert gunluk.count("### ") == coach_mod.SON_OTURUM_KART + 3


def test_acik_konu_ac_kapat(koc):
    koc.acik_konu_guncelle("Otonom ikinci yarı", aciklama="kolinerjikler kaldı")
    koc.acik_konu_guncelle("Pürin metabolizması")
    koc.acik_konu_guncelle("otonom İKİNCİ yarı", durum="kapandi")
    metin = koc.v.oku(ACIK_KONULAR)
    acik, kapanan = metin.split("## Kapananlar")
    assert "Pürin" in acik and "Otonom" not in acik
    assert "- [x] otonom İKİNCİ yarı" in kapanan
    assert "Pürin" in koc.kaldigim_yer()["acik_konular"]


def test_kural_tekrar_eklenmez(koc):
    assert koc.kural_ekle("Cevapları kısa ver")["kaydedildi"]
    assert not koc.kural_ekle("cevapları kısa ver")["kaydedildi"]
    assert koc.v.oku(KURALLAR).count("kısa ver") == 1


def test_profil_ve_sinava_kalan_gun(koc):
    sinav = (coach_mod.simdi().date() + timedelta(days=40)).isoformat()
    koc.profili_guncelle({"ad": "Ayşe", "sinav_tarihi": sinav, "gunluk_saat": 5, "zayif_dersler": ["mikro"]},
                         notlar="Sabah daha verimli")
    durum = koc.kaldigim_yer()
    assert durum["sinava_kalan_gun"] == 40 and durum["profil_eksik"] == []
    assert durum["profil"]["zayif_dersler"] == ["Mikrobiyoloji"]
    assert "Sabah daha verimli" in koc.v.oku(PROFIL)
    with pytest.raises(VaultHatasi):
        koc.profili_guncelle({"sinav_tarihi": "yarın"})


def test_zayif_konu_siralamasi_ve_performans_notu(koc):
    koc.soru_sonucu_kaydet("Farmakoloji", "Otonom", dogru=4, yanlis=16)
    koc.soru_sonucu_kaydet("Biyokimya", "Enzimler", dogru=18, yanlis=2)
    koc.soru_sonucu_kaydet("farma", "otonom", dogru=6, yanlis=4)  # aynı konuya yazılmalı
    z = koc.zayif_konular()
    assert z["zayif_konular"][0]["konu"] in ("Otonom", "otonom")
    assert z["zayif_konular"][0]["toplam_soru"] == 30
    assert z["ders_basarilari"]["Biyokimya"] == 90
    assert "Patoloji" in z["hic_soru_cozulmemis_dersler"]
    assert "[[Enzimler]]" in koc.v.oku(PERFORMANS)
    with pytest.raises(VaultHatasi):
        koc.soru_sonucu_kaydet("Farmakoloji", "x", 0, 0)


def test_tekrar_zamani(koc):
    eski = (coach_mod.simdi().date() - timedelta(days=10)).isoformat()
    koc.soru_sonucu_kaydet("Patoloji", "Neoplazi", dogru=9, yanlis=1, tarih=eski)
    k = koc.konu_istatistikleri()[0]
    assert k["tekrar_araligi_gun"] == 7 and k["tekrar_zamani"] is True
    assert koc.kaldigim_yer()["tekrari_gelenler"][0]["konu"] == "Neoplazi"


def test_calisma_plani(koc):
    sinav = (coach_mod.simdi().date() + timedelta(days=20)).isoformat()
    koc.profili_guncelle({"sinav_tarihi": sinav, "gunluk_saat": 8})
    koc.soru_sonucu_kaydet("Farmakoloji", "Otonom", dogru=3, yanlis=7)
    plan = koc.calisma_plani(gun_sayisi=7)
    assert plan["evre"] == "tekrar + deneme" and len(plan["gunler"]) == 7
    turler = [b["tur"] for g in plan["gunler"] for b in g["bloklar"]]
    assert "deneme" in turler and "tekrar" in turler
    konular = [b.get("ders") for g in plan["gunler"] for b in g["bloklar"] if b["tur"] == "konu"]
    assert len(set(konular)) == len(konular) or len(konular) > 4  # dersler dönüşümlü
    md = koc.v.oku(PLAN)
    assert "- [ ]" in md and "[[Otonom]]" in md
    bugun = coach_mod.simdi().date().isoformat()
    assert koc.kaldigim_yer()["bugunun_plani"].startswith(f"## {bugun}")
