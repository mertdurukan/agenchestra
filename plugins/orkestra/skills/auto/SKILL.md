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
4. İşi `orkestra is kapat` ile kapat; çalışma özeti "Plandan sapmalar" ve "Kullanıcıya kalanlar" bölümlerini taşır.

## Sınırlar

`/auto` aşağıdakileri gevşetmez; hepsi aynen geçerlidir:

- Push yalnız kullanıcının açık isteğiyle yapılır.
- Sır değeri hiçbir çıktıya girmez.
- Veritabanı salt okunurdur.
- İzin hook'u, denetçi, ADR, gap ve kanıt kapıları çalışır.

Kullanıcıya ait işler (parola, push kararı, başka ekibin işi) koşuyu durdurmaz. Diğer maddeler tamamlanır, bunlar çalışma özetinde "Kullanıcıya kalanlar" altında sıralanır.
