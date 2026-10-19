---
name: standart
description: "Ekip yapı standartlarını (PR başlığı ve gövdesi, commit mesajı, Conventional Commits türleri, dal adı, review kuralı, Jira Done yorumu) okutur ve uyulmasını sağlar. Kullanıcı pull request ya da PR açıp yazdığında veya incelediğinde, commit mesajı yazdığında, dal adlandırdığında, Jira görevine Done yorumu yazdığında, 'standart', 'şablon', 'commit türü', 'PR gövdesi', 'review kuralı' dediğinde ya da yeni bir yapı standardı eklemek istediğinde kullan. Standart yazmayan, yalnız kod değiştiren işlerde kullanma."
---

## Amaç

Standartlar bağlamı şişirmemek için kural olarak değil dosya olarak tutulur (ADR-0006). Bu skill yalnız ilgili standardı okutur ve çıktının ona uymasını sağlar.

## Adımlar

1. `orkestra standart liste` ile kayıtlı standartlara bak (proje dosyası eklenti kalıbını ezer).
2. İşe uyan standardı oku: `orkestra standart goster <ad>`.
   - PR açma/inceleme: `pr`, `commit`, `review`.
   - Commit mesajı: `commit`.
   - Dal açma: `dal`.
   - Jira Done yorumu: `jira_yorum`.
3. Yazarken: çıktıyı standardın biçimine göre kur; boş bölüme "Yok" yaz.
4. İncelerken: çıktıyı standartla madde madde karşılaştır, sapmaları `blocker:` ya da `öneri:` etiketiyle bildir.
5. Dış sisteme yazma (PR açma, Jira yorumu, push) kullanıcı onayı olmadan yapılmaz; metni önce göster.

## Yeni standart

Kullanıcı yeni bir yapı isterse `orkestra standart ekle <ad>` projede boş kalıp açar; içeriği kullanıcıyla doldur. Standart kayıtları kural değildir: davranış emri gerekiyorsa `orkestra kural ekle` kullan.

## Sınır

Otomatik commit iletileri (`Otomatik commit: <dosya>`) muaftır; push öncesi birleştirilen commit standarda uyar.
