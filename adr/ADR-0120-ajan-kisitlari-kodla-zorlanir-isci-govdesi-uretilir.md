# ADR-0120: Ajan kısıtları kodla zorlanır, işçi gövdesi tek kaynaktan üretilir

**Durum:** Kabul edildi

**Tarih:** 2026-10-31

**Bağlam:**

12 ajanın incelemesinde (I-292) şunlar çıktı: `isci-t1..t4` gövdeleri ilk satır dışında aynı; ret kodu sayısı, skill eşiği ve model adı ajan metinlerinde elle yazılı ve çelişiyor; `arastirmaci` "yalnız SELECT", `perspektif-ajani` ve `skill-avcisi` "tek dosya yazar", `denetci` "yalnız kart çıktısı" kısıtları yalnız prompt'ta. Claude Code ajan dosyasında include/extends yok (code.claude.com/docs/en/sub-agents); plugin ajanında `hooks` ve `permissionMode` yok sayılır.

**Karar:**

(1) İşçi gövdesi `agents/_kaynak/` altında tek dosyada tutulur; `isci-t1..t4.md` bir betikle üretilir, basamak alanları `ayarlar/model_politikasi.json`'dan gelir, "üretilen = depodaki" testi eşitliği korur. (2) Ajan metinlerindeki sayı, kod ve model adı kaynağından türetilir veya metinden çıkarılır; metin-kaynak eşitliği testi vardır. (3) Ajan türüne göre Bash/yazma kapsamı eklentinin PreToolUse hook'unda (`izin_politikasi`) kodla zorlanır; her kısıt için ihlal vakasını reddeden test yazılır (P-032).

**Seçenekler:**

- Elenen: protokolü skill'e taşıyıp işçiye okutmak. İşçi okumayı atlayabilir; `skills:` önyükleme alanı ayrıca denenir (I-292 P2), tutarsa üretim betiğinin yerine geçer.
- Elenen: `arastirmaci`'dan Bash'i kaldırıp postgres MCP'ye geçmek. MCP bu ortamda bağlanamadı.
- Elenen: kısıtları yalnız prompt'ta bırakmak. Yoruma ve manipülasyona açıktır.

**Sonuçlar:**

Olumlu: tek gerçek kaynak, kısıtlar test edilebilir. Olumsuz: üretilen dosyalar elle düzenlenemez; yanlış pozitif kapı ajanı kilitleyebilir. Geri alma: üretilen dosyaları git'ten geri yükle, kapıyı ayardan kapat.

**İlgili iş:** I-292, P-006, P-022, P-030, P-032
