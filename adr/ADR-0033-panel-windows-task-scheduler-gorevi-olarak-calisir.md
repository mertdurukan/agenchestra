# ADR-0033: Panel, Windows Task Scheduler görevi olarak çalışır

**Durum:** Kabul edildi

**Tarih:** 22.10.2026

**Bağlam:**

Orkestra paneli (`plugins/orkestra/scripts/panel.py`) bir oturumun hook'u ya da `orkestra panel` komutuyla `subprocess.Popen` ile başlatılıyor. Süreci kimse izlemiyor: kapanınca yeniden başlamıyor, port doluysa 8766 ve sonrasına kayıyor. Tarayıcı yer imi ve `.claude/launch.json` ise `http://127.0.0.1:8765` adresine sabit.

**Karar:**

Panel, kullanıcının oturum açılışında başlayan ve hata sonrası yeniden başlatılan bir Task Scheduler görevi (`Orkestra Panel`) olarak çalışır. Port 8765'e sabittir. `orkestra panel servis kur|kaldir|durum` komutu görevi yönetir. Servis kuruluyken `baslat()` süreç öldürmez ve ikinci panel açmaz; sürüm uyuşmazlığında görevi yeniden başlatır. Çözüm eklenti kaynağında (`Desktop\Claude-Orchestration`) genel biçimde yazılır (P-022).

**Seçenekler:**

- **Windows servisi (NSSM, sc.exe):** elendi. Servis hesabı farklıdır; panel `~/.claude` ve kimlik klasörünü kullanıcı hesabıyla okur. Ek yazılım gerektirir.
- **Başlangıç klasörü kısayolu:** elendi. Çökme sonrası yeniden başlatma yok.
- **Mevcut durum (hook ile Popen):** elendi. Kapanma ve port kayması sorununu çözmez.

**Sonuçlar:**

- **Olumlu:** sabit adres, çökme sonrası otomatik yeniden başlatma, ek yazılım yok, yönetici hakkı gerekmez.
- **Olumsuz:** yalnız Windows (diğer platformlarda komut açık hata verir); kullanıcı oturum açmadan panel çalışmaz.
- **Geri alma:** `orkestra panel servis kaldir`; panel eski Popen yoluyla çalışmaya devam eder.

**İlgili iş:** I-176
