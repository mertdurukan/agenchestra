# ADR-0036: Karar anlarında düz metin yerine seçim ekranı (P-029)

**Durum:** Kabul edildi

**Tarih:** 22.10.2026

**Bağlam:**

`orkestra guncelle` sonrası izin sistemi `orkestra is anlati --help` komutunu reddetti; ajan seçenek sunmak yerine düz metinle onay istedi. P-008 izin reddinde "neyi neden yapmak istediğim söylenir ve onay istenir" der, ama biçim belirtmez. Altyapı hazırdı: `scripts/is_onay.py:290` içindeki `TUR_BITIREN` ve `scripts/niyet.py` içindeki açık soru okuyucusu `AskUserQuestion` ve `wrap_up` çağrılarını zaten tanıyor. Eksik olan kullanım kuralıydı.

**Karar:**

P-029 eklenti katmanında kural olarak yazıldı. Karar, onay ve yöntem seçimi anlarında (izin reddi, doğrulanamayan adım, birden çok yol, onay) kullanıcıya `AskUserQuestion` ya da `wrap_up` butonlarıyla seçim ekranı sunulur: 2-4 seçenek, önerilen ilk sırada. Bilgi soruları ve küçük adımlar kapsam dışıdır. Alt ajan kullanıcıya doğrudan soru sormaz; seçenekleri raporuyla ana ajana döner, ekranı ana ajan sunar. P-008'in son cümlesi P-029'e atıf yapar. Hook değişikliği bu kararın parçası değildir.

**Seçenekler:**

- **Yalnız P-008 metnini genişletmek:** elendi. İzin reddi dışındaki karar anları (birden çok yol, doğrulanamayan adım) kapsanmaz.
- **`hook.py` ile düz metin onayı yakalayıp zorlamak:** elendi. Önce kuralın davranışı değiştirip değiştirmediği görülür; `hooks/hooks.json` ve `scripts/izin_politikasi.py` başka işte değişiyor. İhlal sürerse ayrı iş açılır.
- **Her soruya seçim ekranı:** elendi. Kullanıcıyı soruya boğar; bilgi soruları P-001'e göre kısa yanıtla kalır.

**Sonuçlar:**

- **Olumlu:** karar anları tek tıkla yanıtlanır, önerilen seçenek önde olur, izin reddinde ajanın ne istediği açık kalır.
- **Olumsuz:** hook zorlaması olmadığı için uyum yalnız kurala bağlıdır; "gerçek karar noktası" sınırı yoruma açıktır.
- **Geri alma:** `orkestra kural kaldir P-029` ve `orkestra kural esitle`; P-008 atfı `orkestra kural duzenle` ile eski metne döndürülür.

**İlgili iş:** I-068; kurallar P-029, P-008, P-022, P-015
