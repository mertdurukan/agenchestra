# ADR-0137: Auto modunda karar bölümü yok, kapı iş sahibini sorar

**Durum:** Kabul edildi

**Tarih:** 2026-11-01

**Bağlam:**

- ADR-0135 karar bölümünün yanıtın sonunda olmasını Stop kapısıyla zorladı; ret metni "bölümü sona taşı" idi.
- Kullanıcı: auto, ajanın kararları kendisinin verip uyguladığı sistemdir; gövdede karar bölümü olmamalı.
- Gerçek iki ihlalde "Sana kalan" ajanın yapabileceği işti (dal birleştirme); sorun sıra değil, işin yanlış sahibe yazılmasıydı.
- Auto'da `ask` yasak (ADR-0086), bu yüzden metin gövdeye düşüyordu.

**Karar:**

- Kapı auto modunu tanır (`izin_politikasi._auto_modu`).
- Auto'da kesin sınır dışı karar başlığı ("sana kalan", "karar", "onay bekleyen", "seçim") "sahip" ihlalidir: ret metni işi kendin yapmayı, yapamıyorsan "Engel" yazmayı ister.
- Kesin sınır ("Kullanıcıya kalanlar": parola, sır, hesap, push kararı) sonda geçer, ortadaysa "sira" ihlalidir.
- Yuvadaki her madde içerikli "Denendi:" taşır (boş, "yok", "denenmedi", "-" geçmez).
- Deterministik yedek yanıt yoktur: Stop hook yanıt metnini değiştiremez; ikinci denemede tur geçer, kullanıcıya uyarı satırı ve günlük girişi gider (P-032 için en yakın uygulanabilir yol).
- Plan modunda davranış değişmez.
- Tur başı yönergesi ve auto skill'i kuralı kaynakta söyler; kapı güvenlik ağıdır.

**Seçenekler:**

- Hook'un karar listesini türetip `systemMessage` ile göstermesi (L1): elendi, auto'da zaten karar yok; plan modunda karar `wrap_up` düğmesinde.
- Kapıyı auto'da kapatmak: elendi, yanlış sahipli bölüm sessiz geçerdi.
- Her başlığı sona taşıtmak (ADR-0135): elendi, yanlış işi sonda tutar.

**Sonuçlar:**

- Olumlu: ajan yapabileceği işi kullanıcıya bırakamaz; ret metni nedene konuşur.
- Olumsuz: ajan kesin sınır dışı işi "Kullanıcıya kalanlar" diye adlandırıp kapıyı aşabilir; özet kapısı (isler._auto_ozet_eksigi) yalnız "Kullanıcıya kalanlar" bölümünün varlığını yoklar, gövdeyle eşleşmeyi değil. Bunu yakalayan: "Denendi:" içerik biçimi kapısı ve ilk 30 auto turun elle sınıflanması; "Denendi:" içeriğinin anlamca doğruluğu ölçülmez (bilinçli sınır).
- Geri alma: ayarlar/cikti_sirasi.json `auto_sinif: false` ya da `ORKESTRA_CIKTI_SIRASI=0`.

**İlgili iş ya da kural kimliği:** I-322, ADR-0135 (genişletir, yerine geçmez), ADR-0086, P-001, P-029.
