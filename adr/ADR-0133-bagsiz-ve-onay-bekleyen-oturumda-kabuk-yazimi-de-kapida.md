# ADR-0133: Bağsız ve onay bekleyen oturumda dosya yazan kabuk komutu da kapıdan geçer

**Durum:** Önerildi

**Tarih:** 2026-11-01

**Bağlam:**

Gelen kutusu sağ paneli işi iş açılmadan, onaysız ve ADR'siz yazıldı (I-318). Bağsız yazım kapısı `_is_kapisi` yalnız Write/Edit/MultiEdit/NotebookEdit dalında çağrılıyor (hook.py:1070); kabuk dalında çağrılmıyor (hook.py:1131-1148). Panel kodu python heredoc, sed ve cat ile yazıldığı için kapı hiç tetiklenmedi. Onay kapısı da proje kökleri dışındaki yolları serbest bırakıyor (is_onay.py:397-399); eklenti kaynağı ayrı depoda olduğundan onay beklerken de yazılabilir. Uyarı metni "bağlanmadan dosya yazılamaz" diyerek kabuk için yanlış vaat veriyor (hook.py:2072).

**Karar:**

- Kabuk dalında, dosya yazma işleci içeren komut bağsız oturumda reddedilir; hedef geçici dizin (scratchpad, %TEMP%) ise ya da komut salt okunur ise serbesttir.
- Onay bekleyen bağlı işte, iş belgeleri ve adr/ dışındaki kalıcı yola yazım (Write/Edit ve kabuk) proje kökü dışında da reddedilir; geçici dizinler ve kullanıcı hafıza klasörü hariçtir.
- Kapı kapı modu ayarından (`kapi_mod.py`) çalışır, kapatma ORKESTRA_BAGSIZ_KABUK_KAPISI=0, hatada fail-open.
- Red ve uyarı metni kapsamı doğru söyler ve bağlanma komutunu verir.
- Yeni kapının başlangıç modu plan onayında kullanıcı kararıyla seçilir (P-028 gölge ya da P-033 emsali ihlal).

**Seçenekler:**

- Yalnız uyarı metnini yumuşatmak: elendi; kusur belgelenir ama davranış aynı kalır, bu oturum aynı biçimde tekrarlanır.
- Sonradan yakalayan Stop hook'u (tur sonunda bağsız yazım tara): elendi; yazım zaten yapılmıştır, K-006 üretim anında önlemeyi ister.
- Kabuk komutlarının tamamını bağsız oturumda yasaklamak: elendi; okuma, test ve tanılama da engellenir, yanlış pozitif oranı kabul edilemez.

**Sonuçlar:**

- Olumlu: iş bağlama, onay ve ADR kapıları araç türünden bağımsız çalışır; tüm orkestra kullanıcılarına eklentiyle gelir.
- Olumsuz: kabuk yazımı tespiti en iyi çabadır, dolaylı betik yazımları kaçabilir; yanlış pozitifler geçici dizin muafiyetiyle azaltılır.
- Geri alma: ORKESTRA_BAGSIZ_KABUK_KAPISI=0 kapıyı kapatır; kod değişikliği tek commit'te geri alınır.

**İlgili iş ya da kural kimliği:** I-318; K-004, K-006, P-015, P-016, P-022, P-028.
