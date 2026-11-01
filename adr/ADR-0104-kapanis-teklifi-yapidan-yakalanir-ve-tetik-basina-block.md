# ADR-0104: Kapanış teklifi yapıdan yakalanır (kalıp kapısına yapı kalıpları)

**Durum:** Kabul edildi

**Tarih:** 30.10.2026

**Bağlam:**

Kullanıcı, yanıt sonundaki `Kartı değiştirmemi istiyorsan "yap" de.` cümlesinin düğme olmadığını bildirdi. Yerelde çalıştırma: `yanit_ihlali` ve `teklif_sonu` ikisi de False. Kalıp listesinde "istiyorsan … de" yapısı yok. Kalıp kapısı `mod: block` ve çalışıyor (DemoRoot günlüğünde 55 kayıt); ADR-0043 "eksik kalıp ihlali kaçırır" riskini yazmıştı.

**Karar:**

`ayarlar/secim_ekrani_hatirlatma.json` `yanit_kaliplari`'na kapanış yapısına bakan iki kalıp eklenir: (a) koşul ifadesi (istiyorsan, istersen, isterseniz, uygunsa, onaylıyorsan, olursa) ile biten konuşma fiili emri (de, yaz, söyle, onayla, bildir, haber ver); (b) tırnaklı yanıt sözcüğü ve ardından "de/yaz/dersen". Kod değişmez. `teklif_sonu` ve `yapisal_mod` golge kalır.

**Ölçüm:** DemoRoot transkriptlerinin son 150 dosyasında 1247 tur (korpus A) ve tasarımda kullanılmayan 1096 tur (korpus B) tarandı (30.10.2026); yeni kalıplar 20 turda eşleşti, 20'si gerçek düz metin teklif; yanlış pozitif 0/20, %95 alt sınır %86,1; yakalama oranı ölçülmedi; ayrıntı I-279 olcum_kapanis_20261030.md. Eski `teklif_sonu` kalıpları aynı korpusta 170 turda eşleşiyor; çoğu "?" ile biten gerçek soru olduğundan block'a alınmadı.

**Seçenekler:**

- **`teklif_sonu` tetiğini block yapmak:** elendi. 1247 turun 170'inde eşleşir, yanlış pozitif ölçülmemiş (P-028).
- **Kural metnine cümle eklemek:** elendi. P-029 zaten var; ADR-0036: yalnız kurala bağlı uyum sağlamıyor.
- **Model çağıran sınıflayıcı:** elendi. Her Stop'ta token harcar (yöntem seçimi sırası).

**Sonuçlar:**

- **Olumlu:** kapanış teklifi bu ifade ailesinde düğmeye zorlanır; kod ve hook değişmez.
- **Olumsuz:** başka ifade yine kaçabilir; yanlış pozitifte tura bir ek hatırlatma turu eklenir ("karar anı değilse yok say").
- **Geri alma:** iki kalıp satırı silinir ya da `ORKESTRA_SECIM_HATIRLATMA=0`.

**İlgili iş:** I-279, P-029, P-028, ADR-0043.
