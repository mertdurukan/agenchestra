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
4. Önerilen değişiklikleri numaralı liste olarak sun. Kullanıcıya hangilerinin uygulanacağını sor. Varsayılan "hiçbiri" kabul edilir: onaysız hiçbir hafıza değişmez.
5. Onaylananları Agent aracıyla `orkestra:hafiza-bakimcisi` ajanına ver. Ajana şunları ilet:
   - hafıza klasörünün yolu (`~/.claude/projects/<proje>/memory/`);
   - onaylı maddelerin tam metni.
6. Sonra `orkestra perspektif bitti` çalıştır.
7. Skill adayları varsa `/orkestra:skill-avi` ile ilerlemeyi öner.
