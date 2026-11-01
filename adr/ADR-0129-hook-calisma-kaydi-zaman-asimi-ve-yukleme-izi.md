# ADR-0129: Hook çalışma kaydı; zaman aşımı ve yükleme izi oturum bazında tutulur

**Durum:** Kabul edildi

**Tarih:** 2026-11-01

**Bağlam:** Claude Code zaman aşımına uğrayan hook sürecini öldürür; süreç kendini kaydedemediği için "hangi oturumda hangi hook ya da skill gerçekten çalıştı" sorusunun cevabı yoktu. `gunluk.jsonl` yalnız enjekte edilen bağlamın özetini (`baglam`) ve SessionStart süresini (`hook_sure`) tutuyordu; yüklenmeyen hook iz bırakmıyordu.

**Karar:**

- `scripts/hook_kaydi.py` (model çağırmaz, hatada sessiz): her hook başlarken `hook_acik/<pid>-<ns>.json` işareti yazar, biterken siler ve `gunluk.jsonl`'a `hook_calisma` (olay, oturum, araç, sonuç, süre) ekler. Hızlı ve başarılı PreToolUse için günlük satırı yazılmaz; yalnız 1 sn üstü yazılır.
- Silinmemiş eski işaret öldürülmüş hook demektir; süreç ölüysa (ya da 10 dk geçtiyse) `hook_zaman_asimi` olarak kaydedilir. Tarama SessionStart, Stop ve rapor çağrısında çalışır. Sınırlar `hooks.json` ile aynıdır, testle doğrulanır.
- Skill: başarılı yükleme `skill` (mevcut), hata `skill_hata` olarak yazılır (PostToolUseFailure).
- SessionStart sonunda `oturum_yukleme` satırı beklenen hook olaylarını ve skill sayısını yazar; satırı olmayan ama hook kaydı olan oturum `acilis_eksik` sayılır.
- Sonraki SessionStart, son 24 saatte bildirilmemiş zaman aşımı varsa tek kısa satır ekler; yoksa 0 karakter.
- `orkestra oturum hook [--gun N] [--oturum X]` oturum x olay özeti, skill listesi ve `acilis_eksik` verir. Kapatma: `ORKESTRA_HOOK_KAYDI=0`.

**Seçenekler:**

- Her çağrıda günlük satırı: elendi, PreToolUse her araç çağrısında çalışır; günlük şişer ve Windows'ta kilitli yazım ~25 ms ekler.
- Yalnız bitiş satırı: elendi, öldürülen hook bitiş satırı yazamaz; iz tam da kaybolan durumdur.
- Sürekli çalışan izleyici süreç: elendi, ek süreç ve yaşam döngüsü yükü; işaret dosyası yeterli.

**Sonuçlar:** Olumlu: zaman aşımı ve yüklenmeyen skill sonradan görülür; oturumlar arası karşılaştırma mümkün. Olumsuz: her hook çağrısında küçük bir işaret dosyası yazılıp silinir (kilitsiz, tek dosya). Zaman aşımı yalnız sonraki hook ya da rapor çağrısında kaydedilir, anında değil. Geri alma: `ORKESTRA_HOOK_KAYDI=0`; ek alanlar eski okuyucular için zararsızdır.

**İlgili iş ya da kural kimliği:** I-309, P-028, ADR-0125.
