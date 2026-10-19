# Pull request standardı

**Başlık:** `<tür>: <emir kipinde kısa cümle> (PE-123)`

- Türler commit standardındakilerle aynıdır: feat, fix, docs, style, refactor, perf, test, build, ci, chore, revert.
- Kırıcı değişiklikte tür sonuna `!` eklenir: `feat!: ...`.

**Gövde şablonu (GitHub'a bu haliyle konur, yorum satırları doldurulunca silinir):**

```markdown
<!-- Başlık: <tür>: <emir kipinde kısa cümle> (PE-123)
     Türler: feat, fix, docs, style, refactor, perf, test, build, ci, chore, revert
     Kırıcı değişiklikte tür sonuna ! ekle: feat!: ... -->

## Neden
<!-- Sorun ya da ihtiyaç, 1-2 cümle. -->

Closes #
Jira: PE-

## Ne değişti
-

## Nasıl test edildi
<!-- Komut ve sonuç yaz; "test ettim" yetmez. -->
- [ ] Lint ve tip kontrolü
- [ ] Testler:
- [ ] Elle doğrulama (ortam, adımlar, sonuç):

## Ekran görüntüsü
<!-- Yalnız arayüz değişikliğinde; önce / sonra. Değilse bu bölümü sil. -->

## Reviewer için
<!-- Nereye dikkat etsin, bilinçli tercihler, emin olmadığın yer. -->

## Risk ve geri alma
- Risk:
- Geri alma:
```

**Kurallar:**

- PR tek konuya odaklanır, konu dışı değişiklik ayrı PR olur.
- Test bölümüne komut ve sonuç yazılır, "test ettim" yetmez.
- Ekran görüntüsü bölümü arayüz değişikliği değilse silinir.
- Sır, müşteri verisi ve çalışan adı gövdeye yazılmaz.
- Gövde, okuyanın bağlamı bilmediği varsayımıyla yazılır, belirsiz sahiplik ifadesi yerine somut ad kullanılır.
