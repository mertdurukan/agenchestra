# ADR-0138: Oturumlar arası iş talebi (kira) ve test hatası atfı

**Durum:** Kabul edildi

**Tarih:** 2026-11-01

**Bağlam:**

Açık oturumlar aynı depoda eşzamanlı çalışıyor (`orkestra is liste`: en az 29 açık iş, 01.11.2026 13:25).
Bugün yalnız dosya düzeyinde komşu uyarısı (ADR-0125, ADR-0127) ve test sonucu tek uçuşu (`test_onbellek.py`) var.
İki oturum aynı todo işini bağımsız yapabilir; düşen testi koşan oturum, hatayı yazan oturumun bağlamını bilmeden çözmeye çalışır.

**Karar:**

- Todo işi için süreli talep (kira) kaydı tutulur: anahtar yazma alanı kümesi ve normalize madde metni; sahip canlı kalmazsa (30 dk) talep düşer ve başka oturum devralır.
- İlk sürümde ikinci talep engellenmez, gölgede uyarılır: "bu iş I-xxx oturum abcd'de"; ihlale geçiş ölçümden sonra ayrı kararla yapılır (P-028).
- Test düşünce her düşen test, oturum konum kaydındaki son yazılan dosyalarla (`konum.yazilan`) en çok bir sahip oturuma eşlenir; eşleşmeyen sahipsizdir.
- Sahip canlıysa bağlam paketi (iş, todo kanıt notları, yazılan dosyalar) gelen kutusuna bırakılır; sahip canlı değilse ya da sahipsizse hatayı testi koşan oturum paketi okuyarak çözer.
- Eşleştirme belirlenimcidir (yol ve metin benzerliği); LLM yalnız belirsiz kalan için sonraki sürümde değerlendirilir.
- Genel davranış orkestra eklentisinin asıl kaynağında yazılır (P-022).

**Seçenekler:**

- Merkezi koordinatör süreç: elendi; ek servis ve tek hata noktası, dosya tabanlı oturum kaydı yeterli.
- Birleşik durumda sıralı test kuyruğu (merge queue): elendi; oturumlar ayrı dal ve worktree üzerinde çalışıyor, ortak kuyruk dal modelini değiştirir.
- Yalnız not bırakma (bugünkü durum): elendi; iş çakışmasını önlemez, hatayı sahibine eşlemez.
- Madde eşleştirmede başlangıçtan LLM: elendi; maliyet, tutarsızlık ve doğrulanabilirlik (K-006, P-030).

**Sonuçlar:**

- Olumlu: tekrar iş azalır, hata sahibin bağlamıyla çözülür, mevcut oturum kaydı ve gelen kutusu yeniden kullanılır.
- Olumsuz: yanlış eşleşme gereksiz not üretir; gölge dönemde ölçülür, kapı engellemez.
- Geri alma: kapı ayarı `kapali`, `ORKESTRA_IS_TALEBI=0` kapatır; yeni kayıt dosyası silinebilir, mevcut davranış değişmez.

**İlgili iş ya da kural kimliği:** I-324, ADR-0125, ADR-0127, P-022, P-028, K-006.
