# ADR-0038: Atlassian MCP kapısı sunucu kimliğine göre (P-010)

**Durum:** Kabul edildi

**Tarih:** 22.10.2026

**Bağlam:**

P-010 Jira yazmayı onaya bağlar; kapı `ayarlar/izin_politikasi.json` içinde araç adındaki "atlassian" ya da "jira" sözcüğüne bakıyordu. Atlassian MCP sunucusu `mcp__73d9f9eb-9d44-4ce4-b615-490c4b090ae4__` önekiyle geldiğinden `executeWrite`, `executeDestructive`, `createConfluenceContent` ve `updateConfluenceContent` kapıya düşmeden `allow` alıyordu (`orkestra izin sina`, 22.10.2026 22:56). Kullanıcı yalnız GitHub ve Jira yazmanın sorulmasını istedi.

**Karar:**

Sunucu kimliğiyle (`mcp__73d9f9eb-…__`) eşleşen bir kayıt eklenir; okuma dışı her araç `ask` alır. Kimlik başka kurulumda farklı olabileceğinden `execute(Write|Destructive)` son ekiyle kimlikten bağımsız ikinci kayıt da eklenir. `executeRead` ve `discover` okuma sayılır. Confluence yazma (`createConfluenceContent`, `updateConfluenceContent`) Jira yazma gibi onaylı kapıda kalır (kullanıcı kararı, 22.10.2026).

**Seçenekler:**

- **Yalnız adla eşleşen desen:** elendi, UUID önekli sunucu kaçıyor.
- **Her araç adını tek tek listelemek:** elendi, yeni araç kapı dışı kalır.
- **Confluence'ı kapı dışı bırakmak:** elendi, kullanıcı kapıda kalsın dedi.

**Sonuçlar:**

- **Olumlu:** Jira ve Confluence yazma sorulur; sunucuya eklenen yeni yazma aracı kendiliğinden kapıdadır.
- **Olumsuz:** yeni bir okuma aracı okuma desenine girmezse gereksiz `ask` alır (güvenli yön).
- **Geri alma:** `ayarlar/izin_politikasi.json` içindeki iki kaydı sil, `git revert`.

**İlgili iş:** I-062; kurallar P-010, P-022
