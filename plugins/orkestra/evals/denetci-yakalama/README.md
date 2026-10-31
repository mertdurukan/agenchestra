# denetci yakalama ölçümü (I-292 P5, P-030)

**Soru:** `orkestra:denetci` bozuk işçi çıktısını kaçırıyor mu, doğru çıktıyı yanlışlıkla reddediyor mu?

**Set:** `scripts/eval_denetci.py` 60 vaka üretir (tohum 20261031, deterministik): 30 bozuk (5 kusur türü × 6: kapsam-eksik, bicim, sayi-tutarsiz, kanit-yok, talimat-ihlali) ve 30 doğru. Her vaka ayrı bir örnektir, 1 koşu.

**Koşu:** `python scripts/eval_denetci.py uret <dizin>`; her `NNN.md` ayrı bir `orkestra:denetci` ajanına okutulur, ajan tek satır döner (`NNN|onay|-` ya da `NNN|ret|<kod>`); satırlar dosyada toplanır, `python scripts/eval_denetci.py puanla <dosya>`.

**Eşik:** kaçırma ve yanlış ret için %95 güvenle üst sınır ≤ %10. 0 hatada n=30 ile Clopper-Pearson üst sınırı %9,5; 1 hatada ≈%15,6 (eşik aşılır).

**Sınırlar:** kart ve çıktı istemde gömülüdür (CLI/kart akışı yok); vakalar sentetik tek tür bir iş (envanter tablosu) üzerindedir; kusurlar belirgindir, ince kusurlar ölçülmedi. Sonuçlar: `sonuc_20261031.md`.
