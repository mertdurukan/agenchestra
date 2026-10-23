# {baslik}: plan

## Özet

<!-- doldur (ilk bakışta okunur, 3-4 cümle): hedef, seçilen yol, kaç madde, karar ya da onay gereken tek konu. Belgeyi bitirince yaz. -->

**Kök:** <!-- doldur: kanıt yollarının göreli olduğu kök dizin, projeye göre; örn. Claude_Orkestrasyon/plugin_yayin/plugins/orkestra -->

**Sıra:**

[mevcut_durum_{gun}.md](mevcut_durum_{gun}.md) → bu plan → `todo.md`. Plan yalnız mevcut durumdan çıkan sonuçlara dayanır. Her plan maddesi dayandığı mevcut durum bölümünü (MD §) gösterir.

**Önce oku:**

[mevcut_durum_{gun}.md](mevcut_durum_{gun}.md)

**Hazırlanma saati:**

{tarih} {saat}

## 1. Hedef

<!-- doldur: iş hedefi ve ölçü -->

## 2. Mevcut durumdan çıkan sonuçlar (iddialar)

<!--
Her sonuç tek bir doğrulanabilir cümledir (iddia). İşareti (✅ ❌) sen yazma: `orkestra plan dogrula <iş> --yaz` komutu kanıtı yeniden doğrular ve işareti kendisi koyar.

İddia satırı:
- **C1** Doğrulanabilir tek cümle. Dayanak: MD §n.
  - Kanıt: dosya yol/dosya.py:12 "satırdaki alıntı"
  - Kanıt: ara "regex" yol/*.py => 0
  - Kanıt: say yol/test_*.py => >=10
  - Kanıt: komut `komut` => beklenen çıktı parçası
  - Kanıt: deneme yol/deneme.md "alıntı"
  - Kanıt: kaynak https://adres "alıntı" GG.AA.YYYY   (tek başına ✅ vermez)

Kanıtı olmayan ya da yalnız belgeye dayanan iddia ❌ kalır; her ❌ iddia şunlardan en az birini taşır:
  - Spike: hangi denemenin iddiayı kapatacağı
  - Alternatif: iddia tutmazsa izlenecek yol
  - Risk: iddia tutmazsa ne olur

Tahmin ve tercih iddia değildir; "7. Tahminler" bölümüne yaz.
-->

## 3. Kararlar

<!-- doldur: her karar ayrı satır: - **K1:** karar. Neden: ... Dayanak: MD §n -->

## 4. Plan maddeleri

<!-- doldur: her madde ayrı başlık ve zorunlu alanlar:
### P1 Başlık
**Ne:**
**Dayanak:** MD §n (mevcut durum bölümü)
**Dokunulan yer:** MD §3 etki haritasındaki yer
**Gap:** G<n> (MD §6'daki hangi gap'i kapatır; gap'li işlerde zorunlu)
**Sözleşme:** S<n> (sözleşmeli işte zorunlu: bu madde sözleşmedeki hangi başarı kriterini sağlar; `sozlesme_<tarih>.md`)
**Mevcut varlık:** harita kayıt kimliği (virgülle; kimlikten sonra `(not)` ya da `; not` serbest) ya da `yok — <aranan>` (dokunduğun yerde zaten var olan mekanizma; `orkestra harita oku`; haritalı işlerde zorunlu)
**İddialar:** C1, C2   (bu maddenin uygulanabilirliği hangi iddialara bağlı)
**Kapatır:** C5   (yalnız spike maddesinde: bu madde C5'in ❌'sini kapatmak için koşulur)
**Kabul:** ölçülebilir tek ölçüt (komut çıktısı, sayı, dosya:satır); "yapıldı" kabul değildir (kalite kapısında zorunlu)
**Geri alma:** değişikliği geri almanın yolu (kalite kapısında zorunlu)
**Önce:** bu maddeden önce bitmesi gereken P maddeleri (varsa)
**Alternatifler:** en az iki uygulanabilir yaklaşım, madde işaretli ayrı satırlarda: `- Seçilen: … Neden: …` ve `- Elenen: … Neden elendi: …` (P-030; `orkestra standart goster best_in_class`)
Mevcut durumda karşılığı olmayan madde yazılmaz; önce mevcut durum güncellenir. -->

## Gap kapsama

<!-- gap'li işlerde zorunlu (ikinci doğrulama): MD §6'daki her gap bir satır: - **G1** → P1, P2   ya da   - **G3** Kapsam dışı: <gerekçe> -->

## Best in class denetimi

Plan yazarından AYRI `orkestra:denetci` dört soruyu yanıtlar (`orkestra standart goster best_in_class`); sonucu ana ajan buraya yazar. Her satır `✔` ya da `✘` ile başlar.

- **Kök neden:** bekliyor
- **Alternatifler:** bekliyor
- **Kapsam özü:** bekliyor
- **Ölçüm:** bekliyor

**Denetçi:** bekliyor (`orkestra:denetci <agent_id>`)

## 5. Riskler

## 6. Doğrulanmayanlar

## 7. Tahminler

<!-- doldur: doğrulanamayan süre, etki, tercih cümleleri; iddia sayılmaz -->
