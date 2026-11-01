# {baslik}: çalışma özeti ({tarih})

<!-- başlık: Jira kodu varsa "KOD Jira başlığı" (Jira'dan çekilen başlık); Jira'dan çekilmiyorsa görevin ne yaptığını anlatan en kısa başlık. Yalnız kod ("PE-635") ya da genel ifade yazma; yukarıdaki {baslik} yerini bu başlıkla değiştir. -->

<!-- iki katman (ADR-0085, ADR-0091): `## Özet` yalnız kısa Şef Özeti'dir (gövde ≤ 1200 karakter); yöntem listesi, katman ayrıntısı, sayı tablosu ve kanıt ona girmez, hemen altındaki `## Harita`ya yazılır. Bu özet tek kaynaktır: yönetici anlatısı (`orkestra is anlati`) ve Jira Done yorumu (`orkestra is jira-yorum`) buradaki alanlardan türetilir, ayrıca yazılmaz. -->

<!-- Yazım kuralları (tüm belge):
1. Her ayrı ifade ayrı bir satırdır (madde işareti ya da numara ile); bir satırda en çok bir cümle, ~200 karakter.
2. Başlık hiyerarşisi: `##` ana başlık, `###` alt başlık; kalın etiket başlık yerine kullanılmaz, yalnız alan adı olarak kullanılır.
3. Kanıt (dosya:satır, komut, sayı) satırın sonunda parantez içindedir.
4. Belirsiz sahiplik ("bizim kod", "kendi sunucumuz") yazılmaz; somut ad yazılır (adres, sürüm, yol, tablo, müşteri).
5. Tablo ve kod bloğu yok. -->

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

<!-- doldur: en çok 2 cümle, düz dille: hangi yolu seçtik, neden, neyi eledik. Kullanıcı bağlamı bilmez: kısaltma ve iç terim kullanma. Ayrıntı `## Harita`daki Denenenler ve Kararlar'da. -->

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

<!-- doldur: her bilgi ayrı satır; her sayının yanına komutu ve ölçüm saatini yaz. -->

- Tarih ve saat: {tarih} {saat} (yerel)
- Depo: 

**Denenenler:**

<!-- doldur: neyi hangi yöntemle denedik; her deneme ayrı madde, tam bu biçimde: `- **Katman ya da bileşen:** yöntem → sonuç (işe yaradı | kısmen | yaramadı | ölçülmedi) (kanıt: dosya:satır, komut ya da sayı)`. -->

- 

**Sayılar:**

<!-- doldur: komutla ölçülen her sayı ayrı satır: komut → sayı (ölçüm saati). Sayı belgenin başka yerinde de geçiyorsa aynı olur (K-002). -->

- 

**Doğrulanmayanlar:**

<!-- doldur: yalnız denenip engele takılan şey girer; her satır konu ve somut engel (erişim, yetki, süre). Veritabanı, kod, komut ya da API ile bakılabilen şey bu bölüme yazılmaz, önce bakılır (ADR-0136); "bakılmadı" engel değildir. Yoksa "Yok". -->

- 

**Kararlar:**

<!-- doldur: alınan karar ve bilerek kapsam dışı bırakılan her şey ayrı satır; neden ve ADR ya da kimlik ile; yoksa "Yok". -->

- 

**Teslim:**

<!-- doldur (ADR-0091): Jira Done yorumu bu üç satırdan türetilir; satır başına bir değer, somut ad, sürüm ya da bağlantı ile. Değişiklik: PR bağlantısı ve birleşen commit. Test: hangi testler koştu, sonuç. Deploy: hangi ortama, ne zaman; ya da "çıkmadı, neden". Yapılmadıysa "yok" ve nedeni. -->

- **Değişiklik:** 
- **Test:** 
- **Deploy:** 

**Açık işlerin ayrıntısı:**

<!-- doldur: `Açık kalanlar`daki her iş için neden bekliyor, kimde ve sonraki adım; yoksa "Yok". -->

- 

## Plana göre gerçekleşen

<!-- doldur: plandaki her P ve mevcut durum gap bölümündeki her G ayrı satır; her satır en çok 300 karakter (biçim kapısı daha uzununu reddeder), ayrıntıyı bölüm altına ayrı paragraf yaz.
- P1: yapıldı | kısmen | yapılmadı. Kanıt: komut çıktısı ya da dosya:satır.
- G1: kapandı | açık. Hangi P ile kapandığı.
Planın dışına çıkılan işler ve kalan işler de ayrı satırlarla yazılır. -->

## Paralellik sapması

<!-- yalnız kapanış kapısı isterse doldurulur (ADR-0080; `paralel: true` iş, kartlar yüklenmedi ya da gerçekleşen ÷ planlanan < 0,5): planlanan, gerçekleşen (`orkestra is rapor <iş>`, ortalama eşzamanlı iş sayısı) ve neden; en az 40 karakter. Gerekmiyorsa boş bırak. -->

## Plandan sapmalar

<!-- yalnız /auto işlerinde zorunlu (ADR-0009): koşu sırasında plandan ayrılan her karar ayrı satır; yoksa "Yok". -->

## Otomatik kararlar

<!-- yalnız /auto işlerinde (ADR-0086, ADR-0132): kullanıcıya sorulmadan verilen her karar ayrı madde ve dört alanla; yoksa "Yok".
- **Karar:** ne yapıldı ya da ne yanıt verildi.
  - **Gerekçe:** neden bu, hangi kanıta dayanıyor.
  - **Alternatifler:** değerlendirilen diğer yollar.
  - **Geri alma:** kararı geri almanın yolu. -->

## Kullanıcıya kalanlar

<!-- yalnız /auto işlerinde zorunlu (ADR-0009): yalnız kullanıcının yapabileceği işler, sıralı ve uygulanabilir; yoksa "Yok". -->
