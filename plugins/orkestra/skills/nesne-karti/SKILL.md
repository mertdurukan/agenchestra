---
name: nesne-karti
description: "Bir tablo, kolon ya da prosedürü anlatırken her iddiaya derece (KESİN/GÜÇLÜ/DOĞRULANMADI) ve yeniden çalıştırılabilir kaynakça yazdırır; kartı ayrı denetçiye eşletir ve `orkestra nesne-karti dogrula` ile denetler. Tek tek iddia listesi için iddia-dogrula."
when_to_use: >-
  "bu tablo ne işe yarar", "bu kolon nedir", "bu prosedür ne yapıyor", "hangisi nedir", "kesin bilgi ver",
  "kaynakça göster", "emin olmadıklarını işaretle", "nesne kartı çıkar".
argument-hint: "<nesne: şema.tablo, şema.tablo.kolon ya da prosedür adı>"
---
# nesne-karti: tek nesne → derece + kaynakça → ayrı denetçi → doğrulayıcı

**Amaç:** Bir nesneyi anlatan her iddia kaynağıyla ve kesinlik derecesiyle yazılır; kesin olmayan gösterilir.

## 1. Kartı üret

1. Konuyu tek bir nesneye indir (tablo, kolon ya da prosedür).
2. Kaynakları şu sırayla oku, hepsini bu turda çek: canlı veritabanı kataloğu ve prosedür gövdesi, sonra depo kodu, sonra belge ve hafıza.
3. Her iddiayı `- [DERECE] metin (K1, K2)` satırına yaz. Dereceler:
   - **KESİN:** yalnız birincil kaynağa dayanır (Veritabanı kataloğu, Prosedür gövdesi, Kod, Ölçüm çıktısı).
   - **GÜÇLÜ:** ikincil kaynak ya da dolaylı çıkarım.
   - **DOĞRULANMADI:** altına `- Neden:` ve `- Kapatma:` satırları ekle (girintili).
4. Kaynakçayı `- K1: tür=…; komut=… | yol=…; ortam=…; saat=…` biçiminde yaz. Komut ya da yol yeniden çalıştırılabilir olmalı. Sır değeri yazılmaz.
5. Ham sorgu çıktısını döküm dosyasına kaydet (`dokum_<nesne>.txt`).

## 2. Ayrı denetçiye eşleştir

1. `orkestra:denetci` çağır; kartı yazan ajan olmasın.
2. Denetçi her iddiayı kaynağıyla tek tek eşler: kaynak iddiayı söylüyor mu, derece uygun mu?
3. ✘ çıkan iddia düzeltilir ya da DOĞRULANMADI'ya indirilir; denetçiyi yeniden çağır.

## 3. Doğrulayıcıyı çalıştır

```
orkestra nesne-karti dogrula <kart.md> --dokum <dokum_nesne.txt>
```

Çıkış 0 ise kart biçimce temizdir. Çıkış 1 ise bulgular satır satır düzeltilir. Doğrulayıcı biçimi ve kaynak hiyerarşisini denetler; iddianın doğruluğunu 2. adımdaki denetçi yargılar.
