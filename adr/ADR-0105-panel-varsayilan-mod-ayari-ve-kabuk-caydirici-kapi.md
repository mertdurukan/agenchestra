# ADR-0105: Varsayılan çalışma modu panelin Ayarlar sayfasından yönetilir; kabuk kapısı caydırıcıdır

**Durum:** Kabul edildi

**Tarih:** 2026-10-30

**Bağlam:**

ADR-0103 varsayılan modu `.claude/orkestra/yetki.json` ile getirdi; değişiklik için dosya elle düzenleniyordu. Kullanıcı bunu panelin Ayarlar sayfasından yönetmek istedi.

Panel ucu yerel HTTP'dir; çağıranın kullanıcı mı ajan mı olduğu ayırt edilemez. Ajan kabukla uca yazarsa ADR-0103'ün "ajan yazamaz" kuralı dolaşılırdı.

**Karar:**

- `GET/POST /api/ayarlar?alan=<id>` seçili çalışma alanının varsayılan modunu okur (`varsayilan_mod: {deger, kaynak, alan}`) ve `{"varsayilan_mod": "plan"|"auto"}` gövdesiyle `<alan>/.claude/orkestra/yetki.json` dosyasına atomik yazar. Geçersiz değer 400, bilinmeyen alan 404.
- Ayarlar sayfasında seçili alan için mod seçici ve kaynak etiketi (proje | eklenti | varsayılan) bulunur; makine düzeyi varsayılan sunulmaz.
- İzin hook'u, komutunda `/api/ayarlar` ile POST'a eşdeğer bir yazım biçimi (`-X`, `--request`, `-d/--data`, `-Method`, `-Body`, `requests.post`, `fetch method`) geçen kabuk çağrısını tüm modlarda reddeder.
- Bu kapı **caydırıcıdır, kesin değildir**. Kalan risk: Write ile yazılmış betik çalıştırmak ya da komutta `/api/ayarlar` geçmeyen dolaylı çağrı kapıya takılmaz. Risk kabul edilir.

**Seçenekler:**

- Seçilen: mevcut panel ucunu genişletmek + `_yetki_kapisi` genişletmesi. Tek yer, tek test, açık komutla dolaşmayı caydırır.
- Elenen: tek kullanımlık jeton. Sayfa GET'i jetonu ajana da açar; kullanıcıyı ajandan ayırmaz.
- Elenen: panelde yazma ucu açmamak (yalnız elle dosya). İstenen web yönetimini karşılamaz.
- Elenen: yalnız Origin/Sec-Fetch-Site doğrulaması. curl bu başlıkları taklit eder.

**Sonuçlar:**

- Olumlu: kullanıcı modu dosya düzenlemeden değiştirir; ajanın açık komutla dolaşması reddedilir.
- Olumsuz: kesin ayrım yok; panelde ajan/kullanıcı ayrımı gerektiren kesin çözüm ayrı bir iştir.
- Geri alma: panel ucundaki `varsayilan_mod` dalı ve `_PANEL_YAZIM` kapısı silinir; ADR-0103 davranışı aynen kalır.

**İlgili iş ya da kural kimliği:** I-277, ADR-0103, P-020, K-006
