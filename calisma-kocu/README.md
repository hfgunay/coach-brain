# Çalışma Koçu · avenoxbeyin'i telefondan kullanılır kılan uzak MCP sunucusu

Sınav ve ders çalışma odaklı ikinci beyin: soru çözülen her sınav ya da ders için. Öğrenci kendi Claude aboneliğini kullanır, bu sunucuyu **özel bağlayıcı** olarak ekler. Sunucu hiçbir dil modeli API'si çağırmaz; maliyeti barındırmadan ibarettir.

**Hafıza motoru bu klasörde değil, repo kökündeki avenoxbeyin'dir.** Sunucu her kullanıcı için resmi `scripts/install_v3.py` ile gerçek bir avenoxbeyin V3 kasası kurar ve MCP araçlarını o kasanın kendi `beyin.py` komutlarına bağlar. Arama, not ve görev yazımı, revision ve sha çakışma kontrolü, tekrar tarihleri (`review_at`), görev bitiş tarihleri (`due_at`), Companion dosyaları, oturum sonuçları (receipt) ve öğrenim adayları motordan gelir. Burada ayrı bir hafıza, plan ya da hata defteri mantığı yoktur.

```
iPhone / iPad                         Sunucu (tek konteyner)
┌──────────────┐  MCP + OAuth   ┌───────────────────────────────────────────┐
│ Claude uyg.  │ ─────────────► │ /mcp     araçlar ──► beyin.py --json <komut> │
└──────────────┘                │ /authorize, /token, /register (OAuth 2.1)  │
┌──────────────┐  HTTPS form    │ /yukle   soru fotoğrafı ──► kasa/Ekler/    │
│ Safari       │ ─────────────► │ /hesap/  giriş, Obsidian şifresi           │
└──────────────┘                │                                           │
┌──────────────┐  WebDAV        │ /dav/    kullanıcının kendi kasası         │
│ Obsidian +   │ ◄────────────► │                                           │
│ Remotely Save│                │ /data/vaults/<id>/  avenoxbeyin kasası     │
└──────────────┘                │ /data/state/<id>/   motorun indeks/kilit   │
                                │ /data/calisma_kocu.sqlite3  hesaplar + OAuth    │
                                └───────────────────────────────────────────┘
```

## Neyin nereden geldiği

| İhtiyaç | Kaynak |
| --- | --- |
| Profil, kurallar, kaldığı yer, açık konular | Kasadaki `🔮 850-Companion/` (Core, Kurallar, Last-Session, Threads) |
| Sohbet başı bağlam, tarihi gelen tekrar ve görevler | Kasanın SessionStart hook'u (`.claude/scripts/beyin_v3_hook.py`) |
| Ders notu, kitap PDF'i, Word | Repodaki Yakala gelen kutusu (`📥 000-Inbox/Yakala/`). Sunucu metni sayfa sayfa `kaynaklar/<belge>/` altına düz Markdown yazar, motorun kendi araması bulur; koç konu çalışıldıkça not çıkarır |
| Yapamadığı soru, konu notu | `note-create`; yeni notlar repo kuralı gereği `notes/` ya da `knowledge/` altında, klasörü koç seçer |
| Tekrar zamanı | Notun `review_at` alanı; motor "Due reviews" olarak getirir |
| Çalışma planı | `task-create` ile görevler, `project: sinav`, `due_at` |
| Koçluk davranışı | Yalnız koç skill'i: [calisma_kocu/skill/SKILL.md](calisma_kocu/skill/SKILL.md) (kasaya `.agents/skills/calisma-kocu/` olarak konur) |

## Araçlar

| Araç | beyin karşılığı |
| --- | --- |
| `kaldigim_yer` | SessionStart hook bağlamı + oturum kimliği |
| `talimatlari_oku` | Kasadaki AGENTS.md, beyin skill'i ve çalışma koçu skill'i |
| `kasada_ara` | `context` |
| `not_oku`, `not_olustur`, `not_duzenle` | `note-read`, `note-create`, `note-edit` |
| `gorev_olustur`, `gorev_guncelle` | `task-create`, `task-update` |
| `sonuc_kaydet` | `receipt` |
| `ogrenim_adayi` | `learn` |
| `kasa_durumu`, `son_sonuclar` | `triage`, `recap` |
| `yakalananlar`, `yakalanani_oku`, `yakalanan_bitti` | `yakala liste`, `yakala isle` (PDF/Word metni), `yakala bitti`: yüklenen ders notları |
| `ekleri_listele`, `eki_goster` | Sunucuya ait: `/yukle` sayfasından gelen fotoğrafları gösterir (Claude araç argümanıyla görsel gönderemediği için) |

`calisma_kocu` MCP istemi koç skill'inin metnini verir.

## Sunucuya ait olanlar

- OAuth 2.1 (DCR + PKCE), e-posta ve şifre ile hesap, davet kodu, giriş denemesi sınırı
- Kullanıcı başına kasa kurulumu ve kasaya kilitleme (yol hilesi korumalı)
- WebDAV (`/dav`): Obsidian eşitlemesi. Motorun yönettiği dosyalar (`beyin.py`, `AGENTS.md`, `CLAUDE.md`, nokta ile başlayan klasörler) gösterilmez ve yazılamaz.
- `/yukle`: telefondan yükleme sayfası. Fotoğraflar `Ekler/`'e (2000 px JPEG), PDF/Word/metin (100 MB'a kadar) `beyin.py yakala ekle` ile gelen kutusuna, metni aranabilir sayfalara.

## Yerelde çalıştırma

```bash
cd calisma-kocu
python -m venv .venv && . .venv/bin/activate
pip install -e ".[test]"
python -m pytest -q                      # gerçek kasa kurulumu, OAuth, MCP, ayrım, WebDAV, fotoğraf
KOC_DAVET_KODLARI=deneme calisma-kocu     # http://localhost:8000
```

Sunucu motoru repo kökünden bulur (`calisma-kocu/..`). Başka bir yerdeyse `KOC_BEYIN_KAYNAK` ile avenoxbeyin kopyasını gösterin. Claude'a bağlamak için internetten erişilen bir HTTPS adresi gerekir (örn. `cloudflared tunnel --url http://localhost:8000`), adresi `KOC_PUBLIC_URL` olarak verin.

## Belgeler

- [Yayına alma](docs/YAYINA_ALMA.md): Railway (önerilen) ya da Docker
- [Telefondan bağlama](docs/TELEFONDAN_BAGLAMA.md): öğrencinin adım adım yapacakları
- [Obsidian eşitleme](docs/OBSIDIAN.md): iPad'de kasayı görmek (isteğe bağlı)
- [Koç talimatları](docs/KOC_TALIMATLARI.md): koç skill'inin nerede durduğu ve nasıl güncellendiği

## Bilinen sınırlar (v0.2)

- Tek konteyner, tek kopya: SQLite, giriş sınırı ve MCP oturumları yerel.
- Bildirim yok: MCP sohbeti sunucu başlatamaz. Hatırlatma ve fotoğraf için Telegram botu planlanıyor.
- Şifre sıfırlama, ödeme ve kullanıcı başına disk kotası yok.
- Aynı notu aynı anda hem Obsidian hem koç yazarsa: koçun yazması motorun sha kontrolüyle korunur, Obsidian tarafında son eşitleyen kazanır.
