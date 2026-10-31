# ADR-0121: denetci bölünmez; yanlış ret ölçümü düzeltilmiş setle yeniden koşulur

**Durum:** Kabul edildi

**Tarih:** 2026-10-31

**Bağlam:**

I-292 P7, `agents/denetci.md`'nin (4 kip) bölünüp bölünmeyeceğine P5 verisiyle karar verir. P5 (`evals/denetci-yakalama/sonuc_20261031.md`): 30 bozuk vakada kaçırma 0 (%95 üst sınır %9,5, eşik karşılandı); 30 doğru vakada yanlış ret 2 (üst sınır %19,5, eşik karşılanmadı). İki yanlış ret de konusu "API" olan vakada, `kriter-belirsiz` koduyla; ölçüm setinde başlık "Api", dosya adı "API_" yazıyor.

**Karar:**

(1) `denetci` bölünmez. (2) Yanlış ret oranı eşiği aşıyor; P-030 hedefi bu ölçümle karşılanmış sayılmaz. (3) Üretici `eval_denetci.py` başlıkta konu sözcüğünün harf biçimini korur (kaynakta düzeltme) ve 60 vakanın tamamı yeniden koşulur; yeniden koşuya kadar yanlış ret hedefi "karşılanmadı" olarak kayıtlıdır. (4) Yeniden koşuda da yanlış ret üst sınırı %10'u aşarsa `denetci.md` kök neden maddesi açılır.

**Seçenekler:**

- Elenen: dört ajana bölmek. Kaçırma 0; bölmeyi gerektiren veri yok. `denetci` kimliğine bağlı hook'lar (`hook.py` `endswith("denetci")`, politika, enjeksiyon) bölünen ajanlarda kırılır.
- Elenen: yalnız 018 ve 044'ü yeniden koşup hedefi karşılanmış saymak. Seçim yanlılığı; düzeltme sonrası tam set gerekir.
- Elenen: yanlış reti "set kusuru" diyerek kapatmak. Hipotez kanıtlanmadı (API vakalarında 2/3 ret, diğerlerinde 0/27).

**Sonuçlar:**

Olumlu: bölme riski alınmadı, ölçüm kusuru kaynakta düzeltilecek. Olumsuz: P-030 yanlış ret hedefi şimdilik açık; yeniden koşu 60 denetçi çağrısı maliyetlidir. Geri alma: karar yeni ADR ile değiştirilir, `git revert`.

**İlgili iş:** I-292 (P5, P7), P-030, P-032, ADR-0120

**Güncelleme (2026-10-31):** Yeniden koşu yapıldı (`sonuc_20261031.md` v2 bölümü): kaçırma 0/30 (üst %9,5), yanlış ret 0/30 (üst %9,5). Eşik karşılandı; karar (4) kapsamında `denetci.md` kök neden maddesi açılmaz.
