# ADR-0117: Otomatik commit, test dosyasının izlenmeyen modülünü birlikte alır

**Durum:** Kabul edildi

**Tarih:** 2026-10-31

**Bağlam:**

30.10.2026'da `tests/test_paralel_kos.py` otomatik commit'lendi (`f1f14654`), ama `import paralel_calistir` ettiği `scripts/paralel_calistir.py` ile `scripts/komutlar/paralel.py` izlenmeyen kaldı. Temiz kopyada ve `ajan-best-in-class` dalında test `ModuleNotFoundError` verdi. Modüller büyük olasılıkla kabukla yazıldı; kabuk sonrası otomatik commit yalnız `.md`/`.json` alır (`oto_commit.py`, `klasorleri_commit`). Bu kanıtlanmadı, tahmindir.

**Karar:**

`oto_commit.py` bir `test_*.py` dosyasını commit ederken, o dosyanın import ettiği ve depoda hâlâ izlenmeyen `.py` modüllerini aynı commit'e ekler (`eslik_moduller`). Yalnız adı import edilen modüle eşit, izlenmeyen dosyalar alınır; başka dosya alınmaz.

**Seçenekler:**

- Yalnız eksik dosyaları elle eklemek: elendi. Tek seferlik, yeniden oluşmayı önlemez.
- Kabuk sonrası tüm `.py` değişikliklerini commit etmek: elendi. Paylaşılan çalışma klasöründe başka oturumun yarım işini sürükler.
- `is kapat`/commit kapısı (testin izlenmeyen modül import ettiğini reddetmek): ertelendi. Sonradan yakalar; hook düzeltmesi sorunu oluştuğu yerde önler.

**Sonuçlar:**

Olumlu: test ile modülü aynı commit'te gider. Olumsuz: yalnız Edit/Write ile commit edilen test dosyasını kapsar; kabukla yazılan testi ve `from paket.modul` biçimini kapsamaz. Geri alma: `git revert`, ya da `ORKESTRA_OTO_COMMIT` kapatılır.

**İlgili iş:** I-265, ADR-0100
