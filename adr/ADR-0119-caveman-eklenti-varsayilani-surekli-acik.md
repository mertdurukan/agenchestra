# ADR-0119: Eklenti varsayılan sürekli açık skill listesi; caveman varsayılan

**Durum:** Kabul edildi

**Tarih:** 2026-10-31

**Bağlam:** Caveman skill'i yalnız /caveman ile açılıyordu. Kullanıcı her sohbette ve orkestrayı kullanan her projede otomatik çalışmasını istedi. ADR-0113'te sürekli açık kaydı yalnız projenin `skill_durum.json` dosyasındaydı; eklenti varsayılanı yoktu. DemoRoot projesine yazmak P-022'ye aykırıydı.

**Karar:**

- **Varsayılan:** `ayarlar/skill_surekli.json` içindeki `varsayilan` listesi (şimdilik `orkestra:caveman`) her projede sürekli açık sayılır.
- **Proje ezmesi:** proje `skill_durum.json` içinde `haric` listesiyle bir varsayılanı kapatır; `surekli` listesi varsayılan dışı adları tutar. Panel anahtarı (`konum_ata`) ikisini birlikte yazar.
- **Kapatma:** `ORKESTRA_SKILL_SUREKLI=0` tüm sürekli yüklemeyi kapatır.

**Seçenekler:**

- Her projeye `skill_durum.json` yazmak: elendi, P-022 (genel davranış eklentide) ve yeni projede unutulur.
- Skill gövdesini KURALLAR.md'ye gömmek: elendi, ADR-0113 aynı gerekçeyle eledi.
- Skill frontmatter'ına işaret: elendi, dış kaynaklı kopyayı değiştirir (ADR-0095).

**Sonuçlar:**

- Olumlu: tüm projelerde tek ayarla açılır; proje tek satırla kapatır; mevcut kayıtlar bozulmaz.
- Olumsuz: her oturumda caveman gövdesi bağlama girer (token maliyeti); P-001 ve K-005 ile çakışması ölçülmedi.
- Geri alma: `varsayilan` listesi boşaltılır ya da commit geri alınır.

**İlgili iş ya da kural kimliği:** ADR-0113, ADR-0095, P-022, P-001, K-005
