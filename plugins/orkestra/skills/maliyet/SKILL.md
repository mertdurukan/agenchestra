---
name: maliyet
description: Orkestra token ve maliyet raporu — her ajanın her süreç (triyaj, iş, denetim, düzeltme, sentez, rüya…) için harcadığı giriş/çıkış/önbellek tokenı ve tahmini maliyet; görev × süreç, ajan × model, süreç ve gün kırılımları.
argument-hint: "[gün sayısı, ör. 7]"
disable-model-invocation: true
---
# /orkestra:maliyet

1. Gün sayısı: `$ARGUMENTS` boşsa 7.
2. `orkestra maliyet rapor --gun <gün> --cikti .claude/orkestra/raporlar/maliyet_<YYYYMMDD>.md` çalıştır, sonra dosyayı oku.
3. Kullanıcıya kısa özet ver:
   - toplam;
   - en pahalı 3 görev;
   - süreç payları (denetimin toplamdaki payı %15-30 aralığında mı);
   - basamak dağılımı (Haiku ve Sonnet'in payı);
   - dikkat çeken bir şey varsa tek cümle öneri.
4. Rapor dosyasının yolunu ver. Tutarların API liste fiyatıyla tahmin olduğunu belirt; abonelikte gerçek fatura değildir, kota karşılığıdır.
