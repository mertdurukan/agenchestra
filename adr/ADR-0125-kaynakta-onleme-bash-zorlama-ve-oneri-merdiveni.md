# ADR-0125: Sınırsız Bash taraması komut yazıldığı anda zorlanır; sohbet düzeltme önerisi önleme merdiveninden geçer

**Durum:** Kabul edildi

**Tarih:** 2026-10-31

**Bağlam:** I-294 sohbetinde `find /c/Mert/McD -name karar_kapisi.py` 19:07'den 20:00'ye kadar koştu. ADR-0039 gölge kapısı uyarıyı aynı sohbette 6 satırda verdi; uyarı zorlama olmadığı için komut yine de çalıştı. Aynı sohbette ajanın ilk düzeltme önerisi çözümü model alışkanlığına ve tur sonu hatırlatmaya koydu; mevcut gölge kapıyı ve önleme merdivenini (ADR-0111) aramadı. Kök neden metni (ADR-0101) merdiveni ve mevcut mekanizma aramasını sormuyor.

**Karar:**

- **Bash koruması:** `genis_tarama` kapısı gölgeden zorlama basamağına çıkar: geniş kökte zaman sınırsız `find` PreToolUse'ta komut koşmadan reddedilir; ret metni hazır düzeltilmiş komutu (`timeout 20 find …`) ve Glob/Grep seçeneğini verir. `-maxdepth`, `-prune`, `timeout` ve dar yol taşıyan komut geçer. Hook süreç öldürmez. Stop satırı arka plan görevini yaşıyla gösterir, 10 dakikadan eskiyi işaretler ve Windows'ta çocuk `find.exe` süreçlerini listeler.
- **Öneri kapısı:** `standartlar/kok_neden.md` Hata anı bölümüne iki adım eklenir: (1) düzeltme önermeden önce o sınırda mevcut mekanizma aranır, (2) düzeltme önleme merdiveninin (ADR-0111) en üst uygulanabilir basamağına göre kurulur; sonradan yakalayan kontrol ancak üst basamakların neden uygulanamadığı yazılarak önerilir. Stop'ta gölge yanıt denetimi, düzeltme önerip basamak cümlesi içermeyen yanıtı `kural_ihlal / onleme_basamagi` olarak günlüğe yazar; engellemez.
- **Mod:** [D1] Bash kapısı ilk günden `reddet` kipindedir, yalnız `find` için ve dar sınıfta (P-028 sapması kullanıcı kararıyla); `grep -r` gölgede kalır. [D2] Yanıt denetimi `golge` başlar; ihlale ya da uyarıya geçiş eşiği 30 tetik ve 0 yanlış pozitiftir (`ayarlar/onleme_yanit.json` gecis_esigi).

**Seçenekler:**

- Gölge kapıyı koruyup uyarı metnini güçlendirmek: elendi, 6 uyarı satırı komutu durdurmadı (kanıt: I-294 olayı).
- `updatedInput` ile komutu `timeout` ile sarmak: elendi, `updatedInput` yalnız allow/ask ile belgeli; varsayılan modda ek onay sorusu çıkarır, macOS'ta `timeout` yoktur.
- Hook'un arka plan sürecini öldürmesi: elendi, kapatma kararı kullanıcıda ya da ajandadır; hook yalnız listeler.
- Öneri kapısı için yalnız metin ya da yalnız Stop denetimi: elendi, tek başlarına ya modelin uymasına dayanır ya da üretimden sonra yakalar; ikisi birlikte metin üretim anında, denetim ölçüm için çalışır.
- Plan kapısını (P-019, P-033) sohbete genişletmek: elendi, sohbet yanıtında PreToolUse sınırı yoktur ve her yanıt plan değildir.

**Sonuçlar:**

- Olumlu: sınırsız tarama komut koşmadan durur; arka plana düşen görev yaşıyla görünür; düzeltme önerileri merdivenle kurulur ve ölçülür.
- Olumsuz: dar kalıp yanlış pozitif verebilir (meşru geniş `find` reddedilir); yanıt denetimi sezgiseldir, gölgede kalır.
- Geri alma: `ORKESTRA_GENIS_TARAMA=0` zorlamayı, `ORKESTRA_ONLEME_YANIT=0` yanıt denetimini kapatır; commit'ler geri alınır; ayar dosyasında `mod: golge` bugünkü davranışı verir.

**İlgili iş ya da kural kimliği:** I-305, ADR-0039, ADR-0101, ADR-0111, P-012 madde 4, P-028, P-030, P-033, ADR-0111, K-006
