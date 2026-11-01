# ADR-0135: Karar bekleyen konu yanıtın en sonunda; sıra kapısı ilk günden ihlal modunda

**Durum:** Kabul edildi

**Tarih:** 01.11.2026

**Bağlam:**

- Kullanıcı, karar vermesi gereken konuların her zaman yanıtın en sonunda olmasını ve bunun garanti edilmesini istedi; yanıtların da çok uzun olduğunu söyledi.
- Bugün düz metinle karar isteme engelli (ayarlar/secim_ekrani_hatirlatma.json:2, mod block), ama "Sana kalan" gibi karar-benzeri bölümün yanıtın ortasında olmasını denetleyen kod yok.
- Uzunluk yalnız ölçülüyor (ayarlar/cikti_butce.json:2, mod golge).

**Karar:**

- Karar bekleyen konular yalnız yanıtın son bloğunda (wrap_up kutusu ya da auto modunda son bölüm "Kullanıcıya kalanlar") bulunur.
- Sıra kapısı kullanıcı kararıyla ilk günden ihlal (block) modunda açılır; P-028 gölge ilkesinin bilinçli istisnasıdır (emsal P-033).
- Uzunluk kapısı gölgede kalır; en az 30 yanıt ölçülüp yanlış pozitif oranı yazıldıktan sonra ayrı kararla block'a alınır.
- Yanıt iskeleti tek yerde tanımlanır: sonuç tek cümle, en çok 3 madde, karar en sonda.

**Seçenekler:**

- Elenen: yalnız kural metnini güçlendirmek. Neden elendi: model uyumu garanti etmez; kullanıcı mekanik garanti istedi.
- Elenen: sıra kapısını da gölgede açmak. Neden elendi: kullanıcı "garanti et" dedi; gölge dönemi ihlalleri engellemez.
- Elenen: kararı yalnız wrap_up ask alanıyla sınırlamak. Neden elendi: auto modunda ask yasak (ADR-0086), karar "Kullanıcıya kalanlar"da yazılıyor.

**Sonuçlar:**

- Olumlu: karar yeri öngörülebilir olur; ortada kalan karar cümlesi turu bir kez bloklar.
- Olumsuz: yanlış pozitif tur bloklayabilir; kapı her ret için günlüğe kapi_ret yazar, ilk 30 bayrak elle sınıflanır.
- Geri alma: ayarlar/cikti_sirasi.json mod alanı golge ya da kapali yapılır (ORKESTRA_CIKTI_SIRASI=0).

**İlgili iş ya da kural kimliği:** I-321, P-001, P-028, P-029, P-033, K-005, ADR-0086
