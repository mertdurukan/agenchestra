---
name: arsivle
description: >-
  Scratchpad ya da başka bir çalışma klasörünü proje arşivine taşır: önce kaynakta sır taraması (sır
  bulunursa hiçbir şey kopyalanmaz), kimlik/bağlantı dosyalarını (db.py, .env, *.pem, *.key) atlar,
  e-posta ve IP maskeler, ad eşlemesini uygular, kopyalar, hedefte son tarama yapar, taşıma kaydına satır
  ve klasör README iskeleti ekler. Kullanıcı "arşivle", "çalışma klasörünü arşive taşı", "ham çıktıları
  arşive al", "scratchpad'i kalıcı yap" dediğinde kullan.
when_to_use: >-
  "arşivle", "arşive taşı", "ham çıktıları arşive al", "scratchpad kalıcı olsun", "98_calisma'yı temizle",
  "sır taraması yap" (yalnız tarama için --yalniz-tara).
argument-hint: "<kaynak> <hedef_kok> <konu> [--kuru]"
---
# arsivle: çalışma klasörü → sır taraması → maskeleme → arşiv

**Amaç:** Oturum kapanınca kaybolacak ya da dağınık kalan çalışma çıktılarını (betik, ham çıktı, ara CSV) tek komutla, sır sızdırmadan proje arşivine taşımak.

**Betik:** `${CLAUDE_SKILL_DIR}/scripts/arsivle.py` (testi: `test_arsivle.py`). Proje kökü `CLAUDE_PROJECT_DIR` ya da çalışma dizinidir (`--proje` ile değişir). Arşiv kuralı (P-013): tek arşiv `_arsiv\<proje>\`; veri çıkarma, izleme ve orkestra dosyaları arşive gitmez.

## Kullanım
- Önce kuru koşu: `python -X utf8 "${CLAUDE_SKILL_DIR}/scripts/arsivle.py" <kaynak> <hedef_kok> <konu> --kuru`. Çıktıyı kontrol et, sonra `--kuru` olmadan çalıştır.
- Yalnız tarama (kopyalamaz): `python -X utf8 "${CLAUDE_SKILL_DIR}/scripts/arsivle.py" --yalniz-tara <yol>`.
- Seçenekler: `--ekle`, `--tarih YYYYMMDD`, `--ad-esleme DOSYA`, `--kayit CSV`, `--readme-aciklama METIN --readme-baslangic METIN`, `--maskeleme-yok`, `--proje KOK`.

## Akış (sıra önemli; betik zorlar)
- Yol kapıları: hedef proje içinde olmalı, kaynak hedefin içinde olmamalı.
- Envanter: kimlik/bağlantı dosyaları ve artıklar atlanır.
- Sır taraması kopyalamadan önce yapılır; DURDUR sınıfı eşleşmede hiçbir dosya kopyalanmaz (çıkış kodu 2). Sır değeri ekrana yazılmaz, yalnız kalıp, dosya, satır ve uzunluk gösterilir.
- Maskeleme: e-posta → `<e-posta>`, IPv4 → `<ip>`, ad eşlemesi (ad → kod). Eşleme dosyası hedefin içinde olamaz.
- Kopyalama sonrası hedefte son tarama (DURDUR eşleşmesinde çıkış kodu 4).
- Taşıma kaydına satır, klasör README iskeleti, istenirse arşiv README tablosuna satır.

## Çıkış kodları
- 0: tamam.
- 2: sır bulundu, kopyalanmadı.
- 3: kullanım ya da yol hatası.
- 4: son tarama başarısız.

## Sınırlar
- Çalışan adları ad eşlemesiyle koda çevrilir; müşteri adları açık kalabilir.
- Sır bulunursa kullanıcıya yalnız yeri bildirilir (dosya:satır); değeri sohbete ya da belgeye yazma.
