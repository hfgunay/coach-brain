# Koç talimatları

Koçluk davranışının tek kaynağı [`tus_koc/skill/SKILL.md`](../tus_koc/skill/SKILL.md). Bu bir avenoxbeyin skill'idir: yeni mekanizma eklemez, kasadaki AGENTS.md ve beyin skill'inin hafıza protokolünü TUS çalışmasına uygular (tanışma, öncelik, görev olarak plan, yapamadığı soruların notu ve `review_at`).

Koça üç yoldan ulaşır:

1. **Kasada**: sunucu her kasaya `.agents/skills/tus-koc/SKILL.md` olarak koyar ve dosya değişince günceller. Koç `talimatlari_oku` ile AGENTS.md, beyin skill'i ve bu skill'i okur.
2. **Sunucu talimatı**: bağlanınca giden kısa metin (`server.py` içindeki `TALIMAT`): "ilk iş `kaldigim_yer`, protokolü bilmiyorsan `talimatlari_oku`".
3. **MCP istemi**: `tus_kocu` aynı metni verir.

Claude Projesine metin yapıştırmak gerekmez; projenin talimatına "Her sohbette önce kaldigim_yer, sonra talimatlari_oku" yazmak yeter.

Metni değiştirirken:

- Araç adlarını koddakilerle aynı tut ve beyin komutlarıyla eşleşme tablosunu koru.
- Repoda zaten olan bir şey için yeni yapı tarif etme (ayrı hata defteri, ayrı plan dosyası gibi). Önce motor ne sağlıyor bak.
- Tıbbi doğruluk kuralını kaldırma.
