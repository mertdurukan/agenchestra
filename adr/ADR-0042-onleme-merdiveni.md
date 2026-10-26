# ADR-0042: Önleme merdiveni L0–L6: yeni kapıdan önce üst basamaklar sınanır

**Durum:** Kabul edildi

**Tarih:** 2026-10-24

**Bağlam:**

Orkestra denetimlerinin kök neden analizi (McD iş 129, `kok_neden_analizi_20261024.md` §2 ve §5) retlerin çoğunun sonradan yakalayan kapılardan geldiğini gösterdi. Aynı hata kaynağında önlenebilecekken üretilip reddediliyor. Ölçülmüş tek doğal deney ADR-0040: K-003 bağlantı satırları hook'a verilince ret 34'ten 0'a indi. Kapı sayısı arttıkça kural yükü ve dolanma (R8) da artıyor.

**Karar:**

Her ihlal sınıfı en sağlamdan en zayıfa giden merdivenin mümkün olan en üst basamağında çözülür:

- L0: kaldır ya da birleştir (ölü kural, çift kontrol).
- L1: türet, modele yazdırma (bağlantı satırı, numara zinciri, saat damgası).
- L2: kendi kapısından geçen iskelet (şablon uyum testi, sınırlı CLI girdisi).
- L3: mekanik düzelt (`updatedInput` ile güvenli dönüşüm).
- L4: tam zamanında bağlam (yazım anında yalnız ilgili biçim).
- L5: erken ve eksiksiz ret (tüm eksikler tek geçişte, hazır düzeltmeyle).
- L6: sonradan tespit (yalnız anlamsal denetim, denetçi ajan).

Yeni kapı eklenirken ilk soru: L0–L4 neden uygulanamadı? Cevap kapının ADR'sine ya da plan maddesinin Üretim noktası alanına yazılır (P-033'ün kapıların kendisine uygulanması).

**Seçenekler:**

- Kapı eklemeye ölçüsüz devam: elendi, ret ve dolanma artıyor, kök neden çözülmüyor.
- Yalnız mekanik düzeltme (L3): elendi, prototip biçim ihlallerinin yalnız %2,7'sini giderdi (analiz §4.2).
- Yalnız P-033 Üretim noktası alanı: elendi, plan maddelerine uygulanıyor, kapıların kendisine değil.

**Sonuçlar:**

- Olumlu: yeni kapı gerekçesi görünür olur; çözüm üretim noktasına kayar, ret ve kural yükü azalır.
- Olumsuz: kapı eklemek bir gerekçe adımı daha ister; basamak seçimi şimdilik mekanik denetlenmez.
- Ölçüm: hata.jsonl ret satırları artık ret_sinif (R1–R9), kapi, deneme alanlarını taşır; basamak değişikliğinin etkisi bunlardan okunur.
- Geri alma: ADR "Yerine geçildi" diye işaretlenir; ilke yalnız karar kuralıdır, kod değişikliği gerektirmez.

**İlgili:** I-224, K-006, P-028, P-033, ADR-0040
