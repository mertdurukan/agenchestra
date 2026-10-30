# ADR-0103: Sohbet sorularına yanıttan önce aday yolları (skill, MCP, kaynak) saydıran sınırlı not; önce gölge modda

**Durum:** Kabul edildi

**Tarih:** 2026-10-30

**Bağlam:**

Kullanıcı, sohbet sorularına skill, MCP ve kaynak yollarını tarayarak best in class yanıt verilmesini istedi. Bugün UserPromptSubmit hook'u (`hook.py`, `soru_sinif.py`) yalnız iki not ekliyor: bilgi sorusu notu ve ADR-0085 kaynak notu. İkisi de aday yol saymıyor. Kaynak notu 195/200 karakterde dolu. Kullanıcının iki gerçek mesajı soru sayılmadı: 317 karakter "is", 84 karakter "devam" çıktı (I-273 mevcut durum §2).

**Karar:**

- `ayarlar/soru_sinif.json`'a `yol_sozlesmesi` (en çok 300 karakter) ve kapsam ölçütü eklenir; `soru_sinif.yol_metni()` modelsiz Python ile üretir.
- Not, ADR-0085 kaynak notunun hemen ardına eklenir; selam, onay ve kısa devam mesajlarına eklenmez.
- İlk aşama `golge` modudur (P-028): not eklenir ve `gunluk.jsonl`'a `yol_notu` olarak yazılır; yanıt engellenmez, zorlama kapısı yoktur.
- Not, yanıt öncesi adayları sayar (ilgili skill, MCP aracı, kod ya da kayıt, resmi belge), en ucuz yeterli yolu seçtirir; yanıt kısalığı P-001'de kalır.
- Davranış ayrıntısı `skills/yaklasim` skill'indedir; üç kuralı (P-021, P-030, P-031) tek akışta bağlar, yeniden yazmaz.

**Seçenekler:**

- Her soruya `orkestra:triyaj` LLM ön ajanı: elendi; her tura ek model çağrısı ve gecikme getirir, yöntem seçimi ilkesine (önce deterministik kural) aykırı.
- Yalnız yeni kural (P-044; P-036 başka konuda dolu), hook notu olmadan: elendi; kural metni bağlama zaten giriyor ama tetik yok, P-021 ve P-031 de aynı biçimde tek başına yetmedi.
- `kaynak_sozlesmesi` metnini uzatmak: elendi; 200 karakter sınırı ADR-0085'in bağlam şişirmeme kararıdır, ayrı not sınırı korur.
- Sınıflayıcı eşiklerini (`uzun_max_karakter` 300) büyütmek: elendi; "is" akışını (iş açma) etkiler, istenmeyen iş açılır.

**Sonuçlar:**

- Olumlu: yol taraması deterministik tetiklenir, ek model çağrısı yoktur, etki gölge ölçümle sınanır.
- Olumsuz: her ilgili mesaja en çok 300 karakter bağlam eklenir; yanlış pozitif not gereksiz tarama yaptırabilir.
- Geri alma: `yol_sozlesmesi` anahtarını boşaltmak ya da `ORKESTRA_YOL_NOTU=0` notu kapatır; kod değişikliği gerekmez.
- `ihlal` modu ayrı kararla, gölge ölçüm sonrası ve yeni ADR ile.

**İlgili iş ya da kural kimliği:** I-273; P-021, P-028, P-030, P-031, P-001; ADR-0085.
