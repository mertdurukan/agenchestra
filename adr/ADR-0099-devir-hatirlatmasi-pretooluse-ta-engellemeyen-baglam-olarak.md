# ADR-0099: Devir hatırlatması PreToolUse'ta engellemeyen bağlam olarak başlar

**Durum:** Önerildi

**Tarih:** 2026-10-30

**Bağlam:**

McD'nin zaman.jsonl kaydına göre (14–30.10.2026) araç çağrılarının %82'si ana ajanda, 242 işin 90'ında alt ajan yok. Bir turda üç ya da daha fazla Edit/Write yapılan 318 turun 163'ünde alt ajan çalışmadı.

KURALLAR.md satır 11–24 devri yalnız tavsiye olarak tarif eder; hook'larda devir kararını hatırlatan ya da izleyen kod yok.

**Karar:**

- **Tetikleyici:** ana ajanın bir istekte üçüncü ayrı dosyaya Edit/Write yapması; o turda alt ajan çalıştıysa hatırlatma yok.
- **Etki:** `hook.py` `pre_tool_use` içinde tur başına tek hatırlatma, ek bağlam olarak; işi engellemez.
- **Ayar:** eşik, kip ve metin `ayarlar/devir_hatirlatma.json`'da; proje durum klasöründeki dosya ezer.
- **Ölçüm:** `scripts/devir_olcum.py` aynı sayıyı zaman.jsonl'dan üretir; düzeltme sonrası en az 100 tur tabanla karşılaştırılır.

**Seçenekler:**

- **Engelleme (`deny`):** elendi; devirsiz turların bir kısmı muaf iş (KURALLAR.md satır 12–17), engelleme meşru işi durdurur. Ölçümle yanlış pozitif oranı bilinmeden P-028 buna izin vermez.
- **Stop hook'unda sonradan denetim:** elendi; iş bittikten sonra devir kaçırılmıştır, K-006 sonradan yakalamayı çözüm saymaz.
- **Yalnız kural metnini sertleştirmek:** elendi; kural bugün de var ve turların %51'inde (çok dosyalı) uygulanmıyor.
- **Ayrı hooks.json girdisi:** elendi; her araç çağrısında ikinci Python süreci başlatır.

**Sonuçlar:**

- **Olumlu:** devir kararı, işin yapıldığı araç çağrısında hatırlatılır; etkisi aynı betikle ölçülür.
- **Olumsuz:** hatırlatma yok sayılabilir; meşru muaf işte gürültü yapar (tur başına tek hatırlatma ile sınırlı).
- **Geri alma:** `hook.py`'deki tek çağrı satırı ve `ayarlar/devir_hatirlatma.json` kaldırılır.
- **Sonraki karar:** ölçümde oran artmazsa kip değişikliği ayrı ADR ile alınır.

**İlgili iş:** I-263
