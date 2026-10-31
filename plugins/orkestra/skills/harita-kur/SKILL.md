---
name: harita-kur
description: >-
  Bir projenin bilgi grafiğini ilk kez kurar ya da yeniler: koddan statik kenarları çıkarır, konu kartlarını (md)
  yazar, kenar listesini (JSONL) ve INDEX'i üretir. Sonra yeni istekler bu grafikle eşlenir ve etki kümesi plana girer.
  Kullanıcı "projeyi haritala", "bilgi grafiğini kur", "bu proje neyle neye bağlı", "konu kartlarını üret",
  "harita eski, yenile" dediğinde ya da projeye ilk kez dahil olunduğunda kullan.
when_to_use: >-
  "projeyi haritala", "bilgi grafiği kur", "konu kartı yaz", "bağlantıları çıkar", "yeni projeye başlıyoruz",
  "harita kenarları eskimiş".
argument-hint: "[proje-kökü]"
---
# harita-kur: kod yapısı + anlam → konu kartları + tipli kenar listesi

**Amaç:** Yeni bir istek geldiğinde "bu neyle ilgili, nerelere dokunur" sorusu haritadan yanıtlansın (ADR-0112).
Harita bir kez kurulur; kenarlar kaynak dosya özetiyle eskime takibine girer (`orkestra harita yenile`).

**Dizin:** `<durum>/sistem_haritasi/bilgi_grafigi/` altında `kartlar/*.md` ve `kenarlar.jsonl`. Projeye özgü ad bu skill'de yoktur; her şey projenin dosyalarından türer.

## Adımlar

1. **Statik kenarlar (model çağırmaz):**
   `python ${CLAUDE_PLUGIN_ROOT}/scripts/harita_kenar.py <proje-kökü> --cikti <graf>/kenarlar.jsonl`
   Import, yol ve ad atıfları ile birlikte-değişim (git geçmişi) kenarlarını `koken: statik|gecmis` olarak yazar; şemaya uymayan kenar atılır.
2. **Konu adaylarını bul:** kenar yoğunluğu yüksek dosya kümelerini ve belge başlıklarını oku (README, docs, SKILL.md, arayüz listeleri). Her konu için en az bir dosya kümesi çıkar.
3. **Kart yaz** (her konu için bir md, `kartlar/<konu>.md`). Zorunlu bölümler, boş bırakılmaz:
   - `## Amaç`: konunun işi, tek cümle.
   - `## Eşanlamlılar`: kullanıcının isteğinde geçebilecek sözcükler (TR ve EN, çoğul/fiil kökleri).
   - `## Yüzeyler`: konu değişince birlikte bakılması gereken dosya ya da desenler (örn. `**/SKILL.md`), madde başına bir satır ve nedeni.
   - `## Değişmezler`: konu için her zaman doğru kalması gereken kural ya da eşleşme.
4. **LLM kenarı ekle (yalnız statik kenarın kaçırdığı anlam bağı):** `koken: llm`. Her kenar `kanit: dosya:satır` taşır; kanıt satırı yoksa `guven: dusuk` yazılır (K2). Statik kanıtla desteklenmeyen kenar `orta`/`yuksek` olamaz.
5. **Doğrula:** `orkestra harita denetle` eskimiş katmanı gösterir; kenar dosyasını `harita_kenar.yaz` şemaya uymayanı zaten atar, atılan kenarı düzeltip yeniden ekle.
6. **Dağılımı raporla:** kenar sayısı köken ve güven bazında (statik/gecmis/llm × yuksek/orta/dusuk). `dusuk` oranı yüksekse kullanıcıya tek cümleyle söyle.

## Sınırlar
- Sır değeri karta ya da kenara yazılmaz; yalnız yeri anılır.
- Kanıtsız kenar güvenilir sayılmaz; kart içeriği kaynak dosyadan doğrulanamıyorsa yazılmaz.
- Plan ve kapanış kapıları gölge moddadır (`ayarlar/harita_etki.json`); modu geçirmek ölçüme bağlı ayrı karardır.
- Sorgu: `orkestra harita istek "<kullanıcı isteği>"` eşleşen kartları, yüzeyleri ve bir adımlık komşuları verir.
