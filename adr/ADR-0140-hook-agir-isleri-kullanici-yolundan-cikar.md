# ADR-0140: Hook'ta ağır işler kullanıcının bekleme yolundan çıkarılır

**Durum:** Kabul edildi

**Tarih:** 2026-11-01

**Bağlam:**

- Kullanıcı sohbette ciddi yavaşlık bildirdi. Ölçüm (gerçek durum kopyası, n=5): Stop p50 3,8 sn (2 eşzamanlı 19,4 sn), SessionStart p50 14,5 sn; canlı günlükte Stop medyanı 9,7 sn, 134 `hook_zaman_asimi`.
- Neden: Stop, SubagentStop ve SessionStart hook'u panel özetini (`ozet.yaz`) eşzamanlı yazıyor; `ozet.json` kilidi çakışmada 20 sn'ye kadar bekletiyor.
- Oto-commit hook'u tek başına p50 0,62 sn; Edit süresinin yaklaşık %10'u, bu yüzden oto-commit'i arka plana almak (ilk plan P4) uygulanmadı.

**Karar:**

- Hook, özeti kendi sürecinde hesaplamaz: `ozet.yaz_arka_plan` `ozet.json.kirli` sayacını yükseltir ve detached `ozet.py --isci` işçisini başlatır.
- İşçi `ozet.json.kos` kilidini beklemeden dener (işletim sistemi kilidi, log yazmaz); `kirli` > `islenen` olduğu sürece özeti yazar ve kilidi bıraktıktan sonra bir kez daha bakar. `kirli` hiç silinmez, böylece kaçan uyandırma olmaz.
- `ORKESTRA_OZET_ESITZAMANLI=1` eski eşzamanlı yazımı geri getirir; işçi başlatılamazsa hook eşzamanlı yola düşer.
- Diğer çağıranlar (`orkestra.py`, `gosterge.py`) eşzamanlı kalır.
- Aynı ilke sonraki kalemlerde uygulanır: ölçümle doğrulanmayan işte arka plana alma yapılmaz.

**Seçenekler:**

- Kilit bekleme süresini kısaltmak: elendi, 3-4 sn'lik hesabı hızlandırmaz, zaman aşımını sıklaştırır.
- Özeti panel servisine bırakmak: elendi, panel kurulu değilse özet üretilmez.
- Artımlı özet: ertelendi, ayrı geçersiz kılma tasarımı ister; ölçüme göre ayrı iş.
- Oto-commit'i arka plana almak: elendi, ölçülen payı yaklaşık %10 (eşik %50).
- Olay haritası paylaşımı ve eski oturum dosyası eleme (P2): uygulanmadı; `ozet.olustur` artık arka plan işçisinde koşuyor, kullanıcı yolunda kazanç 0.
- Gecikmeli import (P6): uygulanmadı; olası kazanç yaklaşık 0,15 sn (subprocess, shutil, platform, hashlib), ölçüm yayılımından (p90−p50 yaklaşık 0,3 sn) küçük ve cfg/ork_lib genelinde invaziv.

**Sonuçlar:**

- Olumlu: Stop hook'u özet hesabını beklemez; kilit zaman aşımı kullanıcı yolundan çıkar.
- Olumsuz: panel özeti hook dönüşünden birkaç sn sonra tazelenir (arka plan işçisi); işçi hatası `ozet_hata.txt`'ye düşer.
- Geri alma: `ORKESTRA_OZET_ESITZAMANLI=1` ya da `git revert`.

**İlgili:** I-328, P-016, P-028 (ölçüm sonrası ihlal geçişi), ADR-0035.
