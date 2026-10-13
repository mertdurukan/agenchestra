---
name: ruya
description: Orkestra rüyası (hafıza bakımı) — arka planda üretilen rüya raporunu gösterir, kullanıcının onayladığı önerileri hafıza bakımcısı ajanla uygular; istenirse rüyayı şimdi başlatır. Rapor yoksa ya da eskiyse yeni koşu başlatır.
argument-hint: "[şimdi]"
disable-model-invocation: true
---
# /orkestra:ruya

Rüya, oturumlar arasında arka planda çalışan hafıza bakımıdır:
- Ne zaman: son rüyadan bu yana 7 gün ya da 10 oturum geçince, oturum kapanırken.
- Nasıl: Sonnet, yalnız okuma araçlarıyla.
- Hafızayı kendisi DEĞİŞTİRMEZ; yalnız öneri raporu yazar.

1. `orkestra ruya durum` çalıştır.
2. `$ARGUMENTS` "şimdi" içeriyorsa ya da hiç rapor yoksa rüyayı başlat:
   - `orkestra ruya hafiza` ile hafıza klasörünü al.
   - Agent aracıyla `orkestra:ruya-ajani` ajanını `run_in_background: true` ile başlat. İstem: `#SUREC:ruya hafıza klasörü: <yol>`.
   - Kullanıcıya rüyanın arka planda başladığını ve birkaç dakika süreceğini söyle.
   - Dur.
   - Komut satırı oturum açmışsa (`claude auth status` → loggedIn) rüya her oturum kapanışında kendiliğinden de çalışır.
3. `son_rapor` dosyasını oku ve kullanıcıya bölüm bölüm kısa özet ver:
   - birleştirilecek kopyalar;
   - çelişkiler;
   - eskimiş kayıtlar;
   - boyut;
   - skill adayları.
4. Panel kararlarını al: `orkestra onay liste --tur perspektif`.
   - Panelde karar verilmiş (onaylandi, reddedildi, uygulandi) maddeleri kullanıcıya yeniden sorma.
   - Bekleyen maddeler için kullanıcıya iki yol öner: panelin Onaylar sayfası (`orkestra panel` ile açılır) ya da sohbette numara vererek onay.
   - Sohbette verilen onay ya da ret'i `orkestra onay karar <id> --onay` / `--ret` (gerekirse `--not "..."`) ile kaydet; panel de görsün. Varsayılan "hiçbiri" kabul edilir: onaysız hiçbir hafıza değişmez.
5. Onaylananları `/orkestra:onay` akışıyla uygula (hafıza bakımcısı ajanı ve `orkestra onay uygulandi` orada).
6. Rapordaki tüm perspektif kayıtları kapanınca `orkestra ruya bitti` çalıştır (`/orkestra:onay` bunu da yapar).
7. Skill adayları varsa `/orkestra:skill-avi` ile ilerlemeyi öner.
