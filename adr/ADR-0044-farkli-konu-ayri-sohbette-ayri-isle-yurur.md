# ADR-0044: Bağlı işten farklı konu ayrı sohbette, ayrı işle yürür

**Durum:** Kabul edildi

**Tarih:** 2026-10-27

**Bağlam:**

Bir sohbette başka işe ait konu (örn. I-239 kapanışı sırasında eklenti yayını sorusu) bağlı işi gölgeliyor ve takibi karıştırıyor. 23.10.2026 tarihli K-004 metni oturum bölmeyi yasaklayıp aynı sohbette işe geçmeyi şart koşuyordu; bu, tek sohbette birden çok işin karışmasına yol açtı.

**Karar:**

Oturum bir işe bağlıyken bağlı işten farklı konu gelirse ana ajan kullanıcıya sormadan `start_session` (initiation user_asked) ile yeni oturum açar; brief'te önce `orkestra is devam <id>` ya da `orkestra is ac` yer alır. Ardından K-007 gereği `detach_session` çağrılır. Bu sohbet bağlı işte kalır; her sohbet tek konu ve tek iş olarak izlenir. "İş bağlama ve yeni iş açma sorulmaz" ilkesi (I-196) korunur. Bağsız oturumda yeni oturum açılmaz.

**Seçenekler:**

- Aynı sohbette işe geçmek (önceki K-004): elendi, takip karışıyor.
- Her seferinde kullanıcıya sormak: elendi, I-196 ile çelişir.
- Yalnız kural metni, hook'suz: elendi, hook her yeni görevde yönergeyi taşıdığı için kaynakta çözülür.

**Sonuçlar:**

Olumlu: ayrı sohbet, ayrı iş, temiz takip. Olumsuz: daha çok oturum. Geri alma: K-004 metnini önceki sürüme döndür ve `is_yonlendirme.yonlendir` metnini eski haline getir.

**İlgili:** K-004, K-007, I-196, ADR-0044
