# PR-6 model listesi (karar 3)

**Karar:** Aşağıdaki Cursor slug eşlemesi sonraki model_politikasi.cursor.json tabanıdır (10.11.2026).

**İlkeler:** Denetçi işçiden düşük olmaz. Claude haiku, sonnet ve opus ailesi korunur. Ölçülen slug: claude-sonnet-5-5-high (ide_olcum.md:28). Bu oturumda görülen adaylar: claude-haiku-5-5-thinking-high, claude-sonnet-5-5-high, claude-opus-5-5-medium, grok-4.7-high-fast.

## Eşleme

- ana_ajan: claude-sonnet-5-5-high
- T1: claude-haiku-5-5-thinking-high
- T2: claude-sonnet-5-5-high
- T3: claude-opus-5-5-medium
- T4: claude-opus-5-5-medium (ayrı yüksek-effort slug yok; aynı model)
- denetci: işçinin modeli (taban). T1 haiku, T2 sonnet, T3 ve T4 opus. Azami claude-opus-5-5-medium.
- yasak: grok-4.7-high-fast (Claude birebir dışı)

## Maliyet (G4)

- token, usage ve cost alanı yok (ide_olcum.md bölüm 2, madde 4, doğrulandı).
- Kayıt host=cursor ve etiket=tahmini taşır. Kesin sayaç vaat edilmez.

## Alternatifler

- Seçilen: tam Cursor slug ve denetçi tabanı işçiden düşük değil. Neden: hook model alanı tam slug; karar 3.
- Elenen: haiku, sonnet, opus kısa adları. Neden elendi: Cursor slug ile eşleşmez.
- Elenen: sahip listesi gelene dek beklemek. Neden elendi: kalan kararlar ajana bırakıldı.

## JSON iskeleti (sonraki PR-6 uygular)

- surum: 1
- ana_ajan.varsayilan: claude-sonnet-5-5-high
- basamak: T1, T2, T3, T4 yukarıdaki sluglar
- denetci.azami_model: claude-opus-5-5-medium
- denetci.floor_isci: true
