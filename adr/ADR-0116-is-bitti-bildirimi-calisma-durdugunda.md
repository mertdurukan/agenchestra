# ADR-0116: "İş bitti" bildirimi yalnız çalışma durduğunda gider

**Durum:** Kabul edildi

**Tarih:** 2026-10-31

**Bağlam:**
"Orkestra: iş bitti" toast'ı Stop kancasında (tur sonu) atılıyordu ve üç kusuru vardı:

- Arka plan görevi (Bash `run_in_background`, zaman aşımıyla arka plana düşen komut, Agent, Workflow) açıkken tur bitince de toast gidiyordu. Kullanıcı tıklayınca sohbette test koşusunun sürdüğünü görüyordu.
- Erteleme yalnız Claude Code'un Stop girdisindeki `background_tasks` alanına bağlıydı. Kanca transkriptten daha güvenilir bir liste (`acik_gorevler`) hesaplıyordu ama toast kararında kullanmıyordu; 17:31'deki Stop'ta açık görev vardı, girdi alanı yoktu.
- Tur süresi (30 sn eşiği) önceki Stop'tan ilk satıra kadar ölçülüyordu; kullanıcının düşünme süresi "tur süresi" sayılıyor, 9 sn'lik bilgi sorusu bile toast atıyordu (ec83dcab oturumu, 17:43).

**Karar:**
Toast kararı tek noktada verilir (`bildirim.tur_sonu`). Girdi alanı ya da transkriptten türeyen açık görev varsa toast gitmez ve çalışmanın başlangıcı (`bildirim_calisma.json`) saklanır. Görev bitince Claude'u uyandıran bildirim turunun sonunda toast gider; süre saklı başlangıçtan ölçülür. Süre, önceki Stop'tan değil, çalışmayı başlatan gerçek kullanıcı isteğinden ölçülür (`ilk_istem_zaman`; görev bildirimleri istek sayılmaz). Görev bildirimi 2 saatten uzun gelmezse toast yine gider. `idle_prompt` bildirimi açık görev varken susar.

**Seçenekler:**

- Yalnız `background_tasks` alanına güvenmek (elendi): alan 17:31 Stop'ında yoktu.
- Toast'ı hep gönderip metnini "tur bitti" yapmak (elendi): kullanıcı yine boşuna çağrılır.
- Panel durumundan sorgulamak (elendi): Stop anında kaynak zaten kancada; ikinci mekanizma gerekmez.

**Sonuçlar:**
Olumlu: toast'a tıklayan kullanıcı bitmiş iş bulur; kısa sorular toast atmaz; uzun arka plan işleri bitince bildirilir. Olumsuz: bitiş bildirimi hiç gelmeyen görev toast'ı 2 saat geciktirir. Geri alma: `hook.py` içindeki `_tur_toast` çağrılarını `bildirim.tur_bitti`ye döndürmek; `ORKESTRA_BILDIRIM=0` toast'ı tümüyle kapatır.

**İlgili iş ya da kural kimliği:** I-299, K-006; testler `tests/test_bildirim.py`, `tests/test_stop_is_bagi.py::StopToast`.
