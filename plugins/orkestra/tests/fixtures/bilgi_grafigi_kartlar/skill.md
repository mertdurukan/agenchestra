# skill

## Amaç
- Orkestra eklentisinin skill'leri: SKILL.md dosyası, panelde aç/kapa ve konum seçimi.

## Eşanlamlılar
- skill, yetenek, eklenti komutu

## Yüzeyler
- skill tanımı (plugins/orkestra/skills/**/SKILL.md): her skill kendi klasöründe SKILL.md taşır
- panel aç/kapa listesi (plugins/orkestra/scripts/araclar_skill.py): skill listesini SKILL.md klasörlerinden tarar ve skillOverrides yazar
- panel uç noktası (plugins/orkestra/scripts/panel.py): POST /api/araclar-skill aç/kapa isteğini araclar_skill'e iletir

## Değişmezler
- Skill listesi skills/ altındaki SKILL.md klasörlerinden türer; yeni skill listeye elle eklenmez.
