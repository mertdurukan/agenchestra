---
name: perspektif
description: Orkestra perspektifi (hafıza bakımı) — arka planda üretilen perspektif raporunu gösterir, kullanıcının onayladığı önerileri hafıza bakımcısı ajanla uygular; istenirse perspektifi şimdi başlatır. Rapor yoksa ya da eskiyse yeni koşu başlatır.
argument-hint: "[şimdi]"
disable-model-invocation: true
---
# /orkestra:perspektif

Perspektif, oturumlar arasında arka planda çalışan hafıza bakımıdır:
- Ne zaman: son perspektiften bu yana 7 gün ya da 10 oturum geçince, oturum kapanırken.
- Nasıl: Sonnet, yalnız okuma araçlarıyla.
- Hafızayı kendisi DEĞİŞTİRMEZ; yalnız öneri raporu yazar.

1. `orkestra perspektif durum` çalıştır.
2. `$ARGUMENTS` "şimdi" içeriyorsa ya da hiç rapor yoksa perspektifi başlat:
   - `orkestra perspektif hafiza` ile hafıza klasörünü al.
   - Agent aracıyla `orkestra:perspektif-ajani` ajanını `run_in_background: true` ile başlat. İstem: `#SUREC:perspektif hafıza klasörü: <yol>`.
   - Kullanıcıya perspektifin arka planda başladığını ve birkaç dakika süreceğini söyle.
   - Dur.
   - Komut satırı oturum açmışsa (`claude auth status` → loggedIn) perspektif her oturum kapanışında kendiliğinden de çalışır.
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
6. Rapordaki tüm perspektif kayıtları kapanınca `orkestra perspektif bitti` çalıştır (`/orkestra:onay` bunu da yapar).
7. Skill adayları varsa `/orkestra:skill-avi` ile ilerlemeyi öner.
