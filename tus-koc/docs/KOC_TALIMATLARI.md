# Koç talimatları

Koçun nasıl davranacağını anlatan metnin tek kaynağı [`tus_koc/talimatlar.md`](../tus_koc/talimatlar.md). Aynı metin üç yerde kullanılır:

1. **Claude Projesi talimatı**: öğrenci "TUS Koçu" projesini açarken bu dosyanın tamamını projenin **Instructions** alanına yapıştırır. En güçlü yöntem budur, çünkü her sohbetin başında okunur.
2. **MCP istemi**: sunucu bu metni `tus_kocu` adlı istem (prompt) olarak da sunar. Destekleyen istemcilerde menüden seçilebilir.
3. **Sunucu talimatı**: sunucu bağlanırken kısa bir özet gönderir (`server.py` içindeki `KISA_TALIMAT`). Proje kurulmasa da koç en azından kaldığı yeri okuyup oturumu kaydeder.

Metni değiştirirken:

- Araç adlarını (`kaldigim_yer`, `oturumu_kaydet` ...) koddaki adlarla aynı tut.
- Tıbbi doğruluk kuralını ("emin değilsen söyle, uydurma doz yazma") kaldırma.
- Değişiklikten sonra öğrencinin Claude Projesindeki metni de güncellemesi gerekir; sunucudaki dosya oraya kendiliğinden gitmez.
