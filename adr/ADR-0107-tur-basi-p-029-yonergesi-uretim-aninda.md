# ADR-0107: Tur başı P-029 yönergesi (karar cümlesi üretilirken düğmeye yönlendirme)

**Durum:** Kabul edildi

**Tarih:** 30.10.2026

**Bağlam:**

Kullanıcı düz metin onay cümlesinin sonradan engellenmesi yerine üretildiği anda düğmeye yönlendirilmesini istedi (K-006). Bugün P-029 yalnız Stop hook'unda sonradan yakalanıyor (ADR-0043, ADR-0104); `user_prompt_submit` bağlamında P-029 yönergesi yok.

**Karar:**

`ayarlar/secim_ekrani_hatirlatma.json`'a `tur_basi_yonerge` metni (en çok 300 karakter) eklenir; `secim_ekrani_hatirlatma.tur_basi_metni(sd)` onu okur; `hook.user_prompt_submit` her kullanıcı mesajında bağlama ekler. `mod: kapali` ve `ORKESTRA_SECIM_HATIRLATMA=0` kapatır. Stop kapısı yedek ağ olarak kalır.

**Seçenekler:**

- **Mevcut modüle işlev (seçilen):** ayar, kip ve ortam değişkeni hazır; yeni modül yok.
- **Yeni enjeksiyon modülü:** elendi. Aynı ayar ve kapatma mantığını tekrarlar.
- **Yalnız kural metnine cümle:** elendi. Kural zaten var ve yanıt anında bağlamda görünmüyor (ADR-0036).
- **PreToolUse hatırlatması:** elendi. Karar cümlesi araç çağrısız son yanıtta yazılır, hook tetiklenmez.

**Sonuçlar:**

- **Olumlu:** model karar cümlesini yazmadan önce yönergeyi görür; sorun üretildiği yerde ele alınır.
- **Olumsuz:** her mesaja ≤300 karakter bağlam; etkisi ölçülmedi, günlükte `secim_ekrani` kayıtlarının azalmasıyla izlenir.
- **Geri alma:** `tur_basi_yonerge` silinir ya da `ORKESTRA_SECIM_HATIRLATMA=0`.

**İlgili iş:** I-281, P-029, K-006, ADR-0043, ADR-0104.
