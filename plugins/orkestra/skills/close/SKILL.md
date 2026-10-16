---
name: close
description: >-
  Sohbet bitmeden önce çalışır: bu sohbette kullanıcının istediği her şeyi kanıta bakarak sınar ve AÇIK
  KALAN İŞLERİ sohbette madde madde verir; her madde tek cümleyle "bu iş şu nedenle yapılmalı" der.
  Kapalı işler sohbete girmez, yalnız rapor dosyasında durur. Hiçbir kullanıcı mesajı atlanmaz (betik sayar).
  Kullanıcı "/orkestra:close", "sohbeti kapatıyorum", "ne açıkta kaldı", "yapılmayanlar neler",
  "açık işler", "kapanış kontrolü" dediğinde kullan.
argument-hint: "[konu filtresi, isteğe bağlı]"
---
# /orkestra:close: sohbet → kanıtlı karar → sohbette "açık iş — neden" listesi

**Amaç:** Sohbet kapanmadan, açıkta kalan her işi ve onun neden yapılması gerektiğini kullanıcıya göstermek. Asıl çıktı sohbetteki listedir; rapor dosyası onun kanıtıdır. Yeni iş başlatmaz.

**Kapsam:** Yalnız bu sohbet. Kullanıcının istekleri, soruları ve kararları; asistanın sunup cevaplanmayan önerileri de girer (KARAR BEKLİYOR). Başka oturumlar ve orkestra defteri kapsam dışıdır.

**Yöntem ilkesi:** Sayma, numaralama, biçim ve kapsam denetimi betiktedir; yapıldı/açık kararı kanıta bakan modeldedir. Model kendi belleğinden karar vermez.

## Çıktı sözleşmesi (bu skill'in tek ölçütü)
Sohbetteki teslim şudur ve başka bir şey değildir:

```
Açık kalan işler (N):

- **<yapılacak iş>** — <bu iş neden yapılmalı: tek cümle>.
- **Karar sizde: <karar>** — <karar verilmezse ne bekler: tek cümle>.

açık işler: <rapor bağlantısı>
```

- Madde sayısı sınırsızdır; her açık iş görünür. Kapalı iş, sayım ve konu özeti sohbete girmez.
- Liste `liste` komutunun çıktısıdır; model aynen aktarır, yeniden yazmaz, kısaltmaz. Neden cümlesi raporda yazılır, sohbette sonradan uydurulmaz.
- Açık iş yoksa tek satır: `Açık iş yok: <N> isteğin hepsi kapandı.` (komut bunu basar.)
- Bu skill'in teslimi P-001'in "en çok 5 madde" sınırından muaftır: liste kullanıcının açıkça istediği çıktıdır; ayrıntı yine raporda kalır.

## Madde nasıl yazılır
- **İş:** Somut ve eylemle biter; dosya yolu, ad ya da adres içerir ("`C:/ork_tmp_p11` silinmeli"). "Bakılmalı", "gözden geçirilmeli" tek başına yetmez; neye bakılacağı yazılır. Kullanıcıya ait işler (elle silme, push kararı) da listededir; sahibi cümleden anlaşılır.
- **Neden:** Tek cümle, tek ölçüt: yapılmazsa ne olur ya da neye bağlıdır. Kaynağı sohbettir (kullanıcının sözü, bir hata, bir bağımlılık); uydurulmaz.
  - İyi: "Desktop `main` uzak depoya gitmedikçe CI tanımı ve I-026 yalnız bu bilgisayarda kalır."
  - Kötü: "Önemli olduğu için." / "Eksik kaldığı için." (durum tekrarıdır; betik reddeder.)
- **Karar maddesi:** `KARAR BEKLİYOR` etiketi listede "Karar sizde:" öneki alır; neden, kararın bekleyen şeyi neye bağladığını söyler.
- **Eleme:** Sohbette istenmemiş iş eklenmez; kullanıcının sözü yorumla büyütülmez; kullanıcı vazgeçtiyse (ELENDİ) listeye girmez.

