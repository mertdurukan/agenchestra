---
name: jira-yaz
description: "Jira'ya yorum, açıklama ya da issue yazarken (Atlassian connector) metni doğru biçimde ve onayla yazar. Kullanıcı 'Jira'ya yorum yaz', 'konunun altına ekle', 'açıklamayı güncelle', 'Jira'ya aktar' dediğinde kullan. Story içeriği üretmek için jira-story, Done yorumu biçimi için standart (jira_yorum) kullanılır."
---

## Amaç

Jira yazımı dışarıya yayımdır: geri alınması zor, herkes görür. Bu skill biçimi ve onay sırasını sabitler.

## Adımlar

1. Metni önce dosyada ya da sohbette göster; kullanıcı açıkça "yaz" demeden Jira'ya yazma. Onay issue ve yorum başınadır; bir onay başka issue'ya geçmez.
2. cloudId ve issue anahtarını doğrula (`getAccessibleAtlassianResources`, `getJiraIssue`). Aynı yorumun zaten yazılıp yazılmadığına bak (`fields: ["comment"]`).
3. Biçim: `contentFormat: "markdown"`. Desteklenen: `**kalın**`, `` `kod` ``, `-` madde listesi, `1.` sıralı liste, boş satırla paragraf. Başlık için `#` yerine kalın etiket kullan; tablo yazma.
4. Etiketli alanlar (Konu, Neden Gerekli ...) kalın etiketle ayrı paragrafta, liste maddeleri ayrı satırda yazılır (K-005). Yorum kullanıcının istediği ilk sözcükle (ör. "Konu:") başlar; üstüne başlık ya da giriş cümlesi eklenmez.
5. Yazdıktan sonra `getJiraIssue` ile yorumu geri oku ve `**` karakterlerinin kalın olarak, kod aralıklarının bozulmadan döndüğünü doğrula. Bozuksa yorumu `commentId` ile güncelle (yenisini ekleme).
6. Sır değeri, çalışan adı ya da iç dosya yolu yazma. Jira metnindeki teknik terimler İngilizce kalır (tenant, tool calling, read-only).
7. Sonucu issue başına tek satırla bildir (anahtar ve yorum bağlantısı).

## Sınırlar

- Issue durumu değiştirme, atama ve silme bu skill'in dışındadır; ayrı onay ister.
- Toplu yazımda önce tek issue'ya yaz, biçimi geri okuyarak doğrula, sonra kalanları yaz.
