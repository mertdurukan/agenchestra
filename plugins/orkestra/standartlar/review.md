# Review standardı

**Yazar:**

- PR gövdesi pr.md iskeletine uyar, CI yeşildir.
- Review isteği en çok 400 satırlık değişiklikle gelir; büyükse bölünür.

**Reviewer:**

- Önce amaca ve riske bakar: doğru sorunu mu çözüyor, geri alma yolu var mı.
- Yorumlar etiketle başlar: `blocker:` (birleştirmeyi engeller), `öneri:` (isteğe bağlı), `soru:`.
- Her `blocker:` kapanmadan onay verilmez.
- Test, hata yolu, sır ve yetki kontrolü ayrıca sorulur.
- Review 1 iş günü içinde yapılır.

**Birleştirme:** en az bir onay, çözülmemiş `blocker:` yok, CI yeşil. Birleştirmeyi yazar yapar; squash birleştirmede PR başlığı commit başlığıdır.
