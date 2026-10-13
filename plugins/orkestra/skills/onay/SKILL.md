---
name: onay
description: Panelde onaylanan kararları uygular — perspektif (rüya) önerileri, skill taslakları ve ajanın sorduğu kararlar. Kullanıcı "panelde onayladıklarımı uygula", "onayları uygula", "bekleyen kararlar", "onaylananları işle" dediğinde ya da hook bağlamı "onaylanmış, uygulanmayı bekleyen karar" diye yönlendirdiğinde kullan.
disable-model-invocation: false
---
# /orkestra:onay

Kullanıcı kararları panelin Onaylar sayfasında (ya da sohbette) verir; bu skill onaylananları uygular. Hook bağlamı seni buraya yönlendirir.

Kural: `orkestra …` komutlarını tek başına çalıştır (zincir, boru ya da yönlendirme yok).

1. `orkestra onay liste --durum onaylandi` ile uygulanacakları al. Boşsa kullanıcıya "uygulanacak onaylı karar yok" de ve dur. Reddedilenlere dokunma.
2. Her kayıt için sırayla:
   1. Önce türe bak: başka oturumun `karar` kaydını (`oturum` alanı dolu ve bu oturum değil) `orkestra onay al` ÇALIŞTIRMADAN atla; yalnız soran oturum ya da oturumsuz karar alınır. Diğerleri için `orkestra onay al <id>` ile kaydı üstlen (başka oturum aldıysa hata verir; atla).
   2. Türüne göre uygula:
      - **perspektif**: `orkestra ruya hafiza` ile hafıza klasörünü al. Onaylı maddenin tam metnini (karar notu dahil) Agent aracıyla `orkestra:hafiza-bakimcisi` ajanına ver: hafıza klasörünün yolu + madde metni. Başlığı "Skill adayı" ile başlayan maddeler için hafıza değiştirme; `/orkestra:skill-avi` çalıştırmayı öner.
      - **skill**: `skills/skill-avi/SKILL.md` adım 3'teki akışı izle: taslağı `.claude/orkestra/onerilen_skill/<ad>/` → `.claude/skills/<ad>/` taşı (`GEREKCE.md` kalır), ayrı `orkestra:denetci` (`model: opus`) ile incelet, ret gelirse düzelt.
      - **karar**: kaydı soran oturum sensen (`oturum` alanı bu oturumun kimliği) kararı (`karar.secim`, `karar.not`) işine uygula; başka oturumunsa yalnız bilgilendir, uygulama.
      - **kural**: panelde zaten uygulanır; atla.
   3. `orkestra onay uygulandi <id> --ozet "<ne yapıldı, tek cümle>"`.
3. Rapordaki tüm perspektif kayıtları kapandıysa (`orkestra onay liste --tur perspektif` çıktısında bekliyor, onaylandi ya da uygulaniyor kalmadıysa) `orkestra ruya bitti` çalıştır.
4. Kullanıcıya kısa özet ver: uygulananlar, atlananlar ve nedeni.
