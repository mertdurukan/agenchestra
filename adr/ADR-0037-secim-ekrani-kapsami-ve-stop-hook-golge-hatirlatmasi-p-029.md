# ADR-0037: P-029 kapsamı karar anını içerir; düz metin seçtirme Stop hook'unda gölgede ölçülür

**Durum:** Yerine geçildi: ADR-0043 (yalnız golge kipi kararı; kalıp, kapsam ve geri alma geçerli)

**Tarih:** 22.10.2026

**Bağlam:**

P-029 yazıldıktan bir saat sonra, bir bilgi sorusunun sonunda çıkan "iki yoldan birini seç" karar anı düz metin yazıldı; seçim ekranı sunulmadı. Üç neden birleşti: (1) P-029 madde 3 bilgi sorularını kapsam dışı sayıyor, karar anı bilgi sorusunun içinde de doğabilir; (2) ADR-0036 `hook.py` zorlamasını "önce kuralın etkisi görülür" diye eledi, bu yüzden uyumu ölçen hiçbir şey yoktu; (3) kural dosyası ana klasörde güncellendi ama commit edilmediği için yeni worktree'ler P-026..P-029 olmadan açıldı.

**Karar:**

P-029 madde 3'e "bilgi sorusunun sonunda çıkan karar anı kapsam İÇİNDEDİR; yanıt kısa kalır ama seçim ekranıyla biter" cümlesi eklendi ve "hook yoktur" cümlesi Stop hook'unu anacak şekilde değişti. Stop yolunda `hook._secim_kapisi_yanit` (P-023 örüntüsü) düz metin seçtirme kalıplarını arar; kalıplar, kip ve seçim aracı adları `ayarlar/secim_ekrani_hatirlatma.json` içindedir. Varsayılan kip `golge`: yalnız `gunluk.jsonl`'a `kural_ihlal / secim_ekrani` yazar, tur engellenmez. Turda `AskUserQuestion` ya da `wrap_up` çağrıldıysa ya da kalıp kod bloğundaysa ihlal sayılmaz. `ORKESTRA_SECIM_HATIRLATMA=0` kapatır. `block` kipine geçiş ölçüm sonrası ayrı kararla ve yeni ADR ile yapılır (P-028).

**Seçenekler:**

- **Yalnız kapsam cümlesi eklemek:** elendi. ADR-0036'daki "uyum yalnız kurala bağlı" riski aynen kalır, ihlal ölçülemez.
- **Doğrudan `block` kipi:** elendi. Kalıplar yanlış pozitif verebilir ("ister misiniz" bilgilendirici cümlelerde de geçer); P-028 yeni kapıların önce gölgede açılmasını ister.
- **Model çağıran sınıflayıcı:** elendi. Her Stop'ta token harcar; deterministik kalıp yeterli ilk adımdır (yöntem seçimi sırası).
- **Sorun yalnız kural dosyası commit'i:** elendi. Commit eksikliği nedenlerden biriydi, ölçüm ve kapsam eksiği ayrıca duruyor.

**Sonuçlar:**

- **Olumlu:** düz metin seçtirme `gunluk.jsonl`'dan sayılabilir; kapsam belirsizliği kapanır; tüm projelerde geçerli (P-022).
- **Olumsuz:** `golge` modunda ajan hatırlatma almaz, yani davranış yalnız ölçülür; kalıplar Türkçe cümle kalıplarına bağlıdır ve eksik kalıp ihlali kaçırır.
- **Geri alma:** `ayarlar/secim_ekrani_hatirlatma.json` içinde `mod: kapali` ya da `ORKESTRA_SECIM_HATIRLATMA=0`; tamamen kaldırmak için `hook.py` içindeki `_secim_kapisi_yanit` fonksiyonu ve çağrısı, modül, ayar ve test silinir; P-029 metni `orkestra kural duzenle` ile eski haline döner.

**İlgili iş:** I-190; kurallar P-029, P-023, P-028, P-022; yerine geçtiği karar: ADR-0036 (hook zorlamasını eleme kısmı)
