# Yayına alma

Sunucu tek bir Docker konteyneridir ve kalıcı bir diske (`/data`) ihtiyaç duyar. Notlar, veritabanı ve oturum belirteçleri o diskte durur; disk kaybolursa her şey kaybolur.

İki şart var:

1. **HTTPS adresi.** Claude ve ChatGPT bağlayıcıları yalnız HTTPS kabul eder.
2. **Tek kopya.** SQLite ve MCP oturumları tek sürece göre tasarlandı. Ölçeklemek gerekirse önce Postgres'e geçmek gerekir.

## Seçenek A: Railway (önerilen, telefondan da yapılabilir)

Railway GitHub reposundan otomatik derler, disk (volume) ve HTTPS adresi verir. Ücretli Hobby planı gerekir; güncel fiyatı railway.com/pricing sayfasından kontrol edin.

1. [railway.com](https://railway.com) → GitHub ile giriş → **New Project** → **Deploy from GitHub repo** → `hfgunay/coach-brain`.
2. Servisin **Settings** sekmesi:
   - **Root Directory**: boş bırakın (repo kökü). İmaj avenoxbeyin motorunu (`scripts/`, `template/`) da içerir.
   - **Config file**: `calisma-kocu/railway.json` (Dockerfile yolu `calisma-kocu/Dockerfile` orada yazılı)
3. Servise sağ tıklayın (telefonda uzun basın) → **Attach Volume** → mount path `/data`.
4. **Settings → Networking → Generate Domain**. Çıkan adresi kopyalayın, örn. `https://calisma-kocu-production.up.railway.app`.
5. **Variables** sekmesine ekleyin:

   | Değişken | Değer |
   | --- | --- |
   | `KOC_PUBLIC_URL` | 4. adımdaki adres, sonunda `/` olmadan |
   | `KOC_DATA_DIR` | `/data` |
   | `KOC_DAVET_KODLARI` | Uzun, tahmin edilemez bir kod (virgülle birden fazla) |
   | `RAILWAY_RUN_UID` | `0` (volume'a yazabilmek için; imaj normalde root olmayan kullanıcıyla çalışır) |

6. Yeniden dağıtım bitince tarayıcıda `<adres>/saglik` açın. `{"durum":"iyi"}` görmelisiniz.
7. Öğrenciye **bağlayıcı adresini** (`<adres>/mcp`) ve **davet kodunu** verin, sonra [Telefondan bağlama](TELEFONDAN_BAGLAMA.md) rehberini izleyin.

### Kendi alan adı (isteğe bağlı)

Örn. `koc.ornek.com`: Railway → Networking → Custom Domain, alan adı sağlayıcısında verilen CNAME kaydını açın, sonra `KOC_PUBLIC_URL` değerini yeni adresle değiştirin.

> Adres değişince OAuth bilgileri de değişir. Daha önce eklenmiş bağlayıcıyı silip yeni adresle yeniden eklemek gerekir. Alan adını kullanıcılar gelmeden önce bağlayın.

## Seçenek B: Kendi sunucunuz (VPS) ve Docker

```bash
git clone https://github.com/hfgunay/coach-brain && cd coach-brain
docker build -f calisma-kocu/Dockerfile -t calisma-kocu .   # repo kökünden: motor da imaja girer
docker run -d --name calisma-kocu --restart unless-stopped \
  -p 127.0.0.1:8000:8000 -v calisma-kocu-data:/data \
  -e KOC_PUBLIC_URL=https://koc.ornek.com \
  -e KOC_DAVET_KODLARI=uzun-rastgele-kod \
  calisma-kocu
```

Önüne HTTPS için Caddy koyun (`/etc/caddy/Caddyfile`):

```
koc.ornek.com {
    reverse_proxy 127.0.0.1:8000
}
```

## Yedekleme

Her şey `/data` altında: `calisma_kocu.sqlite3` (hesaplar, belirteçler), `vaults/` (kullanıcıların avenoxbeyin kasaları) ve `state/` (motorun yeniden kurulabilir indeksi). Asıl değerli olan `vaults/`. Haftada bir yedek alın:

```bash
sqlite3 /data/calisma_kocu.sqlite3 ".backup /data/yedek.sqlite3"
tar czf calisma-kocu-yedek-$(date +%F).tgz -C /data yedek.sqlite3 vaults
```

Railway'de volume'un **Backups** sekmesinden otomatik yedek de açılabilir. Öğrenci ayrıca Obsidian eşitlemesi açıksa notlarının bir kopyasını iPad'inde tutar.

## Yönetici işleri

Şifre sıfırlama (e-posta akışı yok):

```bash
python -c "
from calisma_kocu.db import DB, sifre_hashle; from pathlib import Path
db = DB(Path('/data/calisma_kocu.sqlite3'))
db.x('UPDATE users SET pw_hash=? WHERE email=?', (sifre_hashle('yeni-gecici-sifre'), 'ogrenci@ornek.com'))"
```

Bir kullanıcının tüm bağlantılarını kapatmak: `DELETE FROM oauth_tokens WHERE user_id = '<id>'`.

## avenoxbeyin güncellemesi

Kasalar ilk kullanımda imajdaki motorla kurulur. Yeniden dağıtımdan sonra yeni kullanıcılar yeni sürümü alır; mevcut kasaları yükseltmek için motorun kendi yolu kullanılır: kasa içinde `python3 beyin.py update` (bkz. kökteki SETUP-V3.md). Koç skill'i her istekte kontrol edilir, değiştiyse kasaya yeniden yazılır.
