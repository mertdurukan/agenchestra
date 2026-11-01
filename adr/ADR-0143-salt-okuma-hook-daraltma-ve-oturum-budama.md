# ADR-0143: Salt okuma araçlarında PreToolUse kapatılır, oturumlar/ budanır, artımlı jsonl okuma ertelenir

**Durum:** Kabul edildi

**Tarih:** 2026-11-01

**Bağlam:** Ölçümde (hiz_bulgulari_20261101.md) her araç çağrısında Python hook süreci 0,4–0,97 sn taban maliyetle başlıyor; PreToolUse p50 1,4 sn, p95 6,3 sn. Read/Grep/Glob/ToolSearch çağrılarının kapıda yapacağı tek iş kimlik klasörü okuma yasağıdır. `oturumlar/` altında 3.110 dosya birikiyor, `ozet.arka_plan_oturumlari` hepsini açıyor.

**Karar:**

- PreToolUse genel eşleştiricisi `^(?!(?:Read|Grep|Glob|ToolSearch)$).*` olur. Read/Grep/Glob için ikinci giriş yalnız `**/.orkestra/credentials/**` yollarında hook'u çalıştırır (`if` kuralı); ADR-0014 kimlik kapısı korunur.
- `ozet.oturum_budama`: 48 saattir değişmeyen yeniden üretilebilir ara dosyalar (.devir, .isdeg, .soguk, .lock, devir_esigi, panel_ac_*, yonlendirme_*, devir_*.log) arka plan işçisinde en çok 6 saatte bir silinir. `<oid>.json`, `.baglanti.json`, `alan_*`, `onay_kaydi_*`, `devir_*.md`, `acik_ajan_*`, `is_*` asla silinmez. `ORKESTRA_OTURUM_BUDAMA=0` kapatır.
- `arka_plan_oturumlari` acik_gorevler taşımayan ad kalıplarını açmadan atlar.
- Artımlı jsonl okuma bu işte yapılmaz (aşağıda).

**Seçenekler:**

- Hook'u tüm araçlarda tutup hızlandırmak (kalıcı sunucu): elendi, süreç tabanı sürüyor ve HTTP hook desteği doğrulanmadı; ayrı iş.
- Matcher'dan yalnız Read çıkarmak: elendi, Grep/Glob/ToolSearch aynı maliyet, aynı risksiz sınıf.
- Budamayı arşive taşıma (P-013): elendi, silinenler çalışma sırasında yeniden üretilen çalışma artıkları; çıktı ya da denetim izi değil.
- Artımlı jsonl okuma: ertelendi. ADR-0140 ile ozet üretimi kullanıcı yolundan çıktı (arka plan işçisi); jsonl maliyeti (~1,5 sn) artık bekleme yaratmıyor. Ofset tabanlı tüketiciler geniş yüzey, kazanç düşük.

**Sonuçlar:**

- Olumlu: Read/Grep/Glob/ToolSearch çağrıları hook süreci başlatmaz; `oturumlar/` kapsamlı biçimde küçülür.
- Olumsuz: Bu araçlar artık `oturum_farkindalik` kalp atışı, `devir_hatirlatma` sayacı ve `_bolme_kapisi` "ilk anlamlı araç" sinyaline katkı vermez. Hook'un allow kararı bu araçlara uygulanmadığından izni olmayan projelerde proje dışı Read istem çıkarabilir.
- Doğrulanmadı: `if` alanı ve negatif ileri bakışlı eşleştiricinin kurulu Claude Code sürümünde çalışma zamanı davranışı; birim testi yalnız JSON yapısını ve regex'i sınar.
- Geri alma: hooks.json PreToolUse eşleştiricisini `.*` yapıp ikinci girişi sil; budama için `ORKESTRA_OTURUM_BUDAMA=0`.

**İlgili iş ya da kural kimliği:** I-003, ADR-0014, ADR-0140, P-013, P-028
