# ADR-0103: Varsayılan çalışma modu proje ayarıyla `auto` yapılabilir

**Durum:** Kabul edildi

**Tarih:** 2026-10-30

**Bağlam:**

`auto` modu (ADR-0086) yalnız iş başına (`is.json` `mod`) ya da oturumda bekleyen mod olarak vardı; `is_onay.mod()` alan yoksa her zaman `plan` döndürüyordu. Kullanıcı klasör, proje ya da sohbet bazında izin sormayan tam yetki istedi. Her yeni işte `/auto` yeniden yazılmak zorundaydı.

**Karar:**

(1) `ayarlar/yetki.json` `varsayilan_mod` (plan | auto, eklenti varsayılanı `plan`); proje ezmesi `.claude/orkestra/yetki.json` (klasör = proje kökü). (2) `is_onay.mod(kayit, sd)` işte `mod` alanı yoksa, `izin_politikasi._auto_modu` iş bağlı değil ve bekleyen mod yoksa bu varsayılana düşer; açık `/plan` ve `/auto` varsayılanı geçer. (3) Kesin sınırlar değişmez: zorla push, kalıcı silme, kimlik klasörü ve sır kapıları `auto` altında da geçerli. (4) `yetki.json` ajan yazımına (Edit/Write/kabuk) `izin_politikasi._yetki_kapisi` ile kapalıdır; yalnız kullanıcı düzenler (P-020). Kapatma: `ORKESTRA_MOD_KAPISI=0`, `ORKESTRA_AUTO_YETKI=0`.

**Seçenekler:**

- İş açılışında `is.json`'a `mod:auto` yazmak: elendi. Eski işleri ve iş bağlanmamış oturumu kapsamaz; ayar değişince işler eski modda kalır.
- `settings.json` izin atlatma (bypass): elendi. Hook kapılarını ve kesin sınırları da düşürür.
- Alt klasör başına ezme: kapsam dışı. Durum klasörü proje başına tektir.
- Kullanıcı-düzeyi (tüm projeler) varsayılan: kapsam dışı. Kararı ayrıdır.

**Sonuçlar:**

Olumlu: tek ayarla proje boyunca onaysız akış; `/plan` ile sohbette geri alınır. Olumsuz: yanlış ayar tüm işleri `auto` yapar (bozuk ya da tanınmayan değer `plan`a düşer); `auto` altında onay kapısı belgeler tamamsa kendiliğinden geçer. Geri alma: `yetki.json` silinir ya da `varsayilan_mod: plan`.

**İlgili iş:** I-276, P-016, P-020, ADR-0086, ADR-0095
