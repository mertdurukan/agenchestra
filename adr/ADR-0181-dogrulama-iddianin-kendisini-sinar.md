# ADR-0181: Doğrulama iddianın kendisini sınar

**Durum:**

Kabul edildi (I-458).

**Tarih:**

12.11.2026

**Bağlam:**

- `plan dogrula` bir iddiayı, en az bir dosya, deneme ya da arama kanıtı geçince ✅ sayar (`plan_dogrulama.py` `iddia_degerlendir`).
- Dosya kanıtı yalnız alıntının satırın ±2 çevresinde bulunduğunu sınar. İddianın yorumunu sınamaz.
- Bu yüzden "8 iddianın 8'i kanıtlı" çıktısı, yorumların da doğrulandığı izlenimini verdi.
- "X yalnız Y'ye bakar" gibi bir kapsam iddiası, fonksiyonun tamamı okunmadan tek alıntıyla ✅ oldu.
- Plan özeti yalnız plan metninden hesaplanır. Kanıt gösterilen kod değişince plan güncel kalır, revize edilmez.
- Sohbet kanıt kapısı turda herhangi bir okuma aracı çağrıldıysa susar. Kısmi okumadan (offset/limit) çıkan "yalnız/hiç/tümü" iddiasını ayırmaz.

**Karar:**

- **Kanıt derinliği:** geçen her kanıt bir derinlik taşır.
  - `yuklem`: tam `=> N` sayılı `ara`/`say` ya da `komut`.
  - `varlik`: `dosya`, `deneme` ya da `>=N`.
- **Çıktı:** CLI ve karar bloğu ✅ sayısını iki parçaya ayırır: "yüklemle a, yalnız alıntı/varlık b". Yalnız alıntılı iddialar adıyla ve "yorum sınanmadı" notuyla listelenir.
- **Kapsam iddiası:** kapsam sözcüğü taşıyan iddia yalnız yüklem kanıtıyla ✅ olur, yoksa ❌.
  - Kalıplar `ayarlar/plan_dogrulama.json` `kapsam_kaliplari` anahtarında durur (P-022).
- **Tanım kapsamlı arama:** `ara "<re>" yol.py::Sinif.ad => N` aramayı tanımın AST satır aralığında (dekoratörler dahil) yapar.
  - Tanım bulunamazsa ya da dosya .py değilse sonuç ❌.
- **Kanıt izi:** `--yaz`, iddia başına okunan içeriğin 8 haneli sha256 özetini `**Kanıt izi:**` satırına yazar.
  - Okunan içerik kanıt türüne göre: dosya penceresi, kapsamlı arama metni, sayılan dosya listesi ya da deneme dosyası.
  - `blok_oku` izi yeniden hesaplar. Todo kapısı "kanıt değişti (C<n>)" der ve planın revize edilmesini ister.
  - `komut` kanıtı izde yoktur: todo kapısı komut koşmaz, `plan dogrula` her koşuda komutu yeniden çalıştırır.
  - İz satırı olmayan eski bloklar eskisi gibi sınanır.
- **Okuma anında not:** PreToolUse'ta kısmi Read oturum ve dosya başına bir kez kısa not ekler. Not okunan aralığı söyler ve aralık dışı için kapsam iddiası yazılmamasını hatırlatır.
- **Gölge ölçüm:** Stop'ta şu üç koşul birlikte tutarsa günlüğe `kural_ihlal / kapsam_iddia` (mod golge) yazılır:
  - aynı cümlede kapsam sözcüğü ve backtick kod adı var;
  - turdaki her Read kısmi;
  - turda arama aracı yok.

  İhlal moduna geçiş ayrı ADR ile yapılır ve kesinlik en az %75 olmalıdır (P-028).

**Seçenekler:**

- **Her yorumu model denetçisine sınatmak:** elendi. Karar yeniden hesaplanamaz ve her koşu model çağırır. Denetçi ek katman olarak kalır.
- **Yalnız sayımı yeniden adlandırmak:** elendi. Kapsam iddiası yine tek alıntıyla geçer.
- **Satır aralıklı arama (`yol:10-40`):** elendi. Kod kayınca aralık sessizce yanlış olur.
- **Dosyanın tamamının özeti, mtime ya da git karşılaştırması:** elendi.
  - İlgisiz değişiklik ve checkout boşuna bayatlatır.
  - Kanıt dosyası git dışında olabilir.
- **PostToolUse Read notu:** elendi. Matcher Read'i içermez ve her Read'e yeni süreç ekler.
- **`kanit_olcum.kanitli_mi` değişikliği:** elendi. O ölçü "kanıt aracı çağrıldı mı" sorusudur; değiştirmek geçmiş ölçümleri bozar.

**Sonuçlar:**

- ✅ sınanan şeyi adıyla söyler. Yalnız alıntılı iddia görünür kalır.
- Kapsam iddiası yüklemsiz geçmez. Bu, yürüyen planlarda yeni ❌ üretebilir; etkisi gerçek planlarda ölçüldü.
- Ölçüm (12.11.2026, McD'nin 263 planı, 1324 iddia): bugün ✅ olan 251 iddianın 69'u yüklemle, 182'si yalnız alıntıyla sınanıyordu. Kapsam kuralı 32 iddiayı ✅→❌ çevirir. İlk 20 örnekte 2 yanlış pozitif var (%10, eşik ≤%20).
- Sohbet ölçümü (12.11.2026, son 200 döküm): 2024 tur, 294 kısmi okumalı tur, 5 isabet; 2'si doğru bulgu, kesinlik %40. Eşik %75 olduğu için kapı gölgede kalır. Kabuk çağrısını tümüyle kanıt saymak kesinliği %33'e düşürdüğü için geri alındı; yalnız arama komutları sayılır.
- Kaynak değişince todo kapısı değişen iddiayı adıyla verir.
- `kanit_dogrula`, `iddialari_ayristir`, `todo_onkosulu` imzaları değişmez. perspektif.py, plan_alan.py, muhendislik_kontrol.py ve is_kaydi.py bu imzalardan etkilenmez. hook.py yalnız kısmi okuma notu (PreToolUse) ve gölge kayıt (Stop) için değişir.

**İlgili:**

- P-016, P-022, P-028, P-045
- ADR-0069, ADR-0178
- I-458
