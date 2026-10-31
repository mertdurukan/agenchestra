# ADR-0127: Oturum farkındalık kapısı ihlal moduna geçti (engellemeden)

**Durum:** Kabul edildi

**Tarih:** 2026-11-01

**Bağlam:** ADR-0125 (I-308) kapıyı P-028 gereği `golge` modunda açtı; geçiş ölçütü ≥60 sınıflı tespitte yanlış pozitif ≤ %10 ve kullanıcı kararıydı. Kullanıcı 01.11.2026'da ihlal modunu başlatmayı istedi. Ölçüt henüz sağlanmadı: `orkestra oturum rapor` sınıflı tespit sayısı 0 (ölçüm 01.11.2026).

**Karar:** `ayarlar/oturum_farkindalik.json` `mod` değeri `ihlal` olur. İhlal bu kapıda engelleme değildir (ADR-0125: akış bozulmaz): bağlam satırı `UYARI:` ile başlar ve tespit `gunluk.jsonl`'a `kapi_ihlal` olarak yazılır. `orkestra oturum rapor` iki türü de sayar. Ölçüt sağlanmadığı için ilk 30 `kapi_ihlal` kaydı `orkestra oturum rapor --sinifla ZAMAN=dogru|yanlis` ile elle sınıflanır; yanlış pozitif oranı > %10 ise mod `golge`ye döner.

**Seçenekler:**

- Git yazan komutta `permissionDecision: ask`: elendi; I-300 olayını önlerdi ama akışı keser, kapsam dışı (sözleşme: bloklama yok).
- Gölgede kalıp ölçüm beklemek: elendi; kullanıcı kararı geçişi istedi.

**Sonuçlar:**

- Olumlu: uyarı daha görünür; ihlal kayıtları ölçümü hızlandırır.
- Olumsuz: yanlış pozitif satırı daha dikkat çekici olur; ölçüt sağlanmadan geçildi.
- Geri alma: ayarda `mod: golge` ya da `ORKESTRA_OTURUM_FARKINDALIK=0`.

**İlgili iş ya da kural kimliği:** I-308, ADR-0125, P-049, P-028.
