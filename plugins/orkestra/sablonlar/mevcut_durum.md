# {baslik}: mevcut durum

<!-- okunabilirlik kuralları (tüm bölümler): bölüm başına en çok 7 madde; madde en çok ~200 karakter ve tek fikir; her bölüm önce `**Sonuç:**` tek cümleyle açılır, kanıt maddeleri altında durur; kanıt (dosya:satır, komut, sayı) maddenin sonunda parantezde; belirsiz sahiplik yerine somut ad (adres, sürüm, yol, tablo, müşteri); tablo ve kod bloğu yok (kapı madde arar). -->

## Özet

<!-- doldur (ilk bakışta okunur; her paragraf en çok 300 karakter, biçim kapısı daha uzununu reddeder). Üç kısa paragraf, düz metin (kalın etiket koyma: kapı etikette Özet'i kapatır):
1. Bu belge neyi gösteriyor ve bugün durum ne (ana sonuç, tek sayıyla).
2. Değişikliğin en riskli dokunuşu ne.
3. Karar ya da onay gereken tek konu; yoksa "Karar bekleyen konu yok."
Belgeyi bitirince yaz. -->

**Amaç:**

<!-- doldur: tek cümle; hangi değişikliğin dokunacağı mevcut durumu gösterir. Bu dosya işin ilk dosyasıdır; plan.md ve todo.md buna dayanır. -->

**Ölçüm saati:**

<!-- doldur: GG.AA.YYYY SS:DD (yerel); ölçülen kod/veri sürümü (depo, dal, commit). -->

**Harita:**

<!-- doldur: `orkestra harita oku` çıktısından bu işe dokunan kayıt kimlikleri (sır yeri, süreç, altyapı, modül); haritada yoksa taranan yer. -->

**Yöntem:**

<!-- doldur: ne okundu/koşuldu (dosya okuma, komut, sorgu), satır başına bir yöntem. "Teyit gerekir" bakılmadı demektir. -->

- 

**Sınır:**

<!-- doldur: bakılmayan ve erişilemeyen yerler, satır başına bir sınır ve nedeni; yoksa "Yok". -->

- 

## 1. İstek ya da veri hangi yoldan geçiyor

<!-- doldur: `**Sonuç:**` tek cümle (yol kaç adım, hangi adımda risk var). Altına ilk adımdan son adıma sıralı numaralı liste: `1. adım (dosya:satır)`. Dallanma varsa (örn. V1/V2) her dal için ayrı kalın başlık ve ayrı liste. -->

## 2. Bugünkü davranış ve çalışan korumalar

<!-- doldur: `**Sonuç:**` tek cümle (koruma yeterli mi). Altına iki liste: `**Çalışıyor:**` ve `**Çalışmıyor ya da yok:**`. Her madde: `- **koruma** → ne yapıyor (kanıt)`. Her iddia dosya:satır, komut çıktısı ya da ölçüm saatiyle. -->

## 3. Etki haritası

<!-- doldur: `**Sonuç:**` tek cümle (kaç yere dokunulacak, en riskli hangisi). Her madde ayrı satır, bu biçimde: `- **yer** → bugünkü davranış → dokunmanın riski (düşük | orta | yüksek)`. Risk sözcüğü satırın sonunda durur. -->

## 4. Git durumu

<!-- doldur: `**Sonuç:**` tek cümle (dal temiz mi, işin dalında ne var). Altına: dal, son commit, çalışma ağacı, işin dalında zaten yapılmış olanlar; her biri ayrı madde. -->

## 5. Bilinmeyenler

<!-- doldur: `**Sonuç:**` tek cümle (kaç bilinmeyen, kaçı plan öncesi kapanmalı). İki liste: `**Teyit gerekir:**` (bakılabilir, bakılmadı) ve `**Karar gerekir:**` (kullanıcıdan ya da ekipten). Eksik bilgi bu dosyaya eklenir, plan ya da todo'da yamanmaz. -->

## 6. Gap analizi

<!-- doldur (gap'li işlerde zorunlu; plan bu bölümden beslenir):
önce "**Hedef durum:**" etiketli tek cümle;
sonra her gap ayrı satır, şu biçimde:
- **G1:** hedef → mevcut (MD §n) → fark
Her satır tek fikir; hedef, mevcut ve fark kısa tutulur. Gap yoksa bile en az bir satır yaz; "fark yok" gerekçesiyle belirt. -->
