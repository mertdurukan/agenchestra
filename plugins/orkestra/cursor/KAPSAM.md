# Cursor birebir uyum: uygulayıcı için tam kapsam

Kaynak: [issue #14](https://github.com/mertdurukan/agenchestra/issues/14) gövdesi (04.11.2026 taslağı) ve yorumundaki karar önerileri (09.11.2026). Karar kaydı: `adr/ADR-0175-cursor-birebir-uyum-programi-claude-koruma-cercevesi.md`.

Durum (09.11.2026): PR-0 ve PR-1 açıldı. PR-2…PR-8 başlamadı. Sahip onayı bekleyen kararlar aşağıdadır; "öneri" kolonu başlangıç varsayımıdır.

## 1. Amaç

Cursor sürümü Claude sürümüyle birebir değil: hook yüzeyi 6 olaya karşı 12, `ask` yanıtı `deny`'e düşüyor, Workflow aracı Claude'a özgü, ajan frontmatter'ı Claude'a özgü. Dört değişmez ilke Cursor'da yeniden kurulur:

1. Ayrı denetçi (işi yapan kendi denetçisi olamaz).
2. Yazma alanı ve onay kapıları.
3. Maliyet kaydı.
4. Paralel kart yürütme.

## 2. Kararlar

| # | Konu | Öneri (09.11.2026) | Durum |
|---|------|--------------------|-------|
| 1 | Dal ve süreç | Fork + taslak PR. PR'lar küçük; main'e yalnız sahip birleştirir. | Sahip teyidi bekliyor |
| 2 | "Birebir" tanımı (bölüm 3) | Olduğu gibi kabul. | Sahip teyidi bekliyor |
| 3 | Model eşlemesi | Denetçi, işçiden düşük model olmasın. Somut T1–T4 eşlemesi PR-6'da sahibin model listesiyle. | Sahip teyidi + model listesi bekliyor |
| 4 | Lisans | `.cursor-plugin/plugin.json` içindeki `UNLICENSED` MIT'e çevrilir (G15, PR-0). | PR-0'da uygulandı; teyit bekliyor |
| 5 | IDE ölçümü (P3) | Canlı Cursor oturumu + test projesi. PR-3, PR-4, PR-5 ölçümden önce başlamaz. | Sahip teyidi bekliyor |

## 3. "Birebir" tanımı

- **Zorunlu eşdeğer:** yazma/onay kapıları, işi yapanın kendi denetçisi olamaması, maliyet kaydı.
- **Uyarlanan:** kart yürütücüsü (Workflow yerine Task), model profili, kurulum yolu.
- **Kabul edilen fark:** Claude Pane arayüzü, kesin token sayımı, `claude://` bağlantıları.

## 4. Claude'u koruma kuralları (her PR için bağlayıcı)

Makine tarafından denetlenen sürümü: `plugins/orkestra/cursor/koruma_kurallari.json` (PR-1). Okunur özet:

- **Bayt eşit kalacak:** `plugins/orkestra/hooks/hooks.json`, `plugins/orkestra/scripts/hook.py`, `plugins/orkestra/agents/*`, `plugins/orkestra/skills/*`, `plugins/orkestra/workflows/calistir.js`, `plugins/orkestra/.claude-plugin/*`, `.claude-plugin/*`. `hook.py` içine host dallanması eklenmez.
- **Yazma izin listesi:** `plugins/orkestra/cursor/`, `plugins/orkestra/.cursor-plugin/`, `.cursor-plugin/`, `plugins/orkestra/hooks/cursor-hooks.json`, `plugins/orkestra/scripts/cursor_*`, `araclar/cursor_*`, `plugins/orkestra/ayarlar/model_politikasi.cursor.json`, `plugins/orkestra/tests/test_cursor_*`, `adr/`, belgeler.
- **Paylaşılan kod** (bayt eşit listesinde olmayan: `scripts/doktor.py`, `scripts/panel.py`, `scripts/ozet.py`, model politikasını okuyan kod): en küçük ek, yalnız Cursor ortamında (`CURSOR_VERSION`, `CURSOR_PLUGIN_ROOT`) çalışır, PR gövdesinde ayrıca işaretlenir; Claude çıktısı altın kayıtlarla bayt eşit doğrulanır.
- Cursor için `skills/` ve `agents/` bir betikle üretilir, manifest bunları gösterir; Claude klasörleri okunur, yazılmaz.
- Her PR'da geri alma adımı vardır (tek revert ile Cursor katmanı çıkar).
- Elenen seçenekler: Claude hook'larını olduğu gibi yüklemek (SubagentStart yok, çift tetik riski), kalıcı fork, `hook.py` içine host dallanması.

## 5. Boşluklar G1–G16

Her madde: hedef / mevcut / yapılacak (PR).

| G | Konu (PR) | Mevcut | Yapılacak |
|---|-----------|--------|-----------|
| G1 | Kurulum rehberi ve betiği (PR-7) | Kurulum betiği yalnız Claude komutuna bağlı; README çelişkili. | `araclar/cursor_kur.py` (`--kuru`, `--kur`, `--kaldir`) ve README Cursor bölümü. |
| G2 | Hook yüzeyi ve `failClosed` (PR-3) | Cursor hook dosyasında 6 olay var; `subagentStart`, `beforeShell`, `beforeMCP`, `afterFileEdit`, `preCompact` yok; `failClosed` yok (ölçüm 04.11.2026). | Olaylar ve matcher eklenir, koruma hook'larına `failClosed` verilir. Güvenlik incelemesi (P15) PR-3'ten önce. |
| G3 | Gerçek `ask` (PR-3) | Adaptör `ask`'ı `deny`'e çevirir (`cursor_hook.py:86`; 019 ölçümü CLI ve TUI'de, IDE'de sürülemedi). `ORKESTRA_CURSOR_ASK` varsayılanı `deny`. | Kabuk ve MCP çağrılarında `ask` eşlenir; yazma/silmede `deny` + açıklama. Belge `ask`'ın yalnız `beforeShellExecution` ve `beforeMCPExecution` için uygulandığını söylüyor; IDE'de ölçülmedi (doğrulanmadı). |
| G4 | Maliyet kaydı (PR-6) | Hook yükünde token alanı belgede yok; defter Claude günlüğünden beslenir. | Host etiketi ve "tahmini" etiketli kayıt; kesin sayaç vaat edilmez. Token alanının yokluğu doğrulanmadı. |
| G5 | Model profili (PR-6) | Politika `haiku`, `sonnet`, `opus` adlarını sabit yazar. | `model_politikasi.cursor.json` yeni dosya; karar 3'e bağlı. |
| G6 | Cursor içi görünüm (PR-8) | HTML panel var; `niyet.py:65` `claude://` bağlantısı üretir. | Cursor host'unda `claude://` ve kota çıktısı gizlenir; Canvas sonraki aşamaya kalır. |
| G7 | CLI PATH (PR-7) | `bin` klasörü PATH'te değil. | `cursor_kur.py` PATH ekler, doktor denetler. (ADR-0172 komut yazımı PATH'siz çalışır; kapsam PR-7'de netleşir.) |
| G8 | IDE'de uçtan uca ölçüm (PR-2) | Yalnız CLI ve TUI ölçüldü (taşınabilirlik ~%83). | Yalnız günlük yazan hook'larla P3 ölçümü; sonuçlar `ide_olcum` belgesinde ve sözleşme testlerinde. |
| G9 | Sahibe teslim paketi (PR-0) | Sözlü analiz. | Bu belge, PR şablonu (`PR_SABLONU.md`), ADR-0175. |
| G10 | Yerel kopya senkronu (PR-7) | Yerel kopya 13 skill / 12 ajan; kaynakta 42 skill / 12 ajan. | Kurulum betiği sürümle eşitler, sürüm kaydı tutar. |
| G11 | Cursor kart yürütücüsü (PR-5) | `skills/is/SKILL.md:66` Claude'a özgü Workflow aracını çağırır. | Task tabanlı, üretilmiş skill; kart sırası CLI'dan gelir. Task paralelliği doğrulanmadı, P3'te ölçülür. |
| G12 | Ayrı denetçi kimlik zorlaması (PR-4) | `hook.py:247` kimliği `agent_id`'den okur; Cursor yükünde bu alanın bulunduğu doğrulanmadı. | `subagentStart` durum kaydı ve tek kullanımlık belirteç (host'tan bağımsız, CLI tarafında). |
| G13 | Ajan araç ve model kısıtı (PR-5) | Ajanlar Claude'a özgü frontmatter taşır. | Üretilmiş Cursor ajanları; kısıt hook'ta uygulanır. Cursor'un yalnız `name`/`description` okuduğu ve manifestte ayrı yolun varsayılan taramayı değiştirdiği IDE'de ölçülmedi (doğrulanmadı). |
| G14 | Çift yükleme önleme (PR-7) | Host koruması ve doktor denetimi yok. | Doktor çift yüklemeyi tespit eder; sayaçlar olay kimliğiyle tekilleştirilir. Çift tetik doğrulanmadı. (ADR-0172 tek uçuş mekanizması kapsamı etkiler.) |
| G15 | Lisans, sürüm, Marketplace (PR-0, PR-8) | Manifest `UNLICENSED`; kök `LICENSE` MIT. | PR-0: manifest MIT. PR-8: gönderime hazır manifest. Gönderim en sonda, ayrı onayla. |
| G16 | Hook gecikme bütçesi (PR-2, PR-7) | Ölçülmedi (doğrulanmadı). | P3'te p50/p95 ölçülür, bütçe doktora yazılır. |

