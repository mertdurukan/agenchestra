# {baslik}: çalışma özeti ({tarih})

<!-- başlık: Jira kodu varsa "KOD Jira başlığı" (Jira'dan çekilen başlık); Jira'dan çekilmiyorsa görevin ne yaptığını anlatan en kısa başlık. Yalnız kod ("PE-635") ya da genel ifade yazma; yukarıdaki {baslik} yerini bu başlıkla değiştir. -->

<!-- iki katman (ADR-0085, ADR-0091): `## Özet` yalnız kısa Şef Özeti'dir (gövde ≤ 1200 karakter); yöntem listesi, katman ayrıntısı, sayı tablosu ve kanıt ona girmez, hemen altındaki `## Harita`ya yazılır. Bu özet tek kaynaktır: yönetici anlatısı (`orkestra is anlati`) ve Jira Done yorumu (`orkestra is jira-yorum`) buradaki alanlardan türetilir, ayrıca yazılmaz. -->

## Özet

***Şef Özeti***

**Durum:**

<!-- doldur: ilk sözcük Tamam, Kısmen ya da Engelli; ardından tek cümle neden. Sonuç önce okunur; aşağıdaki alanlar bununla tutarlı olur. -->

**Amaç neydi?**

<!-- doldur: tek cümle; istenen sonucun kendisi, mümkünse kullanıcının sözüyle. Yöntem ya da gerekçe yazma. -->

**Ne yapıldı?**

<!-- doldur: en çok 3 madde, her biri ayrı satırda ve fiille başlar, en çok ~150 karakter. Her maddeye etiket koy: [Doğrulandı] (kanıtla sınandı), [Tamamlandı] (yapıldı, sınanmadı) ya da [Planlandı] (yapılmadı). Somut ad ve sayı ver; yöntem ve katman ayrıntısı `## Harita`ya. -->

- 

**Nasıl karar verildi?**

<!-- doldur: en çok 2 cümle; neyi kanıtlayıp eledik, neden bu yol, kontrolün sınırı. Ayrıntı `## Harita`daki Denenenler ve Kararlar'da. -->

**Ana sayı:**

<!-- doldur: tek sayı + komut + ölçüm saati; yoksa "Yok". -->

**Senden beklenen:**

<!-- doldur: kullanıcıdan gereken tek karar ya da onay; yoksa "Yok". -->

**Açık kalanlar:**

<!-- doldur: yapılmayan ya da doğrulanamayan her iş tek satır ve nedeniyle; kullanıcıdan karar ya da onay gerekiyorsa tek cümleyle burada; ayrıntı `## Harita`daki "Açık işlerin ayrıntısı"nda; yoksa "Yok". -->

- 

## Harita

<!-- harita (ADR-0085): kapsamlı katman. Denenenler, Doğrulanmayanlar ve Kararlar zorunludur (kapı bunları sınar); diğer alanlar işe göre. -->

**Ölçüm saati:**

{tarih} {saat} (yerel). Her sayının yanına komutu ve ölçüm saatini yaz.

**Denenenler:**

<!-- doldur: neyi hangi yöntemle denedik; satır başına bir yöntem ya da yöntem ailesi. Sütunlar: katman ya da bileşen, yöntem, sonuç (işe yaradı | kısmen | yaramadı | ölçülmedi), kanıt (dosya:satır, komut ya da sayı). Boş satırı doldur, gerekirse satır ekle. -->

| Katman ya da bileşen | Yöntem | Sonuç | Kanıt |
| --- | --- | --- | --- |
| | | | |

**Sayılar:**

<!-- doldur: komutla ölçülen her sayı ayrı satır: komut → sayı (ölçüm saati). Sayı belgenin başka yerinde de geçiyorsa aynı olur (K-002). -->

- 

**Doğrulanmayanlar:**

<!-- doldur: denenmeyen ya da ölçülemeyen her şey ayrı satır ve nedeniyle (erişim, süre, kapsam dışı); yoksa "Yok". -->

- 

**Kararlar:**

<!-- doldur: alınan karar ve bilerek kapsam dışı bırakılan her şey ayrı satır; neden ve ADR ya da kimlik ile; yoksa "Yok". -->

- 

**Açık işlerin ayrıntısı:**

<!-- doldur: `Açık kalanlar`daki her iş için neden bekliyor, kimde ve sonraki adım; yoksa "Yok". -->

- 

**İlgili dosyalar:**

- 

## Plana göre gerçekleşen

<!-- doldur: plandaki her P ve mevcut durum §6'daki her G ayrı satır; her satır en çok 300 karakter (biçim kapısı daha uzununu reddeder), ayrıntıyı bölüm altına ayrı paragraf yaz.
- P1: yapıldı | kısmen | yapılmadı. Kanıt: komut çıktısı ya da dosya:satır.
- G1: kapandı | açık. Hangi P ile kapandığı.
Planın dışına çıkılan işler ve kalan işler de ayrı satırlarla yazılır. -->

## Paralellik sapması

<!-- yalnız kapanış kapısı isterse doldurulur (ADR-0080; `paralel: true` iş, kartlar yüklenmedi ya da gerçekleşen ÷ planlanan < 0,5): planlanan, gerçekleşen (`orkestra is rapor <iş>`, ortalama eşzamanlı iş sayısı) ve neden; en az 40 karakter. Gerekmiyorsa boş bırak. -->

## Plandan sapmalar

<!-- yalnız /auto işlerinde zorunlu (ADR-0009): koşu sırasında plandan ayrılan her karar ayrı satır; yoksa "Yok". -->

## Otomatik kararlar

<!-- yalnız /auto işlerinde (ADR-0086): kullanıcıya sorulmadan verilen her karar ayrı satır: karar, seçilen, elenen, neden; yoksa "Yok". -->

## Kullanıcıya kalanlar

<!-- yalnız /auto işlerinde zorunlu (ADR-0009): yalnız kullanıcının yapabileceği işler, sıralı ve uygulanabilir; yoksa "Yok". -->
