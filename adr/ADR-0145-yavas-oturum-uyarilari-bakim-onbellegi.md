# ADR-0145: Yavaş SessionStart uyarıları bakım koşucusunda hesaplanır

**Durum:** Kabul edildi

**Tarih:** 2026-11-02

**Bağlam:** SessionStart p50 7,3 s ölçüldü (2026-11-01 günlüğü); 82 çağrı 10 s sınırında zaman aşımına düştü ve bu durumda oturum bağlamı yüklenmez. `uyarilar` bölümü 4,4 s'dir. Beş uyarı kaynağı her açılışta eşzamanlı hesaplanıyordu: maliyet 368 ms, hata 279 ms, iz 408 ms, todo 733 ms, devral 410 ms. Bu uyarılar saatler içinde değişmez.

**Karar:** Beş hesap `oturum_bakim.py` içinde `UYARI_ADIMLARI` olarak ADR-0092 koşucusuna eklenir (en çok saatte bir, ayrık süreç, `bakim_onbellek.json`). `hook.py::_ss_uyarilar` yalnız `yavas_uyarilar()` ile önbellekten okur. Önbellek yoksa ilk açılış uyarısız geçer; koşucu sonrakini doldurur. `ORKESTRA_OTURUM_BAKIM=0` ise eski davranış: uyarılar eşzamanlı hesaplanır.

**Seçenekler:**

- Hesapları hızlandırmak: elendi, her biri dosya taraması yapar; kazanç küçük ve kalıcı değil.
- SessionStart zaman aşımını artırmak: elendi, kullanıcıyı daha uzun bekletir, nedeni gidermez.
- Uyarıları tamamen kaldırmak: elendi, işe bağlı olmayan todo ve eşik aşımı bilgisi işe yarıyor.

**Sonuçlar:**

- Olumlu: SessionStart'tan yaklaşık 2,2 s (beş kaynağın toplamı) çıkar; zaman aşımı oranı düşmesi beklenir.
- Olumsuz: uyarı en çok bir saat eski olabilir; ilk oturum uyarısızdır.
- Doğrulanmadı: gerçek kazanç sonraki günlerde `bolumler.uyarilar` p50'siyle ölçülür (taban 4368 ms).

**İlgili iş ya da kural kimliği:** I-003, ADR-0092, ADR-0143, P-022
