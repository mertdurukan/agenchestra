# Önleme merdiveni (P-045, ADR-0042, ADR-0111)

Her çıktı, tabi olduğu denetimin kuralını yazılmadan önce görerek üretilir. Sorun üretildiği yerde, merdivenin en üst uygulanabilir basamağında çözülür; sonradan yakalama yalnız güvenlik ağıdır. Proje, `<durum dizini>/standartlar/onleme_merdiveni.md` ile ezebilir.

## Merdiven

- L0: kaldır ya da birleştir (ölü kural, çift kontrol).
- L1: türet, modele yazdırma (bağlantı satırı, numara zinciri, saat damgası).
- L2: kendi kapısından geçen iskelet (şablon, sınırlı CLI girdisi).
- L3: mekanik düzelt (`updatedInput` ile güvenli dönüşüm).
- L4: tam zamanında bağlam (yazım anında yalnız ilgili biçim).
- L5: erken ve eksiksiz ret (tüm eksikler tek geçişte, hazır düzeltmeyle).
- L6: sonradan tespit (yalnız anlamsal denetim).

## Yazım anı

Bu dosyayı yazıyorsun ve hedef bir denetime tabi: aşağıdaki kuralı yazmadan önce uygula; ret gelmesini bekleme. Yeni kontrol önermeden önce L0–L4'ün neden uygulanamadığını yaz.