## 6. PR sırası

| PR | İçerik | G |
|----|--------|---|
| PR-0 | Belge, ADR, bildirim, lisans | G9, G15 (lisans) |
| PR-1 | Claude koruma çerçevesi (sha256 listesi, bayt eşitliği ve izin listesi denetimi, CI) | koruma |
| PR-2 | IDE ölçüm donanımı ve sonuçları | G8, G16 |
| PR-3 | Hook yüzeyi ve `ask` (P15 güvenlik incelemesi önce) | G2, G3 |
| PR-4 | Kimlik ve denetçi belirteci | G12 |
| PR-5 | Cursor katmanı üretici (skills ve agents) | G11, G13 |
| PR-6 | Model ve maliyet | G4, G5 |
| PR-7 | Kurulum ve doktor, geri alma, sürüm izleme | G1, G7, G10, G14, G16 |
| PR-8 | Panel ve belge kalanı | G6, G15 (gönderim hazırlığı) |

Bağımlılık: PR-3, PR-4, PR-5 → PR-2 ölçüm sonucu. PR-1, PR-2'den önce bitmeli. Marketplace gönderimi hepsinden sonra, ayrı onayla.

## 7. Taban çizgisi ve CI

- Claude test taban çizgisi (issue, main `a826d54`, Windows, TEMP altında): 446 test dosyası, 1 düşen (`test_bagsiz_kabuk_yazimi.py::GeciciYol::test_gecici_yol_mu`), 611 s (doğrulanmadı). Resmi taban çizgisi TEMP dışında, üç işletim sisteminde yeniden alınacak.
- `.github/workflows/orkestra-test.yml` yalnız elle yazılmış 7 test dosyasını koşuyor; yeni test otomatik koşmaz. PR-1 yeni `cursor-koruma` iş akışıyla `test_cursor_*` dosyalarını glob ile koşturur.
- Main CI 09.11.2026 itibarıyla kırmızı (`gh run list`, son 4 koşu `failure`) ve bu işten bağımsızdır: `test_tasinabilirlik` ve `test_cli_baslatici::test_python3_yoksa_python` (issue notu). Bu işin PR'ları bu iki hatayı ayırarak raporlanır.

## 8. Doğrulanmayanlar (kod yazmadan ölç)

1. `ask`'ın `preToolUse`'ta uygulanmaması.
2. Hook yükünde `agent_id` yokluğu.
3. Ajan frontmatter'ının yalnız `name`/`description` okunması.
4. Token alanı yokluğu.
5. Çift yüklemede çift tetik (ADR-0172 üç kopya için ölçtü; Claude önbelleği + yerel kopya dışındaki yollar ölçülmedi).
6. Manifest `skills`/`agents` yolunun varsayılan taramayı değiştirmesi.
7. Task paralelliği.
8. Hook gecikmesinin payı.
