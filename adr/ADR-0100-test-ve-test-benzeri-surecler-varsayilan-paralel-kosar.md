# ADR-0100: Test ve test benzeri süreçler varsayılan paralel koşar

**Durum:** Kabul edildi

**Tarih:** 2026-10-30

**Bağlam:**

Tam test takımı seri 31 dk 48 sn sürdü (30.10.2026, 4575 test, 16 çekirdek, 11,7 GB RAM). Paralel koşucu `scripts/test_paralel.py` vardı ama yalnız elle çağrılınca çalışıyor, varsayılan işçi sayısı `cpu//2` sabitti; kart ve ön kontrol koşuları çıplak `pytest` ile seri kalıyordu. Kullanıcı: paralel koşu her test ve test benzeri süreç için orkestra davranışı olsun, doğrudan paralel başlasın, mümkün olan en çok çekirdek kullanılsın.

**Karar:**

Koşucu `test_paralel.py` çekirdek olarak korunur. `scripts/paralel_kos.py` işçi sayısını min(mantıksal çekirdek, (kullanılabilir bellek - rezerv) / işçi başı MB, üst sınır) olarak türetir; ezme: `ORKESTRA_PARALEL_N`, `ayarlar/paralel_kosu.json`, proje dosyası. Geniş çıplak pytest komutları `ork_lib.test_komutu_paralel` ile koşucuya çevrilir, hata olursa seri koşar. Test dışı bağımsız süreçler `orkestra paralel` ile paralel koşar. Kural P-041.

**Seçenekler:**

- `pytest-xdist` (`-n auto`): elendi. Yeni bağımlılık, kullanıcılarda kurulu değil; mevcut koşucu bağımlılıksız 7,0 kat verdi. xdist bu makinede ölçülmedi.
- `psutil` ile bellek okumak: elendi. Bağımlılık; stdlib ile Windows/Linux/macOS okunur.
- GNU parallel / make -j: elendi. Windows kurulumlarında yok.
- Yalnız kural, kod davranışı yok: elendi. Ajanlar seri komut yazmaya devam eder.

**Sonuçlar:**

Olumlu: tam takım `-n 16` ile 273 sn (7,0 kat), yeni düşen yok; her kullanıcı varsayılan paralel koşar. Olumsuz: bellek dar makinede işçi azalır; ortak geçici ev kullanan yeni testler çakışabilir (P5 ölçer). Geri alma: git revert, `ORKESTRA_PARALEL=0` ya da `ORKESTRA_PARALEL_N=1`.

**İlgili iş:** I-265
