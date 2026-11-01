# ADR-0140: Entegrasyon kuyruğu, tek şeritte birleşik tam koşu

**Durum:** Kabul edildi

**Tarih:** 2026-11-01

**Bağlam:**

- Eşzamanlı oturumların her biri tam test paketini koşuyordu; makine genelinde test kilidinde bekleme ve aynı kırığın çok oturumda yinelenmesi oluyordu.
- I-323 dalı (kuyruk-i323) bu kararı kodladı ve GELISTIRME.md'ye "ADR-0134" diye yazdı; ADR-0134 numarası main'de başka karara (SessionStart zaman bütçesi) ait olduğu için karar hiç ADR dosyası olarak yazılmamış kaldı.

**Karar:**

- Oturum teslimi `orkestra teslim kuyruk ekle` ile entegrasyon kuyruğuna verilir; commit öncesi yalnız hedefli test koşulur (kartın `test_alani`), tam paket oturumda koşulmaz.
- Entegrasyon şeridi (`scripts/entegrasyon.py`) birleşik tam koşuyu bir kez yapar; yeşilde main'e fast-forward, kırmızıda bisect ve karantina, suçlu oturuma `not_birak` ile geri bildirim.
- Durumlar: bekliyor, kosuyor, birlesti; kosuyor'dan karantina (kırmızı koşuda suçlu); karantina'dan bekliyor (düzeltme yeniden teslim edilince).
- Koşucu ölürse `kuyruk.kurtar` takılı kosuyor kaydını bekliyor'a döndürür ve kilidi bırakır.
- Kapı `ayarlar/kuyruk.json` içinde `golge` modunda başlar (P-028); `ihlal` geçişi ölçümden sonra ayrı kararla.

**Seçenekler:**

- Her oturumun kendi tam koşusu: elendi, kilit bekleme ve yinelenen kırık sürdü.
- Kuyruksuz doğrudan main'e itme: elendi, kırmızı birleşik durum main'e girebilirdi.

**Sonuçlar:**

- Olumlu: tam koşu tek yerde ve bir kez; suçlu oturum geri bildirimle bulunur.
- Olumsuz: kuyruk koşucusu tek hata noktasıdır; sahipsiz karantina oturum açılışında uyarı satırına düşer.
- Geri alma: `ORKESTRA_KUYRUK_KAPISI=0` kapıyı kapatır; kuyruğu kullanmamak eski davranıştır.

**İlgili iş ya da kural kimliği:** I-323, I-330 (ADR atfı düzeltmesi), P-028, ADR-0134 (numara çakışması nedeniyle yalnız anılır).
