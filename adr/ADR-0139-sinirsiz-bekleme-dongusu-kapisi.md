# ADR-0139: Sınırsız bekleme döngüsü kapısı (PreToolUse, golge)

**Durum:** Kabul edildi

**Tarih:** 2026-11-01

**Bağlam:** I-325 oturumunda `until grep -q '^exit=' <dosya>; do sleep 5; done` hiç oluşmayan dosyayı sonsuza dek bekledi; "arka plan 1" görevi açık kaldı. Komut üretilirken sınırı yoklayan bir kapı yoktu (K-006: sorun üretim anında çözülür).

**Karar:**

- `scripts/bekleme_kapisi.py` + `ayarlar/bekleme_kapisi.json`: Bash komutunda `sleep` içeren `until/while` bloğu, sınırı yoksa yakalanır. Kalıplar ayarda durur; mod `kapi_mod` ile okunur; kapatma `ORKESTRA_BEKLEME_KAPISI=0`.
- Sınır sayılanlar: `timeout`, `$SECONDS`, `date +%s`, `for x in`, `seq`; sayaç artırımı ile `-lt/-le/-ge/-gt` ya da `((..<..))` karşılaştırması birlikte; süreç canlılığı (`pgrep`, `kill -0`, `tasklist`) yalnız tek başına koşulsa.
- Sınır sayılmayanlar: dosya var mı testi (`-f -e -s`), tek başına sayısal hedef (`wc -c ... -gt 0`), `until <dosya> && ! pgrep` (dosya hiç gelmezse süreç ölse de döngü bitmez). Görev metnindeki "dosya var kontrolü geçer" bilerek daraltıldı: sorunun kendisi hiç gelmeyen dosyaydı.
- Tırnak içi metin ve heredoc gövdesi veridir, analizden çıkarılır. Yalnız Bash aracı; kanca hata verirse komut bozulmaz.
- Başlangıç modu `golge` (P-028): `kapi_golge` + uyarı. `ihlal` geçişi en az 14 gün ve 30 olay ölçümünden sonra ayrı ADR ile.
- Ret/uyarı metni doğru yolu söyler: `run_in_background` ile başlat, bildirim gelir, çıktı dosyasından oku.

**Seçenekler:**

- Elenen: yalnız hatırlatma kuralı (K-006: üretim anında zorlanmaz, tek başına yetmez).
- Elenen: `genis_tarama_hatirlatma`'ya eklemek (farklı sınıf; kalıplar ve mod ayrı yönetilmeli).
- Elenen: açık arka plan görevlerini sonradan temizleyen süreç (sorunu doğduğu yerde çözmez).
- Elenen: dosya var testini sınır saymak (I-325 vakasını kaçırır).

**Sonuçlar:**

- Olumlu: 01.11.2026 gerçek derlemi (144 `sleep` + `until/while` Bash komutu, ~/.claude oturum günlükleri): 106 sınırsız döngü yakalandı, 38 komut geçti (8 sınırlı döngü, 30 döngü olmayan/veri metni); elle sınıflama sonrası kaçak 0, yanlış pozitif 0. Derlemde 7 kaçak bulundu ve kalıplarla kapatıldı (`SECONDS` yazımı, `until A && ! pgrep`, `while tasklist`).
- Sınırlama: negatif n=38 (<60 hedef); kural-of-three ile yanlış pozitif üst sınırı ≈ %8. İhlal geçişinden önce `kapi_golge` sayısıyla genişletilir. `run_in_background` alanının hook girdisinde görünürlüğü doğrulanmadı; ret metni her iki durumda geçerli.
- Olumsuz: `until` koşulunda `&&` varsa süreç sınırı yok sayılır; nadir sınırlı döngüler golge dönemde uyarı alabilir.
- Geri alma: `ORKESTRA_BEKLEME_KAPISI=0` ya da ayarda `mod` değeri; kancayı kaldırmak `hook.py` içindeki `_bekleme_kapisi` çağrısını silmekle olur.

**İlgili iş ya da kural kimliği:** I-326, K-006, P-028, P-030, ADR-0123 (genis_tarama), ADR-0122 (kapi_mod kalıbı).
