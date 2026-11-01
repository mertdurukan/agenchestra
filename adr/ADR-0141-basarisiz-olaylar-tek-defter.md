# ADR-0141: Başarısız olaylar tek defterde (hata.jsonl) kayıtlanır

**Durum:** Önerildi

**Tarih:** 2026-11-01

**Bağlam:**

- Hook reddi `hata.jsonl`'e yazılıyor (596 satır), ama araç hataları (Bash, Edit, MCP) hiçbir yere yazılmıyor; `skill_hata` kodu var ama `gunluk.jsonl`'de 0 satır.
- Kök neden analizi ve tekrarı önleme için başarısız olayın tamamı tek yerde, aynı şemada olmalı (kullanıcı kararı, 01.11.2026).

**Karar:**

- Tek defter `hata.jsonl` kalır; araç hatası üst düzey `kaynak: arac` satırı olarak `hata_kayit` ile yazılır, kök neden `kok.kaynak` altında ayrı kalır.
- Yazma yeri `PostToolUseFailure` hook'udur; API hatalı tur için `StopFailure`, reddedilen çağrı için `PermissionDenied` eklenir ve `hook-red` ile pencere bazlı tekilleştirilir.
- Tekrar `orkestra hata en-cok` içinde sayılır; kök neden durumu (açık | çözüldü) imza bazında ayrı dosyada tutulur, defter ekleme-yalnız kalır.

**Seçenekler:**

- Seçilen: mevcut `hata.jsonl` genişletilir. Neden: okuyucular (hata_en_cok, olay_kaydi, `orkestra hata`) hazır, tek şema.
- Elenen: ayrı `arac_hata.jsonl`. Neden elendi: iki defter, iki okuyucu; birleşik sorgu ve tekrar sayımı bölünür.
- Elenen: `gunluk.jsonl`'e yazmak. Neden elendi: günlük olay akışıdır, imza ve kök neden alanı taşımaz.
- Elenen: durumu hata.jsonl satırına yazmak. Neden elendi: defter ekleme-yalnızdır, durum değişen veridir.

**Sonuçlar:**

- Olumlu: tek sorguyla tüm başarısızlıklar, imza bazlı tekrar ve kök neden durumu.
- Olumsuz: her araç hatasında bir yazma; hook süresi 10 sn zaman aşımı içinde kalmalı.
- Geri alma: hook'lardaki tek çağrı kaldırılır; eski satırlar zararsız kalır.

**İlgili iş ya da kural kimliği:** I-329, K-006, ADR-0035, ADR-0037, ADR-0101
