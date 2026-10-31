# ADR-0115: Eklentinin varsayılan çalışma modu `auto` olur

**Durum:** Kabul edildi

**Tarih:** 2026-10-31

**Bağlam:**

ADR-0103 eklenti varsayılanını `plan` bıraktı; `auto` için her projede proje ezmesi gerekiyordu. Kullanıcı tüm sohbet ve konularda varsayılanın `auto` olmasını, `/plan` yazınca `plan` olmasını ve ayarlardan `plan`a çevrilebilmesini istedi. Mekanizma (açık `/plan` ve `/auto` varsayılanı geçer; panel Ayarlar seçicisi, ADR-0105) zaten var.

**Karar:**

(1) Eklentinin `ayarlar` klasöründeki varsayılan mod ayarı `auto` olur; değeri yalnız kullanıcı değiştirir (ADR-0103 madde 4, P-020). (2) `is_onay.varsayilan_mod` kod yedeği `plan` kalır: ayar yok, bozuk ya da tanınmıyorsa `plan`. (3) Kesin sınırlar (zorla push, kalıcı silme, kimlik, sır, DB salt okunur) `auto` altında aynen geçerlidir. (4) Mod testleri eklenti ayar değerinden bağımsız yazılır (`tests/mod_yalitim.py`).

**Seçenekler:**

- Kod yedeğini `auto` yapmak: elendi. Bozuk ayarda gevşek moda düşer.
- Her projede ezme dosyası: elendi. Yeni projede unutulur; istek "her konuda" idi.
- Testleri `auto` bekleyecek biçimde değiştirmek: elendi. Kullanıcı değeri geri alırsa kırılır.

**Sonuçlar:**

Olumlu: onay beklemeden akış varsayılan olur. Olumsuz: P-016 onay kapısı varsayılanda belgeler tamamsa kendiliğinden geçer. Geri alma: varsayılan mod ayarı `plan` yapılır (panel Ayarlar ya da dosya).

**İlgili iş:** I-295, ADR-0103, ADR-0105, P-016, P-020
