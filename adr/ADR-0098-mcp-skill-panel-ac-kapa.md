# ADR-0098: Orkestra panelinde MCP ve skill aç/kapat

**Durum:** Kabul edildi

**Tarih:** 2026-10-30

**Bağlam:** I-253 ile 19 hazır MCP kayıt defterine alındı (DemoRoot ADR-0097). Kullanıcı hangi MCP ve skill'in açık olacağını orkestra web arayüzünden, tek sayfada seçmek istedi. Kayıt değiştirmek için terminal gerekiyordu.

**Karar:**

- **Sayfa:** `#/araclar` (assets/app.js, "Araçlar"); MCP ve Skill sekmeleri, arama, her satırda anahtar.
- **MCP:** "açık" = kullanıcı kapsamında kayıtlı (`claude mcp add --scope user`, mevcut `komutlar/mcp.py kur`); "kapalı" = kayıt silinir (`claude mcp remove`). Yalnız `ayarlar/mcp_kimlik.json` adları kabul edilir; `~/.claude.json` yalnız okunur; yanıtta sır değeri yoktur. Sonuç kayıt yeniden okunarak doğrulanır.
- **Skill:** seçili çalışma alanının `.claude/settings.local.json` dosyasına yazılır (atomik, yedekli, bozuk JSON'a dokunulmaz). Kullanıcı/proje skill'i `skillOverrides[ad]="off"` ile listeden çıkar; eklenti skill'i `permissions.deny` içine `Skill(orkestra:ad)` ile yalnız çağrıya kapanır (deney: skill_deney_20261030.md; skillOverrides eklenti skill'inde etkisizdir).
- **API:** `POST /api/araclar-mcp` ve `/api/araclar-skill`; `X-Orkestra` başlığı, yerel Host, küçük gövde zorunlu.

**Seçenekler:**

- **`disabledMcpServers` yazmak:** elendi; belgelenmemiş iç alan, sürümle bozulabilir.
- **19 MCP'yi `.mcp.json`'a koymak:** elendi; proje başına çoğalır, kullanıcı düzeyi kayıtla çelişir.
- **Ayrı HTTP sunucusu:** elendi; panelde hazır yazma koruması (başlık, Host) varken ikinci yüzey açar.
- **Klasik sayfa (`araclar.html`):** elendi; ana arayüz SPA'dır, ikinci biçim bakım yükü.

**Sonuçlar:**

- **Olumlu:** tek sayfada 19 MCP + 38 skill; testler: araclar_mcp 10, araclar_skill 10, panel uçları 13, duman 8.
- **Olumsuz:** MCP değişikliği yeni oturumda etkili olur; eklenti skill'i listede görünmeye devam eder; skill ayarı çalışma alanı başınadır.
- **Geri alma:** panel uçlarını ve `app.js` bölümü 10c'yi kaldırmak yeterli; MCP kayıtları `orkestra mcp kur` ile yönetilmeye devam eder.

**İlgili iş:** I-254 (DemoRoot); DemoRoot ADR-0097 (MCP kaydı), P-030, P-033; eklenti ADR-0097 (ADR hedef depo). DemoRoot'deki ilk kayıt bu ADR'ye taşındı.
