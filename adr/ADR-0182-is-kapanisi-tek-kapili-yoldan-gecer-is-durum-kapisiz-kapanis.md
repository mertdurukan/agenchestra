# ADR-0182: Iş kapanışı tek kapılı yoldan geçer; is_durum kapısız kapanışı reddeder

**Durum:** Kabul edildi

**Tarih:** 2026-11-12

**Bağlam:**

İş kapanışının üç yolu vardı: CLI (`orkestra is kapat`), panel ve bakım. SessionStart hook'u ise `hook.py` içinde `is_durum` ile doğrudan kapatıyor, `kapat_uygula` kapılarını (özet, ADR, kapı 3, teslim) atlıyordu. `durum:kapandi` olayı yol taşımadığı için hangi yolla kapandığı ölçülemiyordu.

McD'de 78 kapanmış iş çalışma özetsizdir; 73'ü P-009 sonrası kapanmıştır. ADR-0179 ölçümünde kapı 1 sonucu ayrımsızdı (308/309 FAIL): kapsam içi (gap, kalite, sözleşme bayraklı) ve dışı işler aynı sayılıyordu.

**Karar:**

- `is_durum` "kapandi" için `yol` ∈ {cli, panel, bakim} ister; yoksa ya da geçersizse `ValueError` verir (`is_kaydi.py` `KAPANIS_YOLLARI`). Olay `{"olay": "durum:kapandi", "yol": …, "gerekce": …}` yazılır; `gerekce` yalnız verilmişse.
- `kapat_uygula` yolu taşır: CLI `cli`, panel `panel`, bakım `bakim`. Kapanış yalnız bu tek kapılı yoldan geçer.
- SessionStart hook'u (`_kapanis_notlari`) iş kapatmaz; "kapanabilir: orkestra is kapat <id>" notunu bildirir.
- `olc` (muhendislik_kontrol.py) işleri kapsam içi (gap+kalite+sözleşme bayraklı, `olusturma` >= `kapsam_baslangic`) ve dışı diye ayrı sayar; kapanmış işlerin yol dağılımını (`yol_dagilimi`, yolsuz eski olaylar "bilinmiyor") verir.
- Plan yazımında eksik T için gölge uyarısı üretilir.
- `00-Anlatim.md` onay bekleyen işte ilk bağlantıdır; kaynak (is.json, mevcut durum, plan, todo) anlatımdan yeniyse ya da dosya yoksa üretilir, değişmediyse dosyaya dokunulmaz; kapanışta zorunlu yeniden üretilir.

**Seçenekler:**

- Hook'tan `kapat_uygula` çağırmak: elendi. SessionStart'ta kapanış kapıları kullanıcıya soru üretir; sessiz kapanış yine olurdu.
- Kapıları `is_durum` içine taşımak: elendi. `is_kaydi` → `komutlar` döngüsel import oluşur ve kapanışın yan işleri atlanır.
- Yalnız hook satırını silmek: elendi. Düşük düzeyde koruma kalmaz; gelecekteki bir çağıran `is_durum` ile yine kapısız kapatır.

**Sonuçlar:**

- Kapısız kapanış `is_durum` düzeyinde imkânsızdır; yol her kapanış olayında kayıtlıdır ve ölçülebilir.
- Geçmişteki 78 özetsiz iş düzeltilmez; yol alanı yoksa "bilinmiyor" kalır.
- İlk gerçek ölçüm (12.11.2026 23:04, McD durum klasörü, `muhendislik_kontrol.py olc`): kapsam içi 18 iş (PASS 4, FAIL 14), kapsam dışı 305; kapanış yolu kayıtlı olmayan 283 kapanış "bilinmiyor".
- Kapıların ihlal moduna geçişi P-028 gereği ayrı karar ve ayrı ADR ister; bu ADR geçiş yapmaz.
- Hook artık yalnız bildirir; kapanış kararı kullanıcının `orkestra is kapat` çağrısındadır.

**İlgili:** ADR-0179, P-009, P-028, I-447

**İlgili iş:** I-461
