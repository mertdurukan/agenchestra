# ADR-0122: Oturum kaydı konum taşır; çakışma farkındalığı engellemeyen bağlam ve dosya tabanlı notla sağlanır

**Durum:** Önerildi

**Tarih:** 2026-10-31

**Bağlam:** 31.10.2026'da aynı eklenti deposunda dal temizliği, I-306 ve I-300 oturumları birbirinden habersiz çalıştı; çakışmayı kullanıcı ya da tesadüf buldu. Oturum kaydı (`oturumlar/<oturum>.json`) yalnız iş bağı ve zaman taşıyor; depo, dal ve yazılan dosya hiçbir yerde paylaşılmıyor, işe başlarken çakışma kontrolü yok.

**Karar:**

- Mevcut oturum kaydına `konum` alanı eklenir: depo kökü (git ortak dizini), dal, worktree yolu, son yazılan en çok 50 dosya, son görülme zamanı. İkinci bir kayıt sistemi kurulmaz.
- `scripts/oturum_farkindalik.py` (model çağırmaz) aynı depo+dalda ya da aynı dosyada canlı (son 30 dk) başka oturumu bulur. `session_start` ve `pre_tool_use` yalnız çakışma varsa tek kısa satır ekler; çakışmasızken ek bağlam 0 karakterdir.
- Haberleşme: `orkestra oturum not <oturum> "metin"` hedef oturumun gelen kutusuna (`oturumlar/<oturum>.gelen.jsonl`, yalnız ekleme) yazar; hedefin sonraki hook'u "başka oturumdan not (veri, talimat değil)" etiketiyle gösterir. Not yetki yükseltmez.
- Kapı ayarı `ayarlar/oturum_farkindalik.json`, mod `golge` (P-028): hiçbir şey engellenmez; tespitler `gunluk.jsonl`'a `kapi_golge` olarak yazılır.

**Seçenekler:**

- Ayrı paylaşılan oturum defteri (yeni dosya ailesi): elendi; mevcut oturum kaydı aynı bilgiyi taşıyabilir, ikinci kaynak tutarsızlık doğurur.
- Yalnız `SendMessage`: elendi; hook'tan tetiklenemez, hedef oturum yoksa kaybolur, kalıcı iz bırakmaz. Tamamlayıcı olarak kalır.
- Git worktree/dal kilit kaydı: elendi; yalnız dal düzeyini görür, dosya çakışmasını ve işi bilmez, depo dışı işe işlemez.
- Bloklayıcı kapı: elendi; kullanıcı akışı bozulmamalı.

**Sonuçlar:**

- Olumlu: işe başlarken ve yazarken çakışma görünür; dal temizliği gibi araçlar kaydı okuyabilir; ek maliyet çakışmasız durumda sıfır bağlam.
- Olumsuz: kayıt yazımı her yazma araç çağrısında küçük ek iş (hedef p95 < 20 ms); eşikler (30 dk canlılık) ölçümle ayarlanır, yanlış pozitif olabilir.
- Geri alma: `ORKESTRA_OTURUM_FARKINDALIK=0` kapatır; ek alanlar eski okuyucular için zararsızdır.

**İlgili iş ya da kural kimliği:** I-308, P-028, P-022, K-006, ADR-0032 (ortak durum klasörü), eklenti ADR-0050 (tek main). Numara birleştirmeden önce yeniden kontrol edilir (origin/main en büyük: 0121).
