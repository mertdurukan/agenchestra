# ADR-0034: Panel servisi eklentiyi kullanan herkes için otomatik kurulur

**Durum:** Kabul edildi

**Tarih:** 22.10.2026

**Bağlam:**

ADR-0033 paneli Task Scheduler görevi yaptı, ama kurulum elle (`orkestra panel servis kur`) ve yalnız bu makinede yapıldı. Sorun (panel kapanıyor, farklı portta açılıyor) orkestra eklentisini kullanan herkesin sorunu; çözümün de herkeste varsayılan olması gerekir (P-022). Eklenti güncellenince `panel.py` yolu değişir ve eski görev bozulur.

**Karar:**

SessionStart hook'u Windows'ta `panel_servis.otomatik_kur()` çağırır: görev yoksa kurar, görev başka bir eklenti yolunu gösteriyorsa yeniden kaydeder. Görev oturum açılışında (Windows başlangıcı) başlar. Makine başına işaret dosyası (`~/.claude/orkestra-panel/panel_servis.json`) durumu tutar: `kaldirildi` ise (kullanıcı `servis kaldir` dedi) yeniden kurulmaz; aynı eklenti yoluyla `hata` ise tekrar denenmez. `ORKESTRA_PANEL_SERVIS=0` kurulumu kapatır. Kural eklenti katmanına P-027 olarak yazıldı.

**Seçenekler:**

- **Yalnız elle kurulum:** elendi. Kullanıcıların çoğu komutu bilmez; sorun sürer.
- **Yönetici hakkıyla önyükleme (boot) görevi:** elendi. Panel kullanıcı hesabının `~/.claude` klasörünü okur; oturum açılışı zaten kullanıcının çalışmaya başladığı andır ve yönetici hakkı gerektirmez.
- **Her SessionStart'ta görevi doğrula:** elendi. Her oturumda `schtasks` çağrısı gerekir; işaret dosyasındaki eklenti yolu eşleşince çağrı yapılmaz.

**Sonuçlar:**

- **Olumlu:** her Windows kullanıcısında sabit adres, ek adım yok, güncellemede kendi kendini onarır.
- **Olumsuz:** eklenti kullanıcının makinesinde Task Scheduler kaydı oluşturur; kapatma yolu (`servis kaldir`, ORKESTRA_PANEL_SERVIS=0) belgelidir.
- **Geri alma:** `orkestra panel servis kaldir` görevi siler ve yeniden kurulumu engeller; hook çağrısı kaldırılarak otomatik kurulum tamamen sökülür.

**İlgili iş:** I-176; ADR-0033; kural P-027
