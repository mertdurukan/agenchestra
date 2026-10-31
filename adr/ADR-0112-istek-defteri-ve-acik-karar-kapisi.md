# ADR-0112: İstek defteri ve açık karar kapısı

**Durum:** Kabul edildi

**Tarih:** 2026-10-31

**Bağlam:** 29.10'da kullanıcı caveman dahil 17 bağlantı gönderdi; caveman "MCP değil" diye sorulmadan dışarıda kaldı. Kök neden: mevcut durumdaki "Karar gerekir" maddelerini plan yazarı kendisi kapattı, kullanıcıya tek toplu onay gitti. `scripts/is_sirasi.py` bu ifadeyi denetlemiyordu. Kapsam işin başında 17'den 15'e daraldı; kapanış denetimi daralmış kapsamı referans alırdı.

**Karar:**

- **Açık karar kapısı:** Mevcut durum §5'teki her "Karar gerekir" maddesinin karşısında kullanıcı yanıtı aranır. Yanıt yalnız `is.json` karar kaydından sayılır; plan ya da mevcut durum metnine yazılan satır sayılmaz.
- **İstek defteri:** İş açılırken mesajdaki her bağlantı ve talep kimlikli madde (R1…Rn) olur; işin klasöründe `istek_defteri.md` tutulur. Bağlantıları betik çıkarır; serbest metin taleplerini ajan çıkarıp kullanıcıya gösterir.
- **Kapılar:** Plan ve kapanış kapısı her maddeyi denetler: planda var ya da kullanıcı yanıtı kayıtlı olarak çıkarılmış olmalı. İlk sürüm P-028'e göre gölge modundadır.

**Seçenekler:**

- **Yalnız kapanışta kapsama denetimi:** elendi; sonradan yakalar (K-006), kapsam başta daralmışsa referansı da dardır.
- **Yalnız kural metni (P-029 genişletme):** elendi; sessizce kapatılmış kararı yakalamaz.
- **Yalnız `is.json` karar alanı + hook:** elendi; bağlantı kaybını yakalamaz, defter bu alanı kullanır.

**Sonuçlar:**

- **Olumlu:** istek ile çıktı arasındaki kayıp başta görünür; kapsam dışı yalnız kullanıcı yanıtıyla olur.
- **Olumsuz:** serbest metin taleplerinin çıkarılması model işidir, doğruluğu ilk sürümde ölçülmez; kullanıcıya onaylatılır. Her işe biraz sürtünme ekler.
- **Geri alma:** `ORKESTRA_KARAR_KAPISI=0` ve `ORKESTRA_ISTEK_DEFTERI_KAPISI=0` kapıları kapatır. İhlal moduna geçiş için `orkestra is rapor` ile en az 30 iş ve yanlış pozitif 0 gerekir; geçişte yeni ADR yazılır.

**İlgili iş ya da kural kimliği:** I-291; P-015, P-016, P-017, P-028, P-029, K-006.
