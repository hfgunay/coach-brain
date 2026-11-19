# TUS Koçu · uzak MCP hafıza sunucusu

TUS'a hazırlanan öğrenci için yapay zeka çalışma koçu. Öğrenci kendi Claude (ya da ChatGPT) aboneliğini kullanır, bu sunucuyu **özel bağlayıcı** olarak ekler. Koç notları, oturumları, zayıf konuları ve çalışma planını burada hatırlar. Sunucu hiçbir dil modeli API'si çağırmaz; maliyeti barındırmadan ibarettir.

Bu klasör [avenoxai/avenoxbeyin](https://github.com/avenoxai/avenoxbeyin) projesinin fikirlerini (Companion hafıza dosyaları, Türkçe kök bulucu, BM25 pasaj araması) telefondan kullanılabilen, çok kullanıcılı bir sunucuya taşır. Repo kökündeki masaüstü kurulumundan bağımsızdır.

```
iPhone / iPad                         Sunucu (tek konteyner)
┌──────────────┐  MCP + OAuth   ┌──────────────────────────────────┐
│ Claude uyg.  │ ─────────────► │ /mcp       14 koç aracı          │
└──────────────┘                │ /authorize, /token, /register    │
┌──────────────┐  WebDAV        │ /hesap/... giriş, Obsidian şifre │
│ Obsidian +   │ ◄────────────► │ /dav/      kullanıcının klasörü  │
│ Remotely Save│                │                                  │
└──────────────┘                │ /data/vaults/<kullanıcı>/*.md    │
                                │ /data/tus_koc.sqlite3            │
                                └──────────────────────────────────┘
```

## Kasa düzeni (Obsidian'da böyle görünür)

| Dosya | Görevi | avenoxbeyin karşılığı |
| --- | --- | --- |
| `Koç/Profil.md` | Ad, sınav tarihi, günlük saat, güçlü/zayıf dersler | Core |
| `Koç/Son Oturum.md` | Son 8 oturum kartı, en yeni üstte | Last-Session |
| `Koç/Açık Konular.md` | Yarım kalan konular, `- [ ]` listesi | Threads |
| `Koç/Kurallar.md` | Öğrencinin koça kalıcı talimatları | Kurallar |
| `Koç/Performans.md` | Konu bazlı başarı tablosu (sunucu üretir) | yok |
| `Plan/Çalışma Planı.md` | Günlük bloklu plan | yok |
| `Oturumlar/YYYY-AA-GG.md` | Günün tüm oturum kayıtları | daily log |
| `Konular/<Ders>/<Konu>.md` | Ders notları, `[[bağlantı]]` ve `#etiket` ile | Knowledge |

## Araçlar

| Araç | Ne yapar |
| --- | --- |
| `kaldigim_yer` | Konuşma başında profil, son oturum, açık konular, kurallar, bugünün planı, zayıf ve tekrarı gelen konular |
| `notlarda_ara` | Türkçe ekleri tanıyan BM25 pasaj araması ("yetmezliğinde" ↔ "yetmezlik") |
| `not_oku`, `not_yaz`, `notlari_listele` | Obsidian uyumlu not okuma/yazma (olustur, sona_ekle, uzerine_yaz) |
| `konu_iliskileri` | `[[bağlantı]]` grafiğinden ilişkili konular, geri bağlantılar, notu olmayan bağlantılar |
| `soru_sonucu_kaydet`, `zayif_konular` | Konu başarısı, aralıklı tekrar zamanı, zayıflık sıralaması |
| `calisma_plani_olustur` | Sınava kalan süreye, ders ağırlığına ve zayıf konulara göre plan |
| `oturumu_kaydet`, `acik_konu_guncelle`, `kural_ekle`, `profili_guncelle` | Hafıza dosyalarını günceller |
| `tus_mufredati` | Ders ve konu adları (istatistik dağılmasın diye) |

Ayrıca `tus_kocu` adlı bir MCP istemi tam koç talimatlarını verir ([tus_koc/talimatlar.md](tus_koc/talimatlar.md)).

## Yerelde çalıştırma

```bash
cd tus-koc
python -m venv .venv && . .venv/bin/activate
pip install -e ".[test]"
python -m pytest -q                      # 22 test: OAuth, MCP, kullanıcı ayrımı, WebDAV
TUS_KOC_DAVET_KODLARI=deneme tus-koc     # http://localhost:8000
```

Yerelde Claude'a bağlamak için sunucunun internetten erişilebilir HTTPS adresi gerekir (örn. `cloudflared tunnel --url http://localhost:8000`), adresi `TUS_KOC_PUBLIC_URL` olarak verin.

## Belgeler

- [Yayına alma](docs/YAYINA_ALMA.md): Railway (önerilen) ya da herhangi bir Docker sunucusu
- [Telefondan bağlama](docs/TELEFONDAN_BAGLAMA.md): öğrencinin adım adım yapacakları
- [Obsidian eşitleme](docs/OBSIDIAN.md): iPad'de notları görmek (isteğe bağlı)
- [Koç talimatları](docs/KOC_TALIMATLARI.md): Claude Projesine yapıştırılacak metin

## Bilinen sınırlar (v0.1)

- Tek konteyner, tek kopya çalışmalı: SQLite, giriş deneme sınırı ve MCP oturumları bellekte/yerel diskte.
- Şifre sıfırlama yok (e-posta gönderimi yok). Şimdilik yönetici veritabanından sıfırlar.
- Ödeme ve abonelik yok; kayıt davet koduyla kapalı.
- Kullanıcı başına disk kotası yok; WebDAV'dan büyük PDF/görsel yüklenirse disk dolabilir.
- WebDAV ile aynı anda hem Obsidian hem koç aynı dosyayı yazarsa son yazan kazanır.
