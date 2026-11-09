# ADR-0175: Cursor birebir uyum programı ve Claude koruma çerçevesi

**Durum:** Önerildi (sahip onayı bekliyor)

**Tarih:** 2026-11-09

**Bağlam:**

Issue #14: Cursor sürümü Claude sürümüyle birebir değil. Hook yüzeyi 6 olaya karşı 12; `cursor_hook.py` `ask` yanıtını `deny`'e çevirir; kart yürütücüsü (`skills/is/SKILL.md`) Claude'a özgü Workflow aracını çağırır; ajan frontmatter'ı Claude'a özgüdür. Dört ilke (ayrı denetçi, yazma alanı ve onay kapıları, maliyet kaydı, paralel kart yürütme) Cursor'da yeniden kurulacak. Aynı işte Claude sürümünün çalışan dosyaları değişmemelidir; bugün bunu denetleyen bir mekanizma yok ve CI 446 test dosyasından yalnız elle seçilmiş 7'sini koşuyor.

Tam kapsam: `plugins/orkestra/cursor/KAPSAM.md`.

**Karar:**

1. Çalışma fork + küçük taslak PR ile yürür; `main`'e yalnız sahip birleştirir (issue karar 1).
2. "Birebir" üç sınıfa ayrılır: zorunlu eşdeğer (yazma/onay kapıları, ayrı denetçi, maliyet kaydı), uyarlanan (kart yürütücüsü, model profili, kurulum yolu), kabul edilen fark (Claude Pane arayüzü, kesin token sayımı, `claude://` bağlantıları).
3. Claude dosyaları (`hooks/hooks.json`, `scripts/hook.py`, `agents/*`, `skills/*`, `workflows/calistir.js`, `.claude-plugin/*`) bayt eşit kalır. PR-1 bunu sha256 listesi ve izin listesi denetimiyle CI'a bağlar. Önce çerçeve (PR-1), sonra ölçüm (PR-2), sonra ölçüme bağlı PR'lar (PR-3, PR-4, PR-5).
4. `hook.py` içine host dallanması eklenmez. Cursor davranışı yalnız `cursor_hook.py`, Cursor'a özgü dosyalar ve paylaşılan kodda `CURSOR_VERSION` / `CURSOR_PLUGIN_ROOT` koşullu en küçük eklerle yapılır.
5. Lisans: kök `LICENSE` MIT, GitHub MIT tanıyor; Cursor manifesti `UNLICENSED` yerine `MIT` olur (G15, PR-0).
6. Model eşlemesi kuralı: denetçi, işçiden düşük model olmaz. Somut eşleme PR-6'da sahibin Cursor model listesiyle yazılır.
7. IDE ölçümü (P3) yapılmadan PR-3, PR-4, PR-5 başlamaz. Ölçülmemiş her iddia belgede "doğrulanmadı" kalır.

**Seçenekler:**

- Claude hook'larını Cursor'a olduğu gibi yüklemek: reddedildi. `SubagentStart` yok, çift tetik riski (ADR-0172 çok kopya ölçümü).
- Kalıcı fork: reddedildi. İki kopya ayrışır, düzeltmeler iki yerde yapılır.
- `hook.py` içine host dallanması: reddedildi. Claude dosyasının baytlarını değiştirir; koruma çerçevesinin amacına aykırı.

**Sonuçlar:**

- Bu ADR program kararıdır; kod değişikliği içermez (PR-0). Her sonraki PR kendi ayrıntı kararı için ayrı ADR açar.
- Karar 1, 2, 3, 5, 7 sahibin açık onayına bağlıdır; onay gelene kadar durum "Önerildi" kalır.
- `plugins/orkestra/.claude-plugin/plugin.json` (ve `plugins/orkestra-ui`) hâlâ `UNLICENSED` yazıyor. Bu dosya bayt eşit listesinde olduğundan bu programın PR'ları ona dokunmaz; uyumsuzluk sahibin ayrı kararıdır.
- Geri alma: bu PR'ın revert'ü yalnız belgeleri ve manifestteki lisans alanını eski haline getirir.
