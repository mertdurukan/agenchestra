# ADR-0095: Dış kaynaklı 11 skill eklentiye sabit kopya olarak girer

**Durum:** Kabul edildi

**Tarih:** 2026-10-30

**Bağlam:**

Eklentiyi yükleyen herkesin literature-review, frontend-design, competitive-analysis, senior-architect, find-skills, architect-review, sequential-thinking, software-architecture, textual, scientific-brainstorming ve ui-ux-pro-max skill'lerini ek kurulum yapmadan kullanması istendi. Kaynak: mcp.directory (her biri tek SKILL.md; asıl depolar `source:` alanında).

**Karar:**

Her skill `plugins/orkestra/skills/<ad>/SKILL.md` olarak bayt bayt özgün kopyalanır (`/orkestra:<ad>`). Kaynak URL'si, dizin numarası ve sha256 `ayarlar/dis_skill_kaynaklari.json` içindedir; `tests/test_dis_skiller.py` varlığı, ad=dizin eşleşmesini ve özgünlüğü sınar. İndirilen içerik güvenilmeyen veri sayılıp izole klasörde taranmıştır (komut çalıştırma, sır, enjeksiyon yok). Güncelleme bilinçli yapılır: yeniden indir, kaydı ve hash'i yenile.

**Seçenekler:**

- Kullanıcıya `.claude/skills` altına curl ile kurdurmak: elendi, eklenti kuralı (skill yalnız eklenti kaynağına yazılır) ve "yükleyen herkes kullansın" hedefiyle çelişir.
- Çalışma anında mcp.directory'den çekmek: elendi, ağa ve üçüncü tarafa bağımlılık, sürüm kayması.
- Orkestra dilinde yeniden yazmak: elendi, kaynakla bağ kopar, güncelleme maliyeti artar.

**Sonuçlar:**

Olumlu: ek kurulumsuz kullanım, değişmezlik testi. Olumsuz: skill açıklamaları her oturum bağlama girer; senior-architect `scripts/` ve `references/` dosyalarına atıf yapar ama zip'te yoktu (atıflar boşta); find-skills `npx skills add` önerir, kurulum yalnız kullanıcı onayıyla yapılmalıdır. Geri alma: 11 skill dizinini ve kayıt dosyasını sil.

**İlgili:** P-022, P-015, ADR-0006
