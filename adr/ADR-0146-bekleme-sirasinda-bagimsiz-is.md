# ADR-0146: Bekleme sırasında bağımsız iş (bekleme kaydı, golge)

**Durum:** Kabul edildi

**Tarih:** 2026-11-02

**Bağlam:** Test kirası kuyruğu, arka plan görevi, CI koşusu ya da denetçi beklenirken ajan boşa duruyordu; kullanıcı "beklemeye girince bağımsız işleri paralel yap, onlar bitince bekleneni al" davranışını istedi. P-035 paralelliği yalnız plan aşamasındadır; çalışma anında bekleme tespiti, kaydı ve ölçümü yoktu. ADR-0139 yalnız sınırsız sleep döngüsünü yakalar.

**Karar:**

- `scripts/bekleme_kaydi.py` + `ayarlar/bekleme_kaydi.json` + `orkestra bekleme ac|kapat|liste|rapor`: bekleme noktası tek kayıt yazar (ne, hangi olayla biter, tahmini süre, kaynak, iş); kayıt durum klasöründe `bekleme.json`.
- Kayıt açıkken PreToolUse hook'u (`hook._bekleme_kaydi_kapisi`) işin todo'sundaki bekleyenden bağımsız açık P maddelerini (plandaki `Önce:` ve `Yazma alanı:`, `paralellik.maddeler`) kayıt başına bir kez bağlama koyar ve ana ajanın araç çağrılarını "beklerken yapılan iş" diye sayar.
- Kaynak kirası kuyruğu (`kaynak_kira.kira`) gerçekten beklerken kayıt açar, kira alınınca ya da zaman aşımında kapatır.
- `gunluk.jsonl`: `bekleme_ac` ve `bekleme_kapat` (`bekleme_s`, `bos_s`, `yapilan`). Boş süre, kayıt damgaları araç çağrılarıyla bölünür; `bosluk_esik_s` (90 sn) üstü aralıkların toplamıdır; blokta bekleyen ajan için `bos_s = bekleme_s`.
- Kayıtsız `sleep N` (N ≥ 5), `Start-Sleep`, `gh run watch` komutu `bekleme_kaydi` kapısına takılır. Başlangıç modu `golge` (P-028); `ihlal` geçişi ≥14 gün ve ≥30 `bekleme_kapat` olayı ölçümünden, yanlış pozitif ≤%10 elle sınıflamasıyla, ayrı ADR ile. Kapatma `ORKESTRA_BEKLEME_KAYDI=0`.
- Davranış kuralı P-053 eklenti kuralına yazılır; kod yalnız kaçanı yakalar.

**Seçenekler:**

- Elenen: kaydı `bekleme_kapisi.py` içine eklemek (o modül döngü ayrıştırır, ADR-0139 testleri onu sabit tutar).
- Elenen: kaydı yalnız `gunluk.jsonl` olaylarından türetmek (her araç çağrısında günlük taranır).
- Elenen: ayrı PreToolUse hook dosyası (ikinci süreç, hook süresi uzar; ADR-0143).
- Elenen: hook'ta test komutunu adından tanıyıp kayıt açmak (projeye özgü ad koda girer; P-022).
- Elenen: yalnız kural metni (K-006: üretim anında zorlanmaz).

**Sonuçlar:**

- Olumlu: bekleme süresi ve bağımsız iş yapılıp yapılmadığı ölçülür; kuyrukta bekleyen ajan bağımsız maddeleri görür.
- Olumsuz: foreground komutta bloklanan ajan bildirimi kendisi göremez; bildirim bir sonraki araç çağrısında gelir, bu yüzden uzun koşu `run_in_background` ile başlatılmalıdır.
- Sınırlama: bağımsızlık yalnız plandaki `P<n>` maddelerinden hesaplanır; P numarasız todo satırı önerilmez.
- Geri alma: ayarda `mod` değeri ya da `ORKESTRA_BEKLEME_KAYDI=0`; kodu kaldırmak `hook.py` içindeki `_bekleme_kaydi_kapisi` çağrısını ve `kaynak_kira.py` içindeki `_bekleme_ac/_bekleme_kapat` çağrılarını silmekle olur.

**İlgili iş ya da kural kimliği:** I-342, P-035, P-028, P-053, ADR-0139.