## Adımlar
1. **Kaydı sıkıştır (betik).** Oturum kimliği `${CLAUDE_SESSION_ID}`; boşsa scratchpad yolundaki oturum klasörü adı kullanılır.
   ```
   python -I "${CLAUDE_SKILL_DIR}/scripts/sohbet_cikar.py" cikar --oturum <id> --cikti <rapor klasörü>/girdi.json
   ```
   - Her kullanıcı mesajına `U1, U2…` kimliği verir; tur sürerken gönderilenler dahil. Argümansız slash komutları, skill gövdesi ve meta mesajlar elenir.
   - Her mesajın altına o aradaki yapılanları koyar: değişen dosyalar, komut açıklamaları, hatalar, başlatılan oturumlar, asistanın son cümlesi.
   - `dosyalar_yok`: yazılan ama şimdi diskte olmayan dosyalar (varlık kontrolü betikte). `eylem_yok: true`: salt soru-cevap turu (CEVAPLANDI adayı).
   - **Açık adayları** buradan başla: `plan_son_durum` içinde tamamlanmayan maddeler; `cevapsiz_soru` (asistanın son turdaki cevapsız sorusu); `dosyalar_yok`; `hatalar`. Her aday ya açık iş olur ya da kapalı olduğuna dair kanıt yazılır.
2. **Konulara grupla (model).** Konu = tek amaç. Dağınık mesajlar birleşir; belirsizse ayrı konu. Her konuya kısa ad ve `U` kimlikleri yazılır. Hook/oturum açılış bağlamı kullanıcı isteği değildir.
3. **Her istek için karar ver.** Etiketler:
   - **YAPILDI:** kanıt zorunlu. **CEVAPLANDI:** bilgi sorusu, cevabın yeri kanıt. **ELENDİ:** kullanıcı vazgeçti, mesaj kanıt.
   - **KISMEN:** bir kısmı yapıldı; iş cümlesi kalan kısmı söyler.
   - **YAPILMADI:** istendi, başlanmadı ya da denendi ve olmadı.
   - **KARAR BEKLİYOR:** kullanıcının cevabı ya da onayı gerekiyor (asistanın cevaplanmayan sorusu dahil).
4. **Kanıtı kaynağında doğrula (en ucuz yoldan).**
   - Kanıt: `girdi.json`'daki dosya/komut kaydı, kullanıcının sonraki mesajındaki açık onay, ya da dosya:satır / komut çıktısı. Asistanın "yaptım" demesi tek başına kanıt değildir.
   - Dosya varlığı `dosyalar_yok` alanında hazırdır; Glob/`ls`/`Test-Path` ile yeniden bakma. `dosyalar_yok` doluysa YAPILDI yazma.
   - Eklenti, hafıza ya da başka klasörleri tarama. Doğrulayamazsan KISMEN yaz ve neden cümlesine "teyit edilemedi" bilgisini koy; tahminle YAPILDI yazma.
5. **Raporu yaz, denetle, listeyi üret.** Yer ve biçim aşağıda.
   ```
   python -I "${CLAUDE_SKILL_DIR}/scripts/sohbet_cikar.py" denetle <rapor.md> --girdi <girdi.json>
   python -I "${CLAUDE_SKILL_DIR}/scripts/sohbet_cikar.py" liste <rapor.md>
   ```
   `denetle`: her kullanıcı mesajı raporda var mı; etiket ve satır biçimi geçerli mi; YAPILDI/ELENDİ/CEVAPLANDI satırında `Kanıt:`, açık satırda `Kanıt:` ve `Neden:` var mı; Neden tek ve kısa cümle mi, durum tekrarı değil mi; sayım maddelerle birebir mi; YAPILDI yolları var mı; yer tutucu ve e-posta. `KALDI` ise raporu düzeltip yeniden çalıştır; GEÇTİ olmadan `liste` çalıştırma.
6. **Sohbette teslim.** `liste` çıktısını aynen yaz, altına `açık işler: <bağlantı>` satırı ekle (K-003). Teslimden sonra dur: hafıza, ayar, eklenti ya da başka dosya yazılmaz; sıradaki adım tekrarlanmaz.
7. **Todo'ya işleme yalnız kullanıcı "evet" derse.** Sohbet bir işe bağlıysa açık maddeler `orkestra is todo <id> --ekle` ile işin `todo.md` dosyasına eklenir; ayrı todo dosyası açılmaz. Evet gelmeden hiçbir iş başlatılmaz.

