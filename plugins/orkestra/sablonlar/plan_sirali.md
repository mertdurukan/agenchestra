# {baslik}: plan

## Özet

<!-- doldur (ilk bakışta okunur, 3-4 kısa cümle; paragraf en çok 300 karakter (biçim kapısı daha uzununu reddeder), uzunsa ayrı paragraflara böl): hedef, seçilen yol, kaç madde, karar ya da onay gereken tek konu. Belgeyi bitirince yaz. -->

**Sıra:**

[mevcut_durum_{gun}.md](mevcut_durum_{gun}.md) → bu plan → `todo.md`. Plan yalnız mevcut durumdan çıkan sonuçlara dayanır. Her plan maddesi dayandığı mevcut durum bölümünü (MD §) gösterir.

**Önce oku:**

[mevcut_durum_{gun}.md](mevcut_durum_{gun}.md)

**ADR:** <ADR-nnnn | gerekmez — neden>

**LLM çıktısı:** <yok — neden | kullanıcıya gider — Doğrulama: kod veya test yolu[::test adı]>

<!-- doldur: iki satırda da açılı yer tutucuyu silip değeri yaz; doldurulmadan kapı reddeder. ADR (P-015): `ADR-nnnn` (adr/ klasöründe dosyası olur) ya da `gerekmez — <neden>`. LLM çıktısı (P-032): `yok — <en az 3 sözcük gerekçe>` ya da `kullanıcıya gider — Doğrulama: <yol>`. -->

**Hazırlanma saati:**

{tarih} {saat}

## 1. Hedef

<!-- doldur: iş hedefi ve ölçü -->

## 2. Mevcut durumdan çıkan sonuçlar

<!-- doldur: her sonuç ayrı satır: - **S1:** sonuç. Dayanak: MD §n -->

## 3. Kararlar

<!-- doldur: her karar ayrı satır: - **K1:** karar. Dayanak: MD §n -->

## 4. Plan maddeleri

<!-- doldur: her madde ayrı başlık ve zorunlu alanlar:
### P1 Başlık
**Ne:**
**Dayanak:** MD §n (mevcut durum bölümü)
**Dokunulan yer:** MD §3 etki haritasındaki yer
**Kabul:** ölçülebilir tek ölçüt (komut çıktısı, sayı, dosya:satır); "yapıldı" kabul değildir (kalite kapısında zorunlu)
**Geri alma:** değişikliği geri almanın yolu (kalite kapısında zorunlu)
**Önce:** bu maddeden önce bitmesi gereken P maddeleri (varsa)
**Gap:** G<n> (MD §6'daki hangi gap'i kapatır; gap'li işlerde zorunlu)
**Sözleşme:** S<n> (sözleşmeli işte zorunlu: bu madde sözleşmedeki hangi başarı kriterini sağlar; `sozlesme_<tarih>.md`)
**Mevcut varlık:** harita kayıt kimliği (virgülle; kimlikten sonra `(not)` ya da `; not` serbest) ya da `yok — <aranan>` (dokunduğun yerde zaten var olan mekanizma; `orkestra harita oku`; haritalı işlerde zorunlu)
**Alternatifler:** en az iki uygulanabilir yaklaşım, madde işaretli ayrı satırlarda: `- Seçilen: … Neden: …` ve `- Elenen: … Neden elendi: …` (P-030; `orkestra standart goster best_in_class`)
**Üretim noktası:** sorunun doğduğu yer ve orada önleme, üç türden biri: `Düzeltme: <kural|şablon|skill|betik|kart|istem|hook|ayar|standart ya da yol> — <orada önleme>` · `Kontrol: <yer> — <ne kontrol edilir>; Kaynakta çözülmedi çünkü: <neden>` · `Yeni yetenek — <düzeltilecek kusur olmadığının gerekçesi>` (K-006; `uretim: true` işlerde zorunlu, her maddenin metni kendine özgü olur; hata, ret, kusur, tekrar geçen maddede `Yeni yetenek` yazılmaz)
Mevcut durumda karşılığı olmayan madde yazılmaz; önce mevcut durum güncellenir. -->

## Gap kapsama

<!-- gap'li işlerde zorunlu (ikinci doğrulama): MD §6'daki her gap bir satır: - **G1** → P1, P2   ya da   - **G3** Kapsam dışı: <gerekçe> -->

## Best in class denetimi

Plan yazarından AYRI `orkestra:denetci` dört soruyu yanıtlar (`orkestra standart goster best_in_class`); sonucu ana ajan buraya yazar. Her satır `✔` ya da `✘` ile başlar.

- **Kök neden:** bekliyor
- **Alternatifler:** bekliyor
- **Kapsam özü:** bekliyor
- **Ölçüm:** bekliyor
- **Üretim noktası:** bekliyor

**Denetçi:** bekliyor (`orkestra:denetci <agent_id>`)

## 5. Riskler

## 6. Doğrulanmayanlar
