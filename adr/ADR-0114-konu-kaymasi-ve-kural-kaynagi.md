# ADR-0114: Konu kayması mekanik yakalanır, kural davranışında esas kaynak eklentidir

**Durum:** Kabul edildi

**Tarih:** 2026-10-31

**Bağlam:**

ADR-0044 (27.10) bağlı işten farklı konunun ayrı sohbette yürümesini öngördü, ama pratikte bağlı sohbette konu kayması sürüyor. Kaynak kodda dört neden bulundu: bilgi sorusu ve kısa mesaj yönlendirmeyi susturuyor (`soru_sinif.py:133-142`), ilişki ölçütü iş belgesinin ilk 6000 karakterine dayanıyor (`hook.py:1960`), bölme yalnız metin yönergesi (`is_yonlendirme.py:171`), proje kuralı kopyası ilk oturumda bayat yükleniyor (`onay.py:321`).

Aynı kopya gecikmesi, ajanın orkestra davranışını eski K-004 metninden yanlış anlatmasına yol açtı.

**Karar:**

(1) Eşitleme kopyayı yeniden yazdıysa değişen kuralların özeti SessionStart bağlamına konur. (2) P-021'e "orkestra davranışı anlatılırken eklenti kaynağı esastır" cümlesi eklenir. (3) Kayma sınıflayıcısı bilgi sorusunu da iş başlığı ve güncel niyetle sınar; onay ve kısa mesaj muaf kalır. (4) Bölme gölge modda mekanik kapıyla ölçülür; ihlale geçiş ölçümden sonra ayrı kararla. (5) Yeni sohbetin modu brief'in ilk satırında taşınır.

**Seçenekler:**

- Hook'un oturumu kendisi açması: elendi, hook araç çağıramayabilir (P1 spike ile teyit edilecek).
- LLM sınıflayıcı: elendi, önce deterministik kural; belirsizlik ölçümde görünürse eklenir.
- Kullanıcıdan oturumu yeniden başlatmasını istemek: elendi, kullanıcıya iş bırakır.
- ADR-0044'ü yerinde düzenlemek: elendi, karar geçmişi kaybolur.

**Sonuçlar:**

Olumlu: farklı konu mesaj türünden bağımsız yakalanır; kopya gecikmesi aynı oturumda kapanır. Olumsuz: yanlış pozitifle gereksiz oturum açılabilir; eşik ölçümle (n≥240, yanlış pozitif ≤%5 (Wilson üst ≤%10), kaçırma ≤%10 (Wilson üst ≤%20)) belirlenir. Geri alma: ayar dosyalarında `mod: kapali`; ADR-0044 durumunu "Kabul edildi"ye döndür.

**İlgili:** I-297, ADR-0044, K-004, K-007, P-021, P-028