## Satır ekonomisi (hız kuralı)
Çıktı süresi satır sayısıyla doğrusal artar; zaman açık işlere harcanır.
- **Açık etiketler (KISMEN, YAPILMADI, KARAR BEKLİYOR):** her istek için ayrı tam satır, `Kanıt:` ve `Neden:` ile.
- **Kapalı etiketler (YAPILDI, CEVAPLANDI, ELENDİ):** konu başına, etiket başına tek aralık satırı: `- [CEVAPLANDI] U1–U4: <konular tek cümlede> | Kanıt: <en güçlü tek kanıt>`.
- **Atlanmaz:** her kullanıcı mesajı bir satırın kimlik kümesinde yer alır.
- **Düşünme payı:** `eylem_yok` mesajlar asistanın açık sorusu ya da önerisi içermiyorsa doğrudan CEVAPLANDI aralığına girer.

## Rapor yeri ve biçimi
- **Yer:** Sohbet bir işe bağlıysa işin klasörü: `<iş klasörü>/acik_isler_<YYYYMMDD>.md`. Bağlı iş yoksa projenin kendi çıktı kuralındaki yer (CLAUDE.md ya da `.claude/rules`); kural yoksa `.claude/orkestra/acik_isler/acik_isler_<YYYYMMDD>.md`. `girdi.json` aynı klasöre gider. Var olan dosyanın üstüne yazılmaz; aynı gün ikinci koşuda `_2` eklenir.
- **Okunabilirlik:** Başlık ve etiketli alanlar ayrı paragraflarda, etiket kalın; her madde ayrı satırda.
- **Terimler kesin yazılır:** "kendi/bizim/şu sunucu" yerine dosya yolu, ad ya da adres. Sır değeri, e-posta ve projenin gizlilik kuralının yasakladığı adlar (ör. çalışan adı) yazılmaz.

İskelet:

```
# Açık işler — <sohbet başlığı> — <YYYY-MM-DD HH:MM>

**Sohbet:** <oturum kimliği> · <N> kullanıcı mesajı · <ilk saat>–<son saat>

**Kapsam:** Yalnız bu sohbet; <varsa konu filtresi>.

## Sayım
- YAPILDI: a
- KISMEN: b
- YAPILMADI: c
- KARAR BEKLİYOR: d
- ELENDİ: e
- CEVAPLANDI: f

## Konu 1 — <kısa ad>

**Mesajlar:** U1, U3

**Durum:** <açık kaç madde var: tek cümle>

- [CEVAPLANDI] U1–U2: <sorular tek cümlede> | Kanıt: <yanıtın yeri>
- [YAPILDI] U4: <istek> | Kanıt: `<dosya yolu>` ya da <kısa kanıt>
- [KISMEN] U3: <kalan iş, eylemle biten cümle> | Kanıt: <yapılan kısım> | Neden: <neden yapılmalı, tek cümle>
- [KARAR BEKLİYOR] U5: <verilecek karar> | Kanıt: <neden açık> | Neden: <karar neyi bekletiyor, tek cümle>
```

Madde satırı kuralı: `- [ETİKET] U3: iş | Kanıt: … | Neden: …`. Birden çok mesaj için `U1, U4` ya da `U2–U5`. Sayımı önce maddeleri yazıp sonra say.

## Kabul kriterleri
- `denetle` GEÇTİ; `liste` çıktısı sohbette aynen var.
- Her açık iş eylemle biten tek cümledir ve tek cümlelik `Neden:` taşır; neden sohbetten türetilmiştir.
- Her YAPILDI maddesi doğrulanabilir kanıta dayanır; kapalı iş sohbet listesine girmemiştir.
- `plan_son_durum` açıkları ve `cevapsiz_soru` ya açık işte ya kanıtlı kapalı satırdadır.
- Hiçbir açık iş başlatılmadı; rapor dışında dosya yazılmadı.

## Yasaklar
- Kanıtsız YAPILDI; asistanın kendi beyanı kanıt sayılmaz.
- Açık işleri kendi başına yapmak, yeni iş açmak, kapsamı sohbet dışına genişletmek.
- Sohbette olmayan madde eklemek; kullanıcının sözünü yorumlayarak büyütmek.
- Listeyi sohbette yeniden yazmak ya da neden cümlesini sohbette değiştirmek (önce rapor düzeltilir, `liste` yeniden çalışır).
- Sır değeri ya da e-posta yazmak; ayrı todo/plan dosyası açmak.
