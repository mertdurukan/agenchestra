# {baslik}: plan

<!-- Yazım kuralları (tüm belge):
1. Her ayrı ifade ayrı bir satırdır (madde işareti ya da numara ile); bir satırda en çok bir cümle, ~200 karakter.
2. Başlık hiyerarşisi: `##` ana başlık, `###` alt başlık (`### P1 Ad`); kalın etiket başlık yerine kullanılmaz, yalnız alan adı olarak kullanılır.
3. Kanıt (dosya:satır, komut, sayı) satırın sonunda parantez içindedir.
4. Belirsiz sahiplik ("bizim kod", "kendi sunucumuz") yazılmaz; somut ad yazılır (adres, sürüm, yol, tablo, müşteri). -->

**Sıra:**

- Akış: [mevcut_durum_{gun}.md](mevcut_durum_{gun}.md) → bu plan → `todo.md`.
- Plan yalnız mevcut durumdan çıkan sonuçlara dayanır.
- Her plan maddesi dayandığı mevcut durum bölümünü (MD §) gösterir.

**Önce oku:**

[mevcut_durum_{gun}.md](mevcut_durum_{gun}.md)

- **ADR:** <ADR-nnnn | gerekmez — neden>
- **LLM çıktısı:** <yok — neden | kullanıcıya gider — Doğrulama: kod veya test yolu[::test adı]>

<!-- doldur: iki satırda da açılı yer tutucuyu silip değeri yaz; doldurulmadan kapı reddeder. ADR (P-015): `ADR-nnnn` (adr/ klasöründe dosyası olur) ya da `gerekmez — <neden>`. LLM çıktısı (P-032): `yok — <en az 3 sözcük gerekçe>` ya da `kullanıcıya gider — Doğrulama: <yol>`. -->

**Hazırlanma saati:**

{tarih} {saat}

## 1. Hedef

<!-- doldur: iki satır.
- Hedef: iş bitince ne değişmiş olacak (tek cümle).
- Ölçü: bunu hangi sayı ya da komut gösterir (tek cümle). -->

## 2. Mevcut durumdan çıkan sonuçlar

<!-- doldur: her sonuç ayrı satır: - **S1:** sonuç. Dayanak: MD §n -->

## 3. Kararlar

<!-- doldur: her karar ayrı satır: - **K1:** karar. Dayanak: MD §n -->

## 4. Plan maddeleri

<!-- doldur: her madde ayrı başlık ve zorunlu alanlar:
```markdown
### P1 Başlık
**Ne:**
**Dayanak:** MD §n (mevcut durum bölümü)
**Dokunulan yer:** MD §3 etki haritasındaki yer
**Kabul:** ölçülebilir tek ölçüt (komut çıktısı, sayı, dosya:satır); "yapıldı" kabul değildir (kalite kapısında zorunlu)
**Geri alma:** değişikliği geri almanın yolu (kalite kapısında zorunlu)
**Önce:** zorunlu: `yok` ya da virgülle `P<n> — Çıktı: <o maddenin hangi çıktısını okuduğu>` / `P<n> — Çakışma: <hangi dosyada yazma alanı kesişir>`; yalnız gerçek bağımlılık yaz, "sıra düzgün olsun" gerekçe değildir
**Yazma alanı:** bu maddenin yazacağı dosyalar (virgülle; glob olabilir); aynı dalgadaki maddelerin alanları kesişmez
**Jira:** Jira'dan gelen görevde görev anahtarı (örn. `PE-770`); isteğe bağlı, yalnız Jira görevinde yaz. Öncülleri `jira_bagimlilik.json`dan okunur: açık öncül plan kümesinde olmalı ve `**Önce:**` içinde anılmalıdır (ADR-0086; `orkestra is dalga <iş> --jira` satırları üretir)
**Gap:** G<n> (MD gap bölümündeki hangi gap'i kapatır; gap'li işlerde zorunlu)
**Sözleşme:** S<n> (sözleşmeli işte zorunlu: bu madde sözleşmedeki hangi başarı kriterini sağlar; `sozlesme_<tarih>.md`)
**Mevcut varlık:** harita kayıt kimliği (virgülle; kimlikten sonra `(not)` ya da `; not` serbest) ya da `yok — <aranan>` (dokunduğun yerde zaten var olan mekanizma; `orkestra harita oku`; haritalı işlerde zorunlu)
**Etki:** bu maddenin dokunduğu etki kümesi yüzeyleri (virgülle; `## Etki kümesi` bölümündeki yüzey adı ya da yolu; `etki: true` işlerde her yüzey en az bir maddede anılır, ADR-0118)
**Alternatifler:** en az iki uygulanabilir yaklaşım, madde işaretli ayrı satırlarda: `- Seçilen: … Neden: …` ve `- Elenen: … Neden elendi: …` (P-030; `orkestra standart goster best_in_class`)
**Üretim noktası:** sorunun doğduğu yer ve orada önleme, üç türden biri, her tür ayrı satırda (tek satıra ' · ' ile sıkıştırma: biçim kapısı reddeder):
- `Düzeltme: <kural|şablon|skill|betik|kart|istem|hook|ayar|standart ya da yol> — <orada önleme>`
- `Kontrol: <yer> — <ne kontrol edilir>; Kaynakta çözülmedi çünkü: <neden>`
- `Yeni yetenek — <düzeltilecek kusur olmadığının gerekçesi>`
(K-006; `uretim: true` işlerde zorunlu, her maddenin metni kendine özgü olur; hata, ret, kusur, tekrar geçen maddede `Yeni yetenek` yazılmaz)
```
Mevcut durumda karşılığı olmayan madde yazılmaz; önce mevcut durum güncellenir. -->

## Dalgalar

<!-- orkestra is dalga <iş> üretir: dalga başına P listesi, kritik yol, genişlik. Tüm plan tek zincirse (≥3 madde, genişlik 1) şu satırı yaz: **Tam sıralı çünkü:** <her madde bir öncekinin çıktısını okur, ≥15 karakter gerekçe> -->

## Gap kapsama

<!-- gap'li işlerde zorunlu (ikinci doğrulama): MD gap bölümündeki her gap bir satır: - **G1** → P1, P2   ya da   - **G3** Kapsam dışı: <gerekçe> -->

## Best in class denetimi

Plan yazarından AYRI `orkestra:denetci` dört soruyu yanıtlar (`orkestra standart goster best_in_class`); sonucu ana ajan buraya yazar. Her satır `✔` ya da `✘` ile başlar.

- **Kök neden:** bekliyor
- **Alternatifler:** bekliyor
- **Kapsam özü:** bekliyor
- **Ölçüm:** bekliyor
- **Üretim noktası:** bekliyor

**Denetçi:** bekliyor (`orkestra:denetci <agent_id>`)

## 5. Riskler

<!-- doldur: her risk ayrı satır, tam bu biçimde: `- **R1:** risk → olasılık: düşük | orta | yüksek → önlem (P<n>)`. Risk yoksa tek satır: "Yok". -->

## 6. Doğrulanmayanlar

<!-- doldur: yalnız doğrulanması denenip DOĞRULANAMAYAN şeyler; yoksa tek satır: "Yok". Her madde üç satır: Konu (neyin doğrulanamadığı), Denenen (hangi yol denendi), Engel (neden doğrulanamadı, kim kapatabilir). -->
