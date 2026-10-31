# ADR-0117: Otomatik commit, test dosyasının izlenmeyen modülünü birlikte alır

**Durum:** Kabul edildi

**Tarih:** 2026-10-31

**Bağlam:**

30.10.2026'da `tests/test_paralel_kos.py` otomatik commit'lendi (`f1f14654`), ama `import paralel_calistir` ettiği `scripts/paralel_calistir.py` ile `scripts/komutlar/paralel.py` izlenmeyen kaldı. Temiz kopyada ve `ajan-best-in-class` dalında test `ModuleNotFoundError` verdi. Modüller büyük olasılıkla kabukla yazıldı; kabuk sonrası otomatik commit yalnız `.md`/`.json` alır (`oto_commit.py`, `klasorleri_commit`). Bu kanıtlanmadı, tahmindir.

**Karar:**

İki yol, aynı ilke: testin import ettiği izlenmeyen `.py` modülü testle birlikte commit'lenir.

- Edit/Write yolu: `oto_commit.py` bir `test_*.py` dosyasını commit ederken, import ettiği izlenmeyen `.py` modüllerini aynı commit'e ekler (`eslik_moduller`, AST ile; `import a`, `from a.b import c`).
- Kabuk yolu (I-301): `kabuk_commit` sonunda `izlenmeyen_test_modulleri`. Her izlenmeyen `.py` için izlenen `*test_*.py` içinde `import`/`from` satırı aranır (`git grep`); `from paket import modul` biçimi de eşleşir. Modül, eşleşen testin `tests` klasörünün üstündeki eklenti kökünün altındaysa yalnız o dosya pathspec ile commit edilir. Yorum, dizge, başka kökteki aynı adlı dosya ve izlenmeyen `test_*.py` alınmaz.

**Seçenekler:**

- Yalnız eksik dosyaları elle eklemek: elendi. Tek seferlik, yeniden oluşmayı önlemez.
- Kabuk sonrası tüm `.py` değişikliklerini commit etmek: elendi. Paylaşılan çalışma klasöründe başka oturumun yarım işini sürükler.
- `is kapat`/commit kapısı (testin izlenmeyen modül import ettiğini reddetmek): ertelendi. Sonradan yakalar; hook düzeltmesi sorunu oluştuğu yerde önler.

**Sonuçlar:**

Olumlu: test ile modülü aynı commit'te gider; kabuk yolu dahil. 15 test geçer (`tests/test_oto_commit.py`), kabuk yolu için pozitif, negatif, izlenen test yok ve kapalı anahtar vakaları var.

Olumsuz ve kapsam dışı: göreli import (`from . import x`) kabuk yolunda ve Edit/Write yolunda eşleşmez; kabukla yazılan test dosyasının kendisi hâlâ otomatik commit'lenmez; testi modülsüz commit'ten reddeden çalışma zamanı kapısı yoktur (ertelendi, gerekirse P-028 gereği gölge modda ayrı işle açılır). Her Bash çağrısına yalnız izlenmeyen `.py` varsa ek `git grep` maliyeti biner.

Geri alma: `git revert` ya da `ORKESTRA_OTO_COMMIT` kapatılır.

**İlgili iş:** I-265, I-301, ADR-0100
