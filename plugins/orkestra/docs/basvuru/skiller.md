<!-- Bu dosya scripts/dokuman_uret.py ile üretilir; elle düzenleme. -->

# Skill'ler

Komut: `/orkestra:<ad>`. Kaynak: `skills/<ad>/SKILL.md`.

| Skill | Ne zaman | Argüman |
|---|---|---|
| `architect-review` | Master software architect specializing in modern architecture patterns, clean architecture, microservices, event-driven systems, and DDD. |  |
| `arsivle` | "Çalışma klasörünü proje arşivine taşır: sır taramasından geçirir (sır varsa kopyalamaz), db.py/.env/anahtar dosyalarını atlar, e-posta/IP maskeler, README iskeleti ekler. | "<kaynak> <hedef_kok> <konu> [--kuru]" |
| `auto` | "/auto modunu açar: kullanıcı mesajı onay yerine geçer, mevcut durum-plan-todo yazılır, iş çalışma özetine kadar onaysız yürür. |  |
| `baslat` | Bu projede orkestrayı aç — .claude/orkestra/ durum klasörünü kurar ve kısa bir kullanım özeti verir. |  |
| `caveman` | > |  |
| `caveman-commit` | > |  |
| `caveman-help` | > |  |
| `caveman-review` | > |  |
| `close` | "Sohbet bitmeden önce kullanıcının istediği her şeyi kanıta bakarak sınar ve AÇIK KALAN İŞLERİ madde madde verir; kapalı işler yalnız rapor dosyasında kalır. | "[konu filtresi, isteğe bağlı]" |
| `competitive-analysis` | Analyze competitors with feature comparison matrices, positioning analysis, and strategic implications. |  |
| `db-olcum` | "Veritabanında salt okuma ölçüm yapar: hipotezden sorgu betiği üretir, kapı denetimlerinden (VPN, saat, kimlik yeri, SQL güvenliği) geçirip çalıştırır, CSV ve bulgu raporu yazar. | "<soru ya da hipotez> [şema ...] [--ortam kopya\|prod]" |
| `defter` | Orkestra ortak defterini göster — herkesin (ana ajan, işçiler, denetçiler, perspektif) ne yaptığının son kayıtları; isteğe bağlı olarak tek bir görevin geçmişi. | "[görev id, ör. G-007] [son N]" |
| `devir` | "Sohbeti sıfır bağlamlı yeni sohbete devreden yapıştırılabilir devir belgesi üretir. |  |
| `find-skills` | Helps users discover and install agent skills when they ask questions like "how do I do X", "find a skill for X", "is there a skill that can...", or express interest in extending capabilities. |  |
| `frontend-design` | Create distinctive, production-grade frontend interfaces with high design quality. |  |
| `harita-kur` | "Projenin bilgi grafiğini kurar ya da yeniler: statik kenarlar, konu kartları, kenar listesi ve INDEX. | "[proje-kökü]" |
| `iddia-dogrula` | "İddia ya da eksiklik listesini madde madde kanıtla doğrular (DOĞRULANDI/KISMEN/ÇÜRÜTÜLDÜ/TEYİT/BELİRSİZ); rapor ayrı denetçiden geçer. | "<iddia listesi: dosya yolu (csv/md/xlsx sayfası) ya da sohbetteki maddeler>" |
| `is` | Orkestra ile bir işi yürüt — ana ajan planlar (görev kartları), işleri maliyet basamağına göre işçilere dağıtır, her çıktıyı AYRI bir denetçiden geçirir, bağımsız işleri paralel koşturur ve onaylı sonucu toplayıp getiri… | "<istek>" |
| `is-anlati` | "Bir orkestra işini (I-nnn) kanıttan 'Ne yaptım?' ve 'Nasıl yaptım?' başlıklı iki Türkçe paragrafta anlatır. | "<I-nnn \| Jira anahtarı \| klasör no \| all> [--yaz]" |
| `jira-yaz` | "Jira'ya yorum, açıklama ya da issue yazarken (Atlassian connector) metni doğru biçimde ve onayla yazar. |  |
| `literature-review` | Conduct comprehensive, systematic literature reviews using multiple academic databases (PubMed, arXiv, bioRxiv, Semantic Scholar, etc.). |  |
| `madde-senkron` | "Aynı madde kimliğini (G/A/V/K/Y/E, C1-C20, ST-xxx) taşıyan kanonik belgeleri birlikte günceller: yedek alır, birebir eşleşme yoksa hiçbir şey yazmaz. | "tara <KIMLIK...> \| uygula <plan.json> [--kuru] \| dogrula <kayit.json> \| geri-al <kayit.json>" |
| `maliyet` | Orkestra token ve maliyet raporu — her ajanın her süreç (triyaj, iş, denetim, düzeltme, sentez, perspektif…) için harcadığı giriş/çıkış/önbellek tokenı ve tahmini maliyet; görev × süreç, ajan × model, süreç ve gün kırıl… | "[gün sayısı, ör. 7]" |
| `megacave` | > |  |
| `neredeyiz` | "Durum özeti çıkarır: ne yapıyoruz, nereye geldik, sırada ne var. |  |
| `nesne-karti` | "Bir tablo, kolon ya da prosedürü anlatırken her iddiaya derece (KESİN/GÜÇLÜ/DOĞRULANMADI) ve yeniden çalıştırılabilir kaynakça yazdırır; kartı ayrı denetçiye eşletir ve `orkestra nesne-karti dogrula` ile denetler. | "<nesne: şema.tablo, şema.tablo.kolon ya da prosedür adı>" |
| `onay` | Panelde onaylanan kararları uygular — perspektif (rüya) önerileri, skill taslakları ve ajanın sorduğu kararlar. |  |
| `perspektif` | Orkestra perspektifi (hafıza bakımı) — arka planda üretilen perspektif raporunu gösterir, kullanıcının onayladığı önerileri hafıza bakımcısı ajanla uygular; istenirse perspektifi şimdi başlatır. | "[şimdi]" |
| `root-cause-first` | Evidence-driven troubleshooting and safe-change discipline for software engineering orchestrators. |  |
| `ruya` | ESKİ AD (takma ad) — "rüya" artık Perspektif'tir. | "[şimdi]" |
| `sade-excel` | "CSV/JSON tabloyu sade Excel'e çevirir: Özet + en çok 2 veri sayfası, donmuş başlık, filtre. | "<girdi.csv\|json> [ikinci.csv] --baslik \"...\" [--sutunlar \"a,b=Yeni ad\"] [--cikti ad] [--masaustu]" |
| `scientific-brainstorming` | Research ideation partner. |  |
| `senior-architect` | Comprehensive software architecture skill for designing scalable, maintainable systems using ReactJS, NextJS, NodeJS, Express, React Native, Swift, Kotlin, Flutter, Postgres, GraphQL, Go, Python. |  |
| `sequential-thinking` | Use when complex problems require systematic step-by-step reasoning with ability to revise thoughts, branch into alternative approaches, or dynamically adjust scope. |  |
| `skill-avi` | Tekrar eden işleri bul ve kayıtlı skill'e çevir — skill avcısı ajanı günlük, defter ve maliyet kayıtlarından aday çıkarır ve taslak yazar; kullanıcı onaylarsa taslak projenin .claude/skills/ klasörüne taşınır ve ayrı bi… | "[gün sayısı, ör. 14]" |
| `software-architecture` | Guide for quality focused software architecture. |  |
| `standart` | "Ekip standartlarını (PR başlığı/gövdesi, commit mesajı, dal adı, review, Jira Done yorumu) okutur ve uyumu sağlar. |  |
| `textual` | Expert guidance for building TUI (Text User Interface) applications with the Textual framework. |  |
| `toplu-etiketle` | "Yüzlerce satırı kurallara göre etiketler ya da taksonomiye eşler (paralel Haiku işçileri, betikle sayım, örneklem denetimi). | "<girdi.csv\|json\|xlsx> <neye göre etiketlenecek> [--id-sutun X] [--sayfa S --baslik-satiri N]" |
| `ui-ux-pro-max` | "UI/UX design intelligence. |  |
| `ultracave` | > |  |
| `update` | Orkestra eklentisini günceller, LLM çağırmadan: yayın klonunu GitHub'dan çeker, kurulu orkestra plugin'lerini kendi kapsamıyla günceller. |  |
| `yaklasim` | "Yanıttan önce aday yolları (skill, MCP, kod/kayıt, resmi belge) sayıp en ucuz yeterliyi seçtirir. |  |
