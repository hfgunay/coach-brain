# Obsidian eşitleme (isteğe bağlı)

Koç çalışmak için Obsidian'a ihtiyaç duymaz. Bu adımlar, koçun yazdığı notları iPad'de **Obsidian** ile görmek, bağlantı grafiğinde gezmek ve kendi notlarını eklemek isteyenler için.

## Nasıl çalışıyor

- Sunucuda her öğrencinin düz bir Markdown klasörü var. Koç notları buraya yazar.
- Obsidian bu klasörün bir kopyasını iPad'de tutar. **Remotely Save** eklentisi iki kopyayı WebDAV üzerinden eşitler.
- `[[Digoksin]]` gibi bağlantılar dosyanın içinde düz yazıdır. Obsidian bunları grafik olarak çizer, sunucu da aynı yazıyı okuyup koça "bu konu şunlarla ilişkili" bilgisini verir (`konu_iliskileri` aracı).
- Obsidian'da yazdığın not, eşitlemeden sonra koçun aramasında da çıkar.

Sunucuda Obsidian çalışmaz, taşınmaz. Obsidian yalnız iPad'deki görüntüleyici ve editördür.

## Kurulum (iPad ya da iPhone, bir kez)

1. **Şifre al.** Safari'de `<sunucu adresi>/hesap/obsidian` sayfasını aç. Koç hesabının e-posta ve şifresini gir. Sayfa sana **Server Address**, **Username** ve tek seferlik bir **Password** gösterir. Bu ekranı açık tut ya da ekran görüntüsü al.
2. App Store'dan **Obsidian**'ı kur, aç, **Create new vault** → ad: `TUS` → konum: **On my iPad** (iCloud değil).
3. Obsidian → **Settings** → **Community plugins** → **Turn on community plugins** → **Browse** → `Remotely Save` ara → **Install** → **Enable**.
4. **Settings → Remotely Save**:
   - **Remote Service**: `Webdav`
   - **Server Address**, **Username**, **Password**: 1. adımdaki değerler
   - **Auth Type**: `basic`
   - **Depth Header Sent To Servers**: `auto detect`
   - **Check Connectivity** → "connected" görmelisin.
   - **Schedule For Auto Run**: `every 5 minutes`, **Run Once On Start Up Automatically**: açık.
5. Sol kenardaki eşitleme simgesine bas. `Koç/`, `Konular/`, `Oturumlar/` klasörleri ve `Başla.md` gelir.

## Bilmen gerekenler

- Şifreyi kaybedersen 1. adımı tekrarla; yeni şifre üretilir, eskisi çalışmaz.
- Aynı notu aynı dakikada hem koça hem Obsidian'a düzenletirsen son kaydedilen kazanır. Koç oturumu bittikten sonra eşitle.
- `Koç/Performans.md` her soru kaydında sunucu tarafından yeniden yazılır; elle düzenlemeler kaybolur.
- Büyük PDF ve görselleri kasaya koyma; sunucuda kullanıcı başına disk sınırı yok ve eşitleme yavaşlar.
