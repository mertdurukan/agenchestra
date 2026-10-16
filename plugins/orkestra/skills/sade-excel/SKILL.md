---
name: sade-excel
description: >-
  CSV ya da JSON tabloyu ev stilinde sade bir Excel teslimatına çevirir: Özet sayfası + en çok 2 veri
  sayfası, koyu lacivert başlık, donmuş başlık satırı, filtre, otomatik sütun genişliği; isteğe bağlı
  masaüstüne kopya. Kullanıcı "Excel'e dök", "sade excel", "minimum, en anlamlı", "xlsx olarak ver",
  "excel çok karışık, sadeleştir", "masaüstüne de koy" dediğinde kullan. Çağırırken girdi dosya
  yollarını, başlığı ve (biliniyorsa) sütun seçimini argümana yaz; çatallı bağlamda sohbeti görmez.
when_to_use: >-
  "Excel'e dök", "xlsx yap", "sade excel", "minimum en anlamlı", "excel karışık olmuş", "tek sayfa
  özet + liste", "masaüstüne kopyala". Bir betiğin ürettiği CSV/JSON'un teslim edilecek son hali.
argument-hint: "<girdi.csv|json> [ikinci.csv] --baslik \"...\" [--sutunlar \"a,b=Yeni ad\"] [--cikti ad] [--masaustu]"
context: fork
agent: orkestra:isci-t1
allowed-tools: Bash(python *), Read, Glob
---
# sade-excel: CSV/JSON → ev stili sade xlsx (T0 betik, T1 işçi)

İstek: $ARGUMENTS

**Amaç:** Kullanıcının istediği "sade, minimum, en anlamlı" Excel'i her seferinde aynı biçimde, elle
biçimleme yapmadan üretmek. Biçim tek betikte sabit: `${CLAUDE_SKILL_DIR}/scripts/sade_excel.py`.
Ev stili: Özet sayfası + en çok 2 veri sayfası, koyu lacivert başlık, donmuş başlık satırı, filtre, otomatik sütun genişliği.

Gereksinim: Python `openpyxl` paketi.

Bu skill çatallı bağlamda `orkestra:isci-t1` (Haiku) ile çalışır. Sohbeti göremezsin; her şey argümanda
olmalı. Eksikse (girdi yolu yok, dosya yok, başlık yok) **hiçbir şey üretme**, eksiği tek cümleyle bildir.

## Basamaklar
| Adım | Basamak | Kim |
|---|---|---|
| Hangi veri, hangi sütunlar, hangi ad | T3 | Ana ajan / kullanıcı (argümanda verir) |
| xlsx üretimi, geri okuma denetimi, masaüstü kopyası | T0 | `sade_excel.py` (sen yalnız çalıştırırsın) |
| Sütun seçimi verilmemişse kural ile seçim | T1 | Sen (aşağıdaki kural) |

## Yöntem
1. **Girdiyi doğrula.** Argümandaki her yolu `Glob`/`Read` ile aç; yalnız ilk 5 satırı oku (başlık ve örnek).
   Veri sayfası en çok 2'dir; 3. tablo istenirse birleştirmeyi ya da ayrı dosyayı öner, kendin birleştirme.
2. **Sütun seçimi.** Argümanda `--sutunlar` varsa aynen kullan. Yoksa en çok 8 sütun seç:
   kimlik sütunu (ID/No/Kimlik) → ad/başlık → kararı veren sütunlar (durum, öncelik, karşılama, etiket, sayı)
   → tek açıklama sütunu. URL, ham JSON, iç kod, tekrar eden ve tamamen boş sütunları alma.
   Seçtiğin sütunları ve dışarıda bıraktıklarını son mesajda yaz. Başlıkları `kaynak=Türkçe Ad` ile düzelt.
3. **Özet metni (isteğe bağlı).** Argümanda bulgu maddeleri varsa `<ara klasör>\ozet.md` yaz:
   `## ANA BULGULAR` altında en çok 5 madde, `## NASIL OKUNUR` altında sütun anlamları. Bulgu uydurma;
   argümanda yoksa `--ozet` verme (betik yine SAYFALAR ve ÜRETİM bölümlerini kendisi yazar).
