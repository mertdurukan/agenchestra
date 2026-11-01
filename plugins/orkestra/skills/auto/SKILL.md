---
name: auto
description: "Orkestra'da /auto modunu açar: kullanıcının mesajı onay yerine geçer, üç belge (mevcut durum, plan, todo) yazılır, onay hook tarafından kendiliğinden verilir ve iş çalışma özetine kadar onaysız yürütülür. '/orkestra:auto <iş>', '/auto <iş>', 'onay almadan bitir', 'otomatik koş' dendiğinde kullan. Onay beklemek isteyen kullanıcı için /plan (varsayılan) vardır."
---

## Amaç

`/auto` modunda iş, kullanıcıdan ek onay beklemeden sonuna kadar yürür (ADR-0009, P-020). Bu skill komutu eklentide tanımlı tutar; modu yazan şey hook'tur.

## Mod nasıl açılır

- Kullanıcı mesajı `/auto` ya da `/orkestra:auto` ile başladığında UserPromptSubmit hook'u modu işe yazar ve bağlama "Orkestra: çalışma modu auto (ADR-0009)" satırını koyar.
- Bu satır bağlamda yoksa mod yazılmamıştır. Kullanıcıya tek cümleyle `/auto <iş>` yazmasını söyle ve işe başlama.
- Mod ve onay alanlarını sen yazmazsın: `is.json` düzenlenmez, `orkestra is onayla` çalıştırılmaz (ajan kendi onayını veremez, ADR-0002).

## Akış

1. İşi `orkestra:is` skill'iyle aç ya da bağlı işe devam et.
2. Üç belgeyi sırayla yaz: mevcut durum, plan, todo. Belgeler tamamlanınca hook onayı `verildi` yapar (olay `onay:auto`).
3. Planı sonuna kadar uygula. Her madde için kanıt notu yaz, işçi çıktısını ayrı denetçiden geçir.
4. İşi `orkestra is kapat` ile kapat; çalışma özeti "Plandan sapmalar", "Otomatik kararlar" ve "Kullanıcıya kalanlar" bölümlerini taşır.

## Tam otonomi ve best in class (ADR-0132)

`/auto` işi kullanıcıya dönmeden çalışma özetine kadar sürer; araya durma, onay ya da "devam edeyim mi" yoktur.

- **Best in class:** her konuda, plan maddesi başına şu dört soru yanıtlanır (P-030): kök neden mi ele alınıyor, en az iki uygulanabilir alternatif tartıldı mı, kapsam daraltılırken çözümün özü korundu mu, ölçüm yöntemi yeterli mi. Belirtiyi yamayan ya da tek yaklaşımı deneyen çözüm best in class sayılmaz.
- **Durmama:** tur bir konuda tıkansa da diğer maddeler sürer; iş çalışma özeti yazılıp `orkestra is kapat` çalışana kadar bırakılmaz.
- **Kullanıcıya kalan iş:** önce kendin çöz. Elinde araç, anahtar, API ya da tarayıcı varsa işi yap. Çözemediğin işte best in class güvenli varsayılanı seç, uygula ve kararı yaz. Yanıt gövdesinde karar bölümü ('Sana kalan', 'Karar', 'Seçim', 'Onay bekleyen') yazma; değeri yalnız kullanıcıda olan engel yanıtın SON bölümü 'Kullanıcıya kalanlar'a girer ve her maddesi 'Denendi: <ne denendi, sonuç>' taşır (ADR-0137); denemediğin işi madde yapma, yap.
- **Her otomatik karar** özetin `## Otomatik kararlar` bölümüne dört alanla yazılır:
  - **Karar:** ne yapıldı ya da ne yanıt verildi.
  - **Gerekçe:** neden bu, hangi kanıta dayanıyor.
  - **Alternatifler:** değerlendirilen diğer yollar.
  - **Geri alma:** kararı geri almanın yolu.
- **Çözülemeyenler:** parola girişi, değeri yalnız kullanıcıda olan sır ve hesap açma otomatik çözülmez (kesin sınır). Bunlar "Kullanıcıya kalanlar" altında, ne yapıldığı ve uygulanan güvenli varsayılanla birlikte sıralanır; koşu durmaz.

## Sınırlar

`/auto` aşağıdakileri gevşetmez; hepsi aynen geçerlidir:

- Zorla, silme ve ayna push ile kalıcı silme (`gh ... delete`, Atlassian `executeDestructive`) reddedilir.
- Sır değeri hiçbir çıktıya girmez; kimlik klasörü okuma kapısı kapalı kalır.
- Veritabanı salt okunurdur.
- İzin hook'unun `deny` sınıfı, denetçi, ADR, gap ve kanıt kapıları çalışır.

## Yetki ve soru yasağı (ADR-0086)

- `/auto` mesajı Jira ve GitHub dahil kapsamdaki her eylem için açık yetkidir: `git push`, `gh` yazma, GitHub/Jira REST ve MCP yazma çağrıları sorulmadan çalışır (`ask` → `allow`, yalnız bağlı işin modu `auto` iken).
- Kullanıcıya soru sorulmaz: `AskUserQuestion` ve `ask` alanı dolu `wrap_up` reddedilir. Yanıt metninde de soru sorma ("…mı kastettin?", "hangisini istersin?" yazılmaz). Kararı en iyi uygulamayla kendin ver, çalışma özetinin "Otomatik kararlar" bölümüne yaz.
- Mod okunamazsa `plan` davranışı geçerlidir. `ORKESTRA_AUTO_YETKI=0` bu yetkiyi kapatır.

Değeri yalnız kullanıcıda olan işler (parola, hesap açma, başka ekibin işi) koşuyu durdurmaz. Diğer maddeler tamamlanır, bunlar çalışma özetinde "Kullanıcıya kalanlar" altında, ne yapıldığı ve uygulanan güvenli varsayılanla birlikte yazılır.
