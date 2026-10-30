# ADR-0108: Soğuk önbellek kapısı engellemez, yalnız bilgi verir

**Durum:** Kabul edildi

**Tarih:** 2026-10-30

**Bağlam:** Kapı büyük bağlamda mesajı `decision:block` ile durdurup yeniden gönderme istiyordu. Kullanıcı bunu hata olarak yaşadı (mesajı tekrar yazmak zorunda kaldı) ve kapının yalnız bilgi vermesini istedi. Aynı dosyadaki devir ve iş değişimi uyarıları zaten engellemiyor.

**Karar:** `soguk_onbellek.karar` yalnız bilgi metni döndürür; hook bunu `systemMessage` olarak basar ve mesaj aynı turda işlenir. Metin yeniden gönderme istemez; maliyet tahmini ve `orkestra is devam` önerisi kalır. Aynı soğuma için uyarı `tekrar_dk` içinde bir kez verilir.

**Seçenekler:**

- Kapıyı tümüyle kapatmak: elendi, maliyet bilgisi (ölçümde önbellek yazımının ~%35'i) kullanıcıya hiç ulaşmaz.
- Engellemeyi koruyup mesajı otomatik yeniden göndermek: elendi, hook mesajı yeniden gönderemez.
- Yalnız bilgi vermek: seçildi.

**Sonuçlar:** Olumlu: kullanıcı mesajı kaybolmaz, tekrar yazmaz. Olumsuz: soğuk önbellek maliyeti artık kullanıcı seçmeden doğabilir; bilgi mesajı bunu görünür kılar. Geri alma: `soguk_onbellek.py` ve `hook.py` değişikliğini geri almak; ayar `{"acik": false}` ile kapı yine kapatılabilir.

**İlgili iş:** I-285, I-287; P-016 ile ilişkili değildir.
