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
      - **perspektif**: `orkestra perspektif hafiza` ile hafıza klasörünü al. Onaylı maddenin tam metnini (karar notu dahil) Agent aracıyla `orkestra:hafiza-bakimcisi` ajanına ver: hafıza klasörünün yolu + madde metni. Başlığı "Skill adayı" ile başlayan maddeler için hafıza değiştirme; `/orkestra:skill-avi` çalıştırmayı öner.
      - **skill**: `skills/skill-avi/SKILL.md` adım 3'teki akışı izle: taslağı `.claude/orkestra/onerilen_skill/<ad>/` → `.claude/skills/<ad>/` taşı (`GEREKCE.md` kalır), ayrı `orkestra:denetci` (`model: opus`) ile incelet, ret gelirse düzelt.
      - **karar**: kaydı soran oturum sensen (`oturum` alanı bu oturumun kimliği) kararı (`karar.secim`, `karar.not`) işine uygula; başka oturumunsa yalnız bilgilendir, uygulama.
      - **kural**: panelde zaten uygulanır; atla.
   3. `orkestra onay uygulandi <id> --ozet "<ne yapıldı, tek cümle>"`.
3. Rapordaki tüm perspektif kayıtları kapandıysa (`orkestra onay liste --tur perspektif` çıktısında bekliyor, onaylandi ya da uygulaniyor kalmadıysa) `orkestra perspektif bitti` çalıştır.
4. Kullanıcıya kısa özet ver: uygulananlar, atlananlar ve nedeni.

## Etki ölçümü (vaadi olan kayıtlar)
Perspektif maddelerinde `Vaat:` satırı (ölçü, yön, kapsam) vardır. Uygulama sırası: taban -> uygula -> doğrula -> günlük izleme.

1. **Vaat:** Kayıtta vaat yoksa `orkestra onay vaat <id> …` ile maddedeki `Vaat:` satırından yaz (ölçü, yön, kapsam; eşik varsayılanı göreli %10, birikimde en az 20 örnek). Madde `ölçü=ölçülemez` diyorsa öyle kaydet.
2. **Taban:** `orkestra onay al <id>` taban değerini otomatik alır ve dondurur. Ayrıca elle taban alma.
3. **Uygula:** Yukarıdaki adım 2.2'deki gibi (hafıza-bakımcısı vb.).
4. **Doğrula:** `orkestra onay uygulandi <id> --ozet "…"` uygulama doğrulamasını yapar (değişiklik yerinde mi: yol var/yok, satır, bayt). Bu "uygulandı mı" sorusudur, "işe yaradı mı" değildir.
5. **Günlük izleme:** Uygulama gününden başlar, sabit süre ya da pencere yoktur. `orkestra onay etki-izle` eksik günleri doldurur (idempotent; oturum açılışında ve panel yüklenirken zaten çağrılır, elle de çalıştırılabilir). `orkestra onay etki-liste` gidişatları gösterir (iyi / kötü / etkisiz / yetersiz-veri / ölçülemez).
6. **Kapatma:** `orkestra onay etki-kapat <id> --sonuc dogru-karar|yanlis-karar|belirsiz` yalnız kullanıcı karar verince çalıştırılır; kapatılana (ya da geri alınana) dek izleme sürer. Gidişat 3 gün üst üste `kotu` ise kullanıcıya tek soru sor: geri al / sürdür. Kendiliğinden geri alma ve kendiliğinden kapatma yok; doğru/yanlış kararı kullanıcınındır.

Kurallar:
- **Sahte metrik YASAK:** Vaadi olmayan ya da ölçülemeyen kayda metrik uydurma. `ölçülemez` yaz; "iyi" ya da "başarılı" diye damgalama.
- Etki günlüğü yalnız sona eklenir; elle düzenleme.
- Aynı günlerde başka değişiklikler uygulandıysa sonucu "karışık" diye belirt.
