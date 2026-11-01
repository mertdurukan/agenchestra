# ADR-0131: Test kirası ve çıplak test yönlendirmesi ihlal moduna, test sonucu önbelleği açık

**Durum:** Kabul edildi

**Tarih:** 01.11.2026

**Bağlam:** ADR-0130 iki kapıyı P-028 gereği `golge` modunda açtı: test kirası (`ayarlar/kaynak_kira.json`) ve çıplak test koşusu yönlendirmesi (`test_yonlendirme`, hook.py PreToolUse). Test sonucu önbelleği (`onbellek`) kapalı başladı.

Kullanıcı, eşzamanlı tam test koşularının çekirdek ve belleği aşmasının hemen önlenmesi için üç parçanın da açılmasına karar verdi.

Ölçüm (`python scripts/kilit_olcum.py --sd C:\Work\DemoRoot\.claude\orkestra`, 01.11.2026 10:17): `kapi_golge` içinde `test_yonlendirme` 0, `kaynak_kira` 0, `test_onbellek` 0; gunluk.jsonl'da "BAYAT" isabet kaydı 0.

Gölge dönemi çok kısaydı (aynı gün açıldı). Sıfır sayılar "yanlış pozitif yok" kanıtı değildir, yalnız ölçülecek olay henüz olmadığını gösterir; önbellek gölgeye hiç alınmadığı için BAYAT sayısı ölçülmemiştir.

**Karar:**

- `kaynak_kira.json`: `mod` → `ihlal` (kuyrukta beklenir, işçi bütçeyle kısılır).
- `kaynak_kira.json`: `onbellek` → `true` (isabet ve tek uçuş uygulanır).
- Yeni `ayarlar/test_yonlendirme.json`: `mod` → `ihlal`. Çıplak tam koşu reddedilir; ret iletisi tam takım komutunu (`python …/test_paralel.py`) ve hedefli seçenekleri (dosya, `::`, `-k`, unittest modülü) verir.
- Hedefli ve test koşmayan çağrılar hiçbir modda engellenmez.
- Kod varsayılanları (ayar dosyası yok ya da bozuk) güvenli yönde kalır: kira `golge`, önbellek kapalı.
- Yanlış pozitif ölçümü ihlal modunda `kapi_ret` kayıtlarıyla sürer.

**Seçenekler:**

- Seçilen: üç parçayı birlikte ihlale almak. Kullanıcı kararı; kira ve önbellek aynı koşucu yolunda (test_paralel.py) bağlıdır.
- Elenen: P-028'e göre önce gölgede ölçmek. Gölgede hiç olay birikmemişti; kullanıcı beklemeyi istemedi.
- Elenen: yalnız kirayı ihlale alıp önbelleği gölgede bırakmak. Aynı kod için tekrar eden tam koşuları önlemez.
- Elenen: kod varsayılanlarını da ihlal yapmak. Bozuk ya da eksik ayarda sessiz engelleme riski doğar.

**Sonuçlar:**

- Olumlu: eşzamanlı tam koşular makine bütçesini aşmaz; aynı kod için ikinci tam koşu süreç açmadan önbellekten döner; çıplak tam pytest kirayı atlayamaz.
- Olumsuz: bayat "geçti" riski gölgede ölçülmeden açıldı. Riski anahtar (eklenti kökünün tam içerik özeti, argüman, ortam, yorumlayıcı) ve 3600 sn geçerlilik sınırlar.
- Olumsuz: anahtar kiradan önce hesaplanır (~0,5 sn); kuyruk "sıra:" satırı ondan sonra gelir. P4 uçtan uca testi sahibi sabit süre yerine olayla tutacak biçimde düzeltildi.
- Geri alma: proje ezmesi `.claude/orkestra/kaynak_kira.json` (`mod: golge|kapali`, `onbellek: false`) ve `.claude/orkestra/test_yonlendirme.json` (`mod: golge`); ortam değişkenleri `ORKESTRA_KAYNAK_KIRA=0`, `ORKESTRA_TEST_ONBELLEK=0`, `ORKESTRA_TEST_YONLENDIRME=0`.

**İlgili iş ya da kural kimliği:** I-309, ADR-0130 (güncellemesi), P-028.
