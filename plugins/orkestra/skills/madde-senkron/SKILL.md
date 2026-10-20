---
name: madde-senkron
description: >-
  Aynı madde kimliğini (G/A/V/K/Y/E, C1–C20, ST-xxx) taşıyan kanonik belgeleri birlikte ve güvenli biçimde
  günceller: yedek alır, her değişikliği birebir eşleşmeyle yapar, eşleşme yoksa ya da birden fazlaysa hiçbir
  şey yazmadan durur. Kullanıcı "kimliği tüm belgelerde güncelle", "bu maddeyi senkronla", "A7'nin metni
  değişti, belgelere işle", "kimlik hangi belgelerde geçiyor" dediğinde kullan.
when_to_use: >-
  "A7 metni değişti, hepsine işle", "maddeyi tüm belgelerde güncelle", "kimlik hangi belgelerde geçiyor",
  "madde senkronu", "dış sürümle taslağı eşitle".
argument-hint: "tara <KIMLIK...> | uygula <plan.json> [--kuru] | dogrula <kayit.json> | geri-al <kayit.json>"
---
# madde-senkron: madde kimliği → tüm kanonik belgelerde birlikte, yedekli güncelleme

**Amaç:** Bir madde kimliğinin metni değişince aynı kimliği taşıyan bütün belgelerin tutarlı kalması (projede kimlikler sabit tutulur).

**Betik:** `${CLAUDE_SKILL_DIR}/scripts/madde_senkron.py`. Kimlik aileleri ve belge listeleri projenin `.claude/madde_senkron/belgeler.json` dosyasındadır (örnek biçim: `scripts/test_belgeler_ornek.json`; `--belgeler` ile değişir). Yedekler `.claude/madde_senkron/yedek/` altına yazılır (yollar proje köküne göre; `zorunlu`: kimlik geçiyorsa plan ya işlem koymalı ya da `atlanan`'da gerekçe vermeli; `izle`: yalnız uyarı).

## Alt komutlar
- `tara <KIMLIK...> [--aile AD]`: kimliğin geçtiği belge:satırları listeler. Her zaman önce bunu çalıştır.
- `uygula <plan.json> [--kuru]`: planı doğrular; `--kuru` yalnız farkı gösterir, değilse yedek alır, yazar ve kayıt üretir.
- `dogrula <kayit.json>`: denetçi içindir; yedeğe planı yeniden uygulayıp bugünkü dosyayla karşılaştırır.
- `geri-al <kayit.json>`: dosyalar kayıttaki "sonra" hâlindeyse yedekten geri yükler.

## plan.json
- Zorunlu alanlar: `aciklama` (tek satır), `aile`, `kimlikler`, `islemler`.
- İşlem türleri: `degistir` (`eski`, `yeni`, `adet`), `isaretci_once` (`isaretci`, `metin`), `bolum_sonuna` (`baslik`, `metin`).
- Değişmeyen zorunlu belge için `atlanan: {"yol": "neden"}`.

## Akış
- `tara` ile etkilenen belgeleri bul.
- `plan.json` yaz, `uygula --kuru` ile farkı kullanıcıya göster.
- Onaydan sonra `uygula`; ardından işi yapan ajandan farklı bir denetçiyle `dogrula`.

## Çıkış kodları
- 0: tamam.
- 1: doğrulama başarısız.
- 2: eşleşme, kapsam ya da sır kapısı durdurdu.
- 3: kullanım ya da yol hatası.
