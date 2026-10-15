---
name: ruya
description: ESKİ AD (takma ad) — "rüya" artık Perspektif'tir. /orkestra:perspektif ile aynı işi yapar: perspektif raporunu gösterir, onaylanan önerileri uygular, istenirse perspektifi şimdi başlatır.
argument-hint: "[şimdi]"
disable-model-invocation: true
---

# /orkestra:ruya (eski ad → /orkestra:perspektif)

Bu skill yalnız geriye uyum için durur. Kullanıcıya tek satırla "Bu komutun yeni adı `/orkestra:perspektif`" de, sonra **`/orkestra:perspektif` skill'indeki adımları aynen uygula** (`$ARGUMENTS` aynı şekilde geçer).

Kısaca:
1. `orkestra perspektif durum` çalıştır (eski `orkestra ruya …` komutu da takma ad olarak çalışır; eski `ruya/` durum klasörü ve `ruya_*.md` raporları otomatik göç eder, okunur).
2. `$ARGUMENTS` "şimdi" içeriyorsa ya da hiç rapor yoksa `orkestra:perspektif-ajani` ajanını `run_in_background: true` ile başlat (eski `orkestra:ruya-ajani` adı artık yoktur).
3. Rapor varsa özetle; panel kararlarını `orkestra onay liste --tur perspektif` ile al, onaylananları `/orkestra:onay` akışıyla uygula, tüm perspektif kayıtları kapanınca `orkestra perspektif bitti` çalıştır.
