# ADR-0104: Kapanış teklifi yapıdan yakalanır; `teklif_sonu` tetiği block

**Durum:** Kabul edildi

**Tarih:** 30.10.2026

**Bağlam:**

Kullanıcı, yanıt sonundaki `Kartı değiştirmemi istiyorsan "yap" de.` cümlesinin düğme olmadığını bildirdi. Yerelde çalıştırma: `yanit_ihlali` ve `teklif_sonu` ikisi de False. Kalıp listesi bu ifadeyi içermiyor; yapısal kapı yalnız `?` ya da -ım/-im ekiyle biten cümleyi sayıyor. Ayrıca `yapisal_mod` golge olduğu için yakalansa da engellenmezdi; McD günlüğünde `teklif_sonu` tetiği hiç kayıt düşmedi (18 yapısal kayıt, hepsi `degisiklik`). ADR-0043 "eksik kalıp ihlali kaçırır" riskini yazmıştı.

**Karar:**

(1) `teklif_sonu_kaliplari` kapanış yapısına bakan iki kalıp alır: koşul ifadesi (istiyorsan, istersen, uygunsa…) ile biten konuşma fiili emri (de, yaz, söyle, onayla…); tırnaklı yanıt sözcüğü ve ardından "de/yaz". (2) Ayara `yapisal_mod_tetik` eklenir; `teklif_sonu` block, `degisiklik` golge kalır. (3) `yapisal_mod(ayar, tetik)` tetik anahtarını önce okur; hook kipi tetikle çağırır.

**Seçenekler:**

- **Tek tek ifade eklemek:** elendi. Aynı kaçış bir sonraki ifadede sürer.
- **`yapisal_mod` genel block:** elendi. `degisiklik` tetiği her düzenleme turunu etkiler, ölçümsüz (P-028).
- **Model çağıran sınıflayıcı:** elendi. Her Stop'ta token harcar (yöntem seçimi sırası).

**Sonuçlar:**

- **Olumlu:** kapanış teklifi ifadeden bağımsız düğmeye zorlanır.
- **Olumsuz:** yanlış pozitifte tura bir ek hatırlatma turu eklenir ("karar anı değilse yok say").
- **Geri alma:** ayarda `yapisal_mod_tetik` silinir ya da `ORKESTRA_SECIM_HATIRLATMA=0`.

**İlgili iş:** I-279, P-029, P-028, ADR-0043.