4. **Çıktı adı.** Teslimat, projenin kuralının gösterdiği teslim klasörüne (kural yoksa işin klasörüne, o da yoksa `.claude/orkestra/`) `<konu>_<YYYYMMDD>.xlsx` adıyla yazılır. Aynı ad varsa üzerine yazma;
   `_v2` ekle. Ara/deneme dosyaları aynı yerde `<konu>_<YYYYMMDD>\` alt klasörüne.
5. **Çalıştır (T0):**
   ```
   python -X utf8 -I "${CLAUDE_SKILL_DIR}/scripts/sade_excel.py" --cikti <xlsx> --baslik "<başlık>" \
     --alt-baslik "<GG.AA.YYYY · kaynak · kapsam>" --veri <a.csv> --sayfa <Ad> --sutunlar "<...>" \
     [--aciklama "<sayfa ne gösterir>"] [--veri <b.csv> --sayfa <Ad2> ...] [--ozet ozet.md] \
     [--dondur-sutun 1] [--masaustu]
   ```
   `--sayfa/--sutunlar/--aciklama` sırayla `--veri`'lere eşlenir. Kimlik sütunu varsa `--dondur-sutun 1`.
   `--masaustu` yalnız kullanıcı istediğinde ya da "final" teslimatta verilir.
6. **Sonucu oku.** Betik `TUTARLI -> <yol>` ve sayfa başına satır/sütun sayısı basar.
   - Çıkış 1: argüman/girdi hatası (dosya yok, sütun yok, 2'den fazla veri); mesajı aynen raporla.
   - Çıkış 2 (TUTARSIZ): geri okunan sayılar girdiyle tutmuyor; dosyayı teslim etme, çıktıyı aynen raporla.
   - Çıkış 3: sır kalıbı bulundu, dosya yazılmadı; hücre adreslerini raporla, değeri yazma.
   - `UYARI: uzun anahtar benzeri dizi`: dosya yazıldı ama o hücreler elle kontrol edilmeli; raporla.

## Ev stili (betikte sabit, elle değiştirme)
- Sayfa 1 `Ozet`: A sütunu 150 genişlik; başlık kalın 16 punto lacivert (1F3864); alt başlık italik gri;
  bölüm başlıkları beyaz yazı + lacivert dolgu, BÜYÜK HARF; sonda SAYFALAR ve ÜRETİM.
- Veri sayfaları: başlık kalın beyaz, lacivert dolgu, ortalı, kaydırmalı; ince gri kenarlık; hücreler üstten
  hizalı, kaydırmalı; sütun genişliği içerikten (8–60); donmuş başlık; tüm aralıkta filtre.
- Sayılar sayı olarak yazılır, baştaki sıfırlı kodlar ("007") metin kalır; `=` ile başlayan metin formül olmaz.

## Çıktı (son mesajın)
Dosya yolu (ve masaüstü kopyası), sayfa başına satır × sütun, seçilen ve dışarıda bırakılan sütunlar,
betik çıktısının son satırı. 5–8 satır; yorum ekleme.

## Kabul kriterleri
- Betik çıkış kodu 0 ve `TUTARLI` satırı var; veri sayfası sayısı ≤ 2; ilk sayfa `Ozet`.
- Her veri sayfasında satır sayısı girdi satır sayısına eşit (betik geri okuyarak denetler).
- Başlık satırı donmuş, filtre açık; seçilen sütun sayısı ≤ 8 (kullanıcı açıkça daha fazlasını istemediyse).
- Masaüstü kopyası yalnız istendiyse var.

## Yasaklar
- Betiği atlayıp openpyxl ile elle biçimleme yapma; stil değişikliği gerekiyorsa betiğe dokunma, son mesajda öner.
- Sır değeri, şifre, bağlantı dizesi ve çalışan adı hiçbir hücreye girmez (müşteri adları kalabilir).
- 3+ veri sayfası, renkli kategori boyaması, birleştirilmiş hücre, grafik ekleme: "sade" kuralına aykırı.
- Masaüstü kopyası betiğin bulduğu gerçek masaüstüdür (OneDrive yönlendirmeli olsa bile).
- Kaynak CSV'yi değiştirme ya da silme.
