# ADR-0183: Görev listesi açık adımla tur bitmez

**Durum:** Kabul edildi

**Tarih:** 2026-11-13

**Bağlam:**

Ajanın görev listesi (masaüstünde `mcp__ccd_turn__update_plan`, CLI'da `TodoWrite`) uygulamanın tuttuğu ayrı bir kayıttır. Hook bu listeyi değiştiremez; yalnız ajan değiştirebilir. Stop hook'u listeyi okumuyordu: `stop()` içinde `update_plan` ya da `TodoWrite` geçmiyordu.

13.11.2026'da bir oturumda iki tur, işler bitmiş olduğu halde listede açık adımla bitti. Kullanıcı açık adımları görüp işin bitip bitmediğini sormak zorunda kaldı. Talimat ve hafıza hatırlatması bu hatayı önlemedi.

**Karar:**

- `scripts/gorev_listesi.py` listenin son durumunu transcript'ten kuran tek ayrıştırıcıdır. close skill'inin `sohbet_cikar.Plan` sınıfı da bunu kullanır.
- `scripts/gorev_listesi_kapisi.py` Stop kapısıdır; `hook.py` `stop()` içinde kapanış kapısından önce çağrılır.
- Açık adım varsa tur bir kez durdurulur (`decision: block`). Ajan aynı turda listeyi kapatır ya da neyin kaldığını söyler.
- Muafiyetler:
  - `stop_hook_active` (döngü kesici)
  - arka plan görevi (`background_tasks`)
  - kullanıcıdan soru ya da onay bekleyen tur (`niyet.bekleme_nedeni`)
  - yalnız listenin son adımı `in_progress` ise; uygulama onu tur sonunda kendisi işaretler.
- Her tetik `gunluk.jsonl`'a yazılır: `tur: kapi_ihlal` (block) ya da `kapi_golge`, `kapi: gorev_listesi`.
- Ayar `ayarlar/gorev_listesi_kapisi.json`; proje durum dizinindeki aynı adlı dosya ezer. `ORKESTRA_GOREV_LISTESI_KAPISI=0` kapatır.

**P-028 istisnası:** Kapı gölgede değil, doğrudan `block` modunda açılır. Kullanıcı bu hatayı açıkça engellenmesi gereken hata olarak istedi; gölge mod önlemez. Yanlış pozitifin maliyeti tek kısa ek turdur.

**Ölçüm ve geri alma:** İlk 50 tetikte, block'tan sonra aynı turda `update_plan` ya da `TodoWrite` gelmeyen tetikler yanlış pozitif sayılır. Bu pay %20'yi aşarsa kapı `golge`'ye alınır ve muafiyetler gözden geçirilir.

**Seçenekler:**

- Seçilen: Stop'ta transcript'ten durumu kurup bir kez block; durum kurucu close skill'iyle ortak.
- Elenen: kapıya ayrı yeni ayrıştırıcı. Neden elendi: `sohbet_cikar.Plan` ile kopya olur, iki ayrıştırıcı ayrışır.
- Elenen: talimat ya da hafıza hatırlatması. Neden elendi: alışkanlığa bağlı; aynı oturumda iki kez kaçtı.
- Elenen: listeyi hook ile `todo.md`'den üretmek. Neden elendi: görev listesi uygulama aracıdır, hook çağıramaz.
- Elenen: ayrı Stop hook girdisi. Neden elendi: ikinci süreç, transcript iki kez okunur.

**Sonuçlar:**

- Açık adımla biten tur durur; ajan listeyi kapatmadan tur bitmez.
- `sohbet_cikar.Plan`'ın `advance` davranışı düzeldi: artık in_progress adımdan sonraki ilk pending adımı başlatır (önceden listedeki ilk pending adımı başlatıyordu). `TodoWrite` de okunur.
- Kapsam dışı: CLI'ın `TaskCreate`/`TaskUpdate` araçları. Bunlar kimlik bazlı ayrı bir model kullanır; ölçümde ihtiyaç görülürse ayrı iş açılır.

**İlgili:** P-028, P-030, `scripts/hook.py` `_gorev_listesi_yanit`, `tests/test_gorev_listesi_kapisi.py`
