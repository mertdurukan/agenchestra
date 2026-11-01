# ADR-0144: Kapı ve şablonun zorladığı sekiz kural kural dosyasından çıkarılır (yukle: hook)

**Durum:** Kabul edildi

**Tarih:** 2026-11-01

**Bağlam:** Her oturum ve alt ajan açılışında `orkestra_kurallari.md` (~34 KB, ~9 bin token) yüklenir. Kuralların çoğu zaten mekanik kapıyla zorlanır ve kapı eksiği reddederken söyler. Bazı kural metinleri koddan geri kalmıştır: P-018 metni hâlâ "Geri alma" alanı ve plan `## Özet` ister; kod bunları ADR-0136 ve ADR-0126 ile kaldırmıştır. Eski metin ajanı yanıltır.

**Karar:** P-015, P-016, P-017, P-018, P-019, P-020, P-033 ve P-035 `yukle: hook` olur (mevcut mekanizma, ADR öncesi P-005/P-009/P-010 ile aynı). Tam metin panelde ve KURALLAR.md'de kalır; kural dosyasında yalnız kimlikleri listelenir. Ölçüt: kuralın ihlal modunda mekanik kapısı vardır, kapı eksiği kimlikle söyler ve gereken alanlar `sablonlar/` altındaki şablonda bulunur. Eklentideki kural tablosu hesabı: ~48,5 KB → ~38 KB (~%22; üretilen dosya ölçümü proje bazında değişir).

**Seçenekler:**

- Tüm kuralları kısa özete çevirmek: elendi, davranışı zorlayan kapısı olmayan kurallar (K-005, P-001, P-021) metne bağımlıdır.
- Yalnız kapıya güvenmek, şablona güvenmemek: elendi, eksik alan ilk plan denemesinde reddedilir ve tur kaybettirir; şablon alanı önceden verir.
- Hiçbir şey yapmamak: elendi, her çağrıda tekrar eden önbellek okuma maliyeti ve eski metin riski sürer.

**Sonuçlar:**

- Olumlu: kural dosyası küçülür; kod ile metin arasındaki sapma yükleme yolundan çıkar.
- Olumsuz: şablonu açmadan plan yazan ajan ilk denemede kapı retini görebilir. P-020 modu hook bağlama ayrıca yazar.
- Doğrulanmadı: token ve ret oranı etkisi canlı ölçülmedi; bir hafta sonra `orkestra is rapor` kapı ret sayıları karşılaştırılır. Ret oranı belirgin artarsa ilgili kural `yukle` alanı silinerek geri alınır.
- Geri alma: `kurallar/eklenti_kurallari.json` içinde sekiz kuraldan `"yukle": "hook"` satırını kaldır.

**İlgili iş ya da kural kimliği:** I-003 (TOK-6), ADR-0126, ADR-0136, P-022
