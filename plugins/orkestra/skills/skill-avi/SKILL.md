---
name: skill-avi
description: Tekrar eden işleri bul ve kayıtlı skill'e çevir — skill avcısı ajanı günlük, defter ve maliyet kayıtlarından aday çıkarır ve taslak yazar; kullanıcı onaylarsa taslak projenin .claude/skills/ klasörüne taşınır ve ayrı bir denetçi onu inceler.
argument-hint: "[gün sayısı, ör. 14]"
disable-model-invocation: true
---
# /orkestra:skill-avi

1. Agent aracıyla `orkestra:skill-avcisi` çalıştır. İstem:
   `#GOREV:- #SUREC:skill-avi` ve ardından "son $ARGUMENTS gün (boşsa 14) için skill adaylarını çıkar".
2. Dönen aday listesini kullanıcıya tablo olarak göster: ad, sıklık, basamak, tahmini tasarruf, taslak yolu.
3. Kullanıcı hangi adayları onaylarsa her biri için:
   1. Taslağı `.claude/orkestra/onerilen_skill/<ad>/` → `.claude/skills/<ad>/` klasörüne taşı. `GEREKCE.md` taşınmaz, olduğu yerde kalır.
   2. Ayrı bir `orkestra:denetci` çalıştır (`model: opus`). Denetçi skill'i şunlara göre incelesin:
      - `description` tetik cümlelerini kapsıyor mu;
      - adımlar uygulanabilir mi;
      - betik yolları gerçekten var mı;
      - sır ya da çalışan adı içeriyor mu.
   3. Ret gelirse taslağı düzelt ve yeniden denetlet.
4. Gömülü CLI ile yapıyı doğrula:
   `"$CLAUDE_CODE_EXECPATH" plugin validate .claude/skills/<ad>`
   Çalışmazsa frontmatter'ı elle kontrol et.
5. Kullanıcıya yeni skill'lerin adını ve nasıl tetiklendiğini söyle (`/<ad>` ya da doğal dil).
