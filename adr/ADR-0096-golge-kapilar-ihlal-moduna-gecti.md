# ADR-0096: On gölge kapı ihlal moduna geçti

**Durum:** Kabul edildi

**Tarih:** 2026-10-30

**Bağlam:**

P-028 gölge kapıların ölçümden sonra, kapı başına ayrı kararla `ihlal`e geçmesini ister. Kullanıcı 30.10.2026'da tüm gölge kapıların `ihlal`e alınmasını açıkça istedi. `orkestra is rapor` gölge uyarıları: best_in_class 17, sozlesme 79, paralellik_kapanis 5, sef_ozeti 6 (izole_ortam 5, cikti_butce 409).

**Karar:**

`kapi_mod` kullanan on kapı `ihlal` oldu: sozlesme, teslim, best_in_class, ozet_baslik, paralellik_kapanis, sef_ozeti, auto_kararlar, kapanis_birlestirme, jira_bagimlilik, gorev_turleri. Geçiş kullanıcı kararıyladır; best_in_class'ın kendi ölçütü (en az 30 planda elle sınıflama, 0 yanlış pozitif) karşılanmadı, 17 kayıt vardır. Sonraki yanlış pozitifler kapı başına ayardan `golge`ye dönülerek ya da `ORKESTRA_*_KAPISI=0` ile kapatılır.

**Seçenekler:**

- `izole_ortam`: gölgede kaldı, P-028 "hiçbir modda zorunlu değildir" der.
- `cikti_butce`, `kanitsiz_iddia`, `denetim_politikasi`: `ihlal` değerini tanımaz (farklı mod kümesi: kapali/golge, block/golge/kapali, tam/golge/etkin); değiştirilmedi.
- Ölçütü bekleyip hiçbirini geçirmemek: kullanıcı kararıyla elendi.

**Sonuçlar:**

Olumlu: eksikler artık iş kapanışında/planda reddedilir. Olumsuz: yanlış pozitif iş akışını durdurabilir. Geri alma: ilgili `ayarlar/<kapi>.json` `mod` değerini `golge` yap.

**İlgili:** P-028, ADR-0035, ADR-0095
