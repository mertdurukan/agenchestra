# ADR-0043: Onay ve öneri cümleleri düğme olarak sunulur; P-029 kipi block

**Durum:** Kabul edildi

**Tarih:** 27.10.2026

**Bağlam:**

Kullanıcı, yanıt sonunda düz metin yazılan onay cümlelerinin ("Numaralandırmayı eklemek için 'yap' demen yeterli") düğme olarak sunulmasını istedi. P-029 bu davranışı zaten ister, ama üç boşluk vardı: (1) kip `golge` olduğu için ihlalde ajan uyarı almıyordu (DemoRoot günlüğünde 5 kayıt, davranış değişmedi); (2) kalıplar yalnız "hangisini istersiniz" türünü yakalıyordu, "yap demen yeterli", "onay verirsen", "istersen yaparım", "yapayım mı?" kaçıyordu; (3) boş `actions` ile çağrılan `wrap_up` seçim ekranı sayılıp düz metin onayı aklıyordu.

**Karar:**

(1) `ayarlar/secim_ekrani_hatirlatma.json` kipi `block` olur: ihlalde tur başına bir kez block edilir, uyarı `wrap_up` (ask + actions[0] önerilen, tek öneride 'Yap' düğmesi) ya da `AskUserQuestion` ister. (2) Beş yeni kalıp eklenir (yap-yeterli, onay-ver, onaylarsan, isterseniz-eylem, …ayım mı?). (3) `buton_alanlari` ayarı: seçim aracı yalnız ilgili girdi alanı doluysa (`wrap_up.actions`, `AskUserQuestion.questions`) seçim ekranı sayılır. (4) P-029 metnine madde (6) eklenir.

**Ölçüm (P-028 gereği, K-002):** DemoRoot transkriptlerinde 27.10.2026 10:19'da 2925 tur tarandı; 2153'ünde düğme aracı çağrılmamıştı. Eski kalıplar bunların 80'inde, yeni beş kalıp eski kalıpların yakalamadığı 153 turda daha eşleşti. Bu 153'ten rastgele (tohum 1) 14 örnek elle okundu: 11'i gerçek düz metin onay isteği, 3'ü bilgilendirme ya da sınırda ("istersen yapabileceğin tek şey…"). Kesinlik yaklaşık %79 (n=14, geniş belirsizlik); yanlış pozitifin bedeli tura bir ek hatırlatma turudur ve hatırlatma "karar anı değilse yok say" der. "Sen 'yap' demeden başlamıyorum" gibi bildirimler eşleşmez (negatif test).

**Seçenekler:**

- **`golge` kipinde kalıp eklemek:** elendi. Ajan uyarı almaz; 5 kayıtlı gölge dönemde davranış değişmedi.
- **Her yanıta zorunlu `wrap_up`:** elendi. Bilgi soruları P-001 kadar kısa kalır, kullanıcı soruya boğulur.
- **Model çağıran sınıflayıcı:** elendi. Her Stop'ta token harcar; deterministik kalıp ve ölçüm yeterli (yöntem seçimi sırası).
- **Yalnız kural metnine cümle eklemek:** elendi. ADR-0036'daki "uyum yalnız kurala bağlı" riski aynen sürer.

**Sonuçlar:**

- **Olumlu:** "yap demen yeterli" yerine tek tık; ajan düz metin onayı yazdığı turda düzeltmeye zorlanır; boş düğmeyle aklama kapanır.
- **Olumsuz:** kalıp yanlış pozitif verirse tura bir ek hatırlatma turu eklenir (hatırlatma "gerçek karar anı değilse yok say" der); Türkçe kalıplara bağlı, eksik kalıp ihlali kaçırır.
- **Geri alma:** ayarda `mod: golge` ya da `kapali`, ya da `ORKESTRA_SECIM_HATIRLATMA=0`; `buton_alanlari` silinirse eski davranış (araç adı yeter).

**İlgili iş:** kural P-029, P-028 (gölge ilkesi, kullanıcı kararıyla geçiş), P-001; ADR-0036 ve ADR-0037 (hook zorlaması kip kararı: yerine geçildi bu ADR ile).
