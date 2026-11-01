# ADR-0134: Kritik SessionStart bağlamı bağımsız ikinci hook'ta üretilir

**Durum:** Kabul edildi

**Tarih:** 01.11.2026

**Bağlam:**

- Caveman ADR-0119 ile her projede sürekli açık, ama 31.10.2026'dan beri istek kaydı olan 34 oturumun 23'ünde SessionStart bağlam kaydı yok.
- SessionStart hook'u 10 sn zaman aşımıyla koşar (hooks/hooks.json:5); 57 ölçümün medyanı 7,8 sn, worktree'de `durum_devral.planla` tek başına 48 sn.
- Zaman aşımında hook bağlamı yazmadan ölür; kurallar, caveman ve açık iş bilgisi birlikte kaybolur.

**Karar:**

- Kritik bağlam (sürekli açık skill gövdeleri ve kural yolu satırı) hooks.json'da ayrı ikinci SessionStart komutuyla üretilir; ana hook yavaşlasa da kendi 10 sn'si içinde teslim edilir.
- Kritik hook kendi tur=baglam_kritik kaydını yazar (sürüm etiketli); teslim oranı bundan hesaplanır.
- Ana hook'a hook_basla kaydı, bölüm süreleri ve 10 sn üstü gölge uyarısı eklenir.
- `devral_ipucu` dosya içeriği okumaz; yalnız dosya adı ve isler.json anahtarı karşılaştırır (tam karşılaştırma `orkestra durum devral` komutunda kalır).

**Seçenekler:**

- Elenen: hook zaman aşımını 10 sn'den 60 sn'ye çıkarmak. Neden elendi: her oturum açılışını yavaşlatır, kök nedeni gizler ve zaman aşımı değeri ürün sınırıdır.
- Elenen: ana hook içinde daemon iş parçacığı + 6 sn bütçe. Neden elendi: yan etkili bölümleri yarıda keser, ikinci hook aynı garantiyi sade verir.
- Elenen: yalnız `devral_ipucu`'yu hızlandırmak. Neden elendi: bir sonraki yavaş bölüm aynı kaybı üretir; teslim garantisi olmaz.
- Elenen: caveman'ı UserPromptSubmit'e taşımak. Neden elendi: her turda tekrar yükler, ADR-0113 oturum başı yükleme kararını bozar.

**Sonuçlar:**

- Olumlu: yavaşlık kritik bağlamı bir daha silemez; bölüm süreleri ölçülür.
- Olumsuz: ikinci python açılışı (~1 sn) ve iki hook çıktısının birleşmesi canlı oturumda doğrulanmalıdır.
- Geri alma: hooks.json'dan ikinci komut silinir, skill çağrısı ana hook'a döner (tek commit).

**İlgili iş ya da kural kimliği:** I-314, ADR-0113, ADR-0119, P-022, K-006


**Not:** Aynı karar McD projesinde ADR-0132 olarak kayıtlıdır (I-314).
