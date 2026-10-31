# ADR-0113: Skill anahtarı üç konumlu; sürekli açık skill oturum açılışında yüklenir

**Durum:** Kabul edildi

**Tarih:** 2026-10-31

**Bağlam:** Paneldeki skill anahtarı iki konumluydu (açık, kapalı). Kullanıcı üç konum istedi: kapalı, ihtiyaçta, sürekli açık; tıklanan konuma geçsin ve davranış değişsin. Claude Code `skillOverrides` yalnız on, name-only, user-invocable-only, off değerlerini destekler ve skill gövdesini oturum başında yükleyen resmi bir ayar yoktur (code.claude.com/docs/en/skills.md).

**Karar:**

- **Konumlar:** `kapali` (çağrı engelli), `ihtiyacta` (açık; açıklama göreve uyunca çağrılır, bugünkü "açık"), `surekli` (açık; gövde oturum açılışında bağlama yüklenir).
- **Saklama:** sürekli açık skill adları çalışma alanının `.claude/orkestra/skill_durum.json` dosyasında (`{"surekli": [...]}`). Kapalı/açık ayarı eskisi gibi `settings.local.json`'da kalır. Eski `acik` kaydı "ihtiyaçta" sayılır.
- **Yükleme:** SessionStart hook'u `surekli` skill gövdelerini bağlama ekler; toplam 20000 karakteri aşarsa kısaltır; `ORKESTRA_SKILL_SUREKLI=0` kapatır (kullanıcı kararı D1, 31.10).
- **API:** `POST /api/araclar-skill` gövdesi `{ad, durum}` ya da `{ad, konum}` kabul eder; yanıt ve liste `konum` alanı taşır, `durum` (acik|kapali) geriye uyumlu kalır.

**Seçenekler:**

- `skillOverrides`'a özel değer yazmak: elendi, resmi değerler dışında etkisi doğrulanmadı.
- Skill frontmatter'ına işaret koymak: elendi, dış kaynaklı sabit kopyayı değiştirir (ADR-0095).
- Kural dosyasına gömmek: elendi, dosya şişer, elle bakım ister.
- Her kullanıcı mesajında yüklemek: elendi, her turda bağlam maliyeti.

**Sonuçlar:**

- Olumlu: tek yerden üç davranış; eski kayıtlar bozulmaz; kapalı skill hiç yüklenmez.
- Olumsuz: sürekli açık skill bağlamı şişirir ve yanıt kurallarıyla (P-001, K-005) çakışabilir; ölçülmedi.
- Geri alma: commit geri alınır, `skill_durum.json` silinir; eski ayar etkilenmez.

**İlgili iş ya da kural kimliği:** I-294, ADR-0098, ADR-0095, P-001, K-005
