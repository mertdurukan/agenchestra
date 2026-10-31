# ADR-0128: Eşzamanlı kaynak çakışmasında önce paylaşımı kaldır, kilidi sona bırak

**Durum:** Kabul edildi

**Tarih:** 01.11.2026

**Bağlam:** Birden çok sohbet ve ajan aynı anda çalışınca ortak kaynaklar çakışıyor.

Ölçüm (`scripts/kilit_olcum.py`): `ozet.json` kilidinde 118 zaman aşımı, 101'i 31.10.2026'da, ortalama bekleme 20.011 ms.

Tam test takımının (`scripts/test_paralel.py`) süreçler arası koruması yoktu.

P3 ölçümü C6 iddiasını doğruladı: zaman aşımının nedeni kilit altındaki yeniden hesaptır; 20 tekrar x 8 eşzamanlı soğuk `ozet.yaz` çağrısında `olustur` sayısı 160'tan 24'e indi, zaman aşımı satırı 0.

P2 testi klasör numarası (NNN) yarışının olmadığını gösterdi: bariyerli iki süreç 100 tekrarda 100/100 farklı numara üretti (kilitsiz kopyada 12/30 çakışma).

**Karar:** Çözüm sırası:

- (1) ölç;
- (2) paylaşımı kaldır ya da işi birleştir (coalescing, sonuç önbelleği, tek uçuş);
- (3) yalnız kalan tekil kaynağa lease ve adil kuyruk.

Mevcut `ork_lib.kilit` (FIFO bilet) yeniden kullanılır, ikinci kilit sistemi kurulmaz.

Yeni kapılar P-028 gereği `golge` modunda açılır: test kirası (`ayarlar/kaynak_kira.json`) ve çıplak test koşusu yönlendirmesi (`test_yonlendirme`, hook.py PreToolUse). Hedefli test çağrısı (tek dosya, `-k`, unittest modülü) yönlendirme kapsamı dışındadır.

**Seçenekler:**

- Elenen: yalnız kural ya da istem ("başka ajan test koşuyorsa bekle"). Ajan göremediği durumu bilemez.
- Elenen: merkezi kuyruk servisi. Tek hata noktası olur, dosya kilidi aynı işi daha ucuza yapar.
- Elenen: ağaç başına tam izolasyon. Git indeksi ve ortak durum gibi gerçekten paylaşılan kaynakları çözmez.
- Elenen: bekleme süresini artırmak. Belirtiyi gizler, kuyruğu uzatır.

**Sonuçlar:** Olumlu: kök neden giderilir, kilit sayısı azalır; `ozet.json` yeniden hesabı P3 ölçümünde 160'tan 24'e indi.

Olumlu: NNN için ek kilit gerekmedi (P2, 100/100); yalnız GELISTIRME.md düzeltildi.

Olumsuz: önbellek geçersiz kılma mantığı ek karmaşıklıktır.

Gölge dönemi: `kaynak_kira` ve `test_yonlendirme` kapıları `kapi_golge` kaydı yazar, engellemez; ihlal geçişi `orkestra is rapor` sayıları ölçüldükten sonra ayrı kararla yapılır.

Geri alma: her parça ayarla kapatılır (`kaynak_kira.json` mod alanı `kapali`, `ORKESTRA_TEST_YONLENDIRME=0`) ve ayrı commit'tir.

**İlgili iş ya da kural kimliği:** I-309, P-028, P-029 yanında K-006, P-022.
