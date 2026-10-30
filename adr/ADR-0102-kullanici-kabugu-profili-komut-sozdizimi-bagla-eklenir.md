# ADR-0102: Kullanıcıya verilen komut hedef kabuğun sözdizimiyle yazılır

**Durum:** Kabul edildi

**Tarih:** 2026-10-30

**Bağlam:**

Ajan kullanıcıya terminalde çalıştırması için komut verirken hedef kabuğun sözdizimini bilmiyor ve bash alışkanlığıyla yazıyor. 30.10.2026'da Windows PowerShell 5.1'de `&&` ayrıştırılamadı (`The token '&&' is not a valid statement separator in this version.`). Kullanıcı bunun sürekli yaşandığını söyledi (sıklık günlükten ölçülmedi). Eklentide `standartlar/` ve `scripts/` içinde kabuk sözdizimi bilgisi taşıyan hiçbir şey yok (0 eşleşme). Ajan süreci kullanıcının terminalini göremez.

**Karar:**

Davranış eklenti katmanında, model çağırmadan zorlanır: (1) Kural P-043 (katman plugin). (2) Profil metni tek kaynaktan, `standartlar/kabuk_profili.md`; profil adı ayardan gelir (`ayarlar/kabuk_profili.json`: `profil` auto | powershell5 | powershell7 | bash | cmd; auto = Windows'ta `powershell5`, diğerlerinde `bash`; proje ezmesi `.claude/orkestra/kabuk_profili.json`). (3) `scripts/kabuk_profili.py`: oturumun ilk kullanıcı mesajında ve komut ya da terminal anan mesajlarda `ORKESTRA KABUK` satırı bağlama eklenir. (4) Stop'ta `powershell`/`bash` etiketli kod bloğunda profilde yasak kalıp varsa günlüğe `kural_ihlal / kabuk_sozdizimi` yazılır; kip `golge`, engellemez (P-028). Kapatma: `ORKESTRA_KABUK_PROFILI=0`.

**Seçenekler:**

- Yalnız skill ya da kural metni: elendi. Çağrısı ajanın hatırlamasına bağlı, tam bu hatada unutulan şey.
- MCP sunucusu: elendi. Dış sistem erişimi yok; yeni süreç ve bağlantı hatası riski ekler.
- Yalnız Stop'ta sonradan yakalamak: elendi. K-006: hata üretilirken önlenmeli; tarama yalnız ölçüm ve güvenlik ağı.
- Kullanıcı kabuğunu çalışma anında keşfetmek: elendi. Ajan süreci terminali göremez; ortam değişkenleri araç kabuğunu gösterir, kullanıcı terminalini değil.

**Sonuçlar:**

Olumlu: komut yazılmadan önce profil bağlamda; ihlal ölçülür; her kullanıcı aynı davranışı alır. Olumsuz: auto profili yanlış olabilir (ör. `pwsh` 7 kullanan kullanıcı en kısıtlı kurala tabi kalır); tarama yanlış pozitif verebilir. Geri alma: `ORKESTRA_KABUK_PROFILI=0`, ayarda `mod: kapali` ya da `orkestra kural kapat P-043`.

**İlgili iş:** I-270, P-043, K-006, ADR-0101, P-028
