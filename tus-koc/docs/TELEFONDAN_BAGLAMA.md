# Telefondan bağlama (öğrenci için)

Bu rehberi bir kez yapman yeterli, 5 dakika sürer. Sana iki şey verilecek:

- **Bağlayıcı adresi**, örn. `https://tus-koc-production.up.railway.app/mcp`
- **Davet kodu**

## Claude ile (önerilen)

Claude'un ücretsiz planında bir özel bağlayıcı eklenebilir. Her gün uzun çalışacaksan Pro planı mesaj sınırına daha geç takılır.

### 1. Bağlayıcıyı ekle

En kolayı iPhone ya da iPad'de **Safari**'den yapmak. Eklediğin bağlayıcı Claude uygulamasına kendiliğinden gelir.

1. Safari'de [claude.ai](https://claude.ai) aç ve giriş yap.
2. Sol menü → **Customize** (Özelleştir) → **Connectors** (Bağlayıcılar) → **Add custom connector**.
3. **Name**: `TUS Koçu`. **URL**: sana verilen bağlayıcı adresi.
4. Kimlik doğrulama ya da OAuth seçeneği sorulursa: **Sign in now**, OAuth client için **Register automatically**.
5. **Add**, sonra **Connect**.
6. TUS Koçu giriş sayfası açılır. İlk sefer **Yeni hesap** sekmesini seç: e-posta, en az 8 karakterlik şifre ve davet kodu yaz. **Hesap aç ve bağlan**.
7. Claude'a geri dönersin, bağlayıcının yanında "Connected" yazar.

> Bu e-posta ve şifre Claude hesabın değil, koçun hafızasının hesabıdır. Bir yere not al; Obsidian eşitlemesi için de lazım olacak.

### 2. Koç projesini kur (bir kez)

1. Claude'da **Projects** → **New project** → ad: `TUS Koçu`.
2. Projenin **Instructions** (talimatlar) alanına şunu yaz: `Her sohbette önce TUS Koçu bağlayıcısından kaldigim_yer'i, sonra talimatlari_oku'yu çalıştır.` Koçluk talimatlarının tamamı sunucuda, kasanın içinde durur.
3. Proje özelliği planında yoksa sorun değil: sunucu kısa talimatı zaten veriyor. Her yeni sohbete "TUS koçum olarak başla" yazman yeterli.

### 3. Fotoğraf yükleme sayfası (bir kez)

Claude, sohbete attığın fotoğrafı bağlayıcıya aktaramaz. Saklanacak soru fotoğrafları için:

1. Safari'de `<sunucu adresi>/yukle` aç, koç hesabınla giriş yap (90 gün hatırlar).
2. Paylaş → **Ana Ekrana Ekle**. Artık telefonda "Soru yükle" simgesi var.
3. Yapamadığın sorunun fotoğrafını oradan yükle, sonra koça "az önce yüklediğim soruya bakalım" yaz. Koç `eki_goster` ile görür.

### 4. Her gün

1. Claude uygulamasında **TUS Koçu** projesinde yeni sohbet aç.
2. Mesaj kutusundaki **+** → **Connectors** → **TUS Koçu** açık olsun.
3. "Merhaba, başlayalım" yaz. Koç önce kaldığın yeri okur, sonra bugün ne yapacağını önerir.
4. Claude ilk seferlerde bir aracı kullanmak için izin sorar. **Always allow** (her zaman izin ver) dersen bir daha sormaz.

Koça doğrudan şunları söyleyebilirsin:

- "Sınavım 2027-03-21, günde 6 saat çalışabiliyorum."
- "Farmakoloji otonom çalıştım, 20 soruda 13 doğru."
- "Bu haftanın planını çıkar, pazar nöbetim var." (önce taslak gösterir, onaylarsan görevlere döker)
- "Yüklediğim soruyu birlikte çözelim, sonra not al."
- "Yapamadığım sorulardan bana soru hazırla."
- "Kalp yetmezliğini anlat, sonra 5 soru sor. Önemli yerleri not al."
- "Bana bu kadar uzun yazma." (kalıcı kural olarak kaydeder)
- "Bugünlük bu kadar." (oturumu kaydeder, yarın oradan devam eder)

## ChatGPT ile

ChatGPT'de özel MCP bağlayıcısı **ücretsiz planda yok**. Plus ve üstü planlarda **Developer mode** ile eklenir ve kurulum bilgisayar tarayıcısında yapılır. Kasım 2026 itibarıyla OpenAI'ın kendi belgeleri, bazı planlarda yalnız okuma yapan araçlara izin verildiğini söylüyor; o durumda koç not yazamaz ve oturum kaydedemez. Bu yüzden Claude öneriliyor.

Denemek istersen: chatgpt.com → **Settings** → **Apps & Connectors** → **Advanced settings** → **Developer mode** açık → **Create** → ad `TUS Koçu`, URL bağlayıcı adresi, kimlik doğrulama **OAuth**. Sonrası Claude'daki 6. adımla aynı.

## Sorun olursa

| Ne oldu | Ne yap |
| --- | --- |
| "Bağlantı isteği bulunamadı" sayfası | 15 dakikadan uzun beklenmiş. Claude'a dön, **Connect**'e yeniden bas. |
| "Davet kodu geçersiz" | Kodu boşluksuz yaz, olmazsa yeni kod iste. |
| Koç seni hatırlamıyor | Sohbette **+ → Connectors → TUS Koçu** açık mı bak. Açıksa "kaldığım yeri getir" yaz. |
| Şifreni unuttun | Kurulumu yapan kişiye söyle, sıfırlasın. |
