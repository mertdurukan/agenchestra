# ADR-0040: K-003 bağlantı satırlarını model değil hook gösterir

**Durum:** Kabul edildi

**Tarih:** 23.10.2026

**Bağlam:**

K-003 kapısı hazır bağlantı satırlarını üretiyor, sonra turu reddedip modelden aynı satırları yanıt metnine yeniden yazmasını istiyordu (`hook._bitis_baglanti_kapisi` PreToolUse reddi, `hook._baglanti_kapisi` Stop block'u). Orkestra belgeyi zaten veriyordu; model satırları ve çoğu zaman belge içeriğini sohbette ikinci kez yazdı. Kök neden: görev modele bırakılmış, oysa girdi tamamen deterministik.

**Karar:**

Bağlantı satırlarını hook kullanıcıya `systemMessage` olarak gösterir; tur reddedilmez, model satır yazmaz ve belge içeriğini sohbete aktarmaz. PreToolUse'ta turu bitiren araç (wrap_up, AskUserQuestion, ExitPlanMode) çağrıldığında işin belge satırları `systemMessage` olarak gider. Stop'ta `baglanti_kapisi` ihlal kipinde, yanıtta bağlantısı olmayan bu turun belgeleri aynı biçimde `systemMessage` ile gösterilir; PreToolUse'ta zaten gösterilen belge Stop'ta tekrarlanmaz. K-003 metni "bağlantıyı hook verir, model yazmaz" diye değişir. Model bağlantıyı yine yazarsa zararsızdır: Stop yalnız bağlantısız belgeyi gösterir.

**Seçenekler:**

- **Mevcut ret ve yeniden yazdırma:** elendi. Modele deterministik işi yaptırır, belge ikinci kez yazılır, her tur bir ret ve bir araç çağrısı maliyeti ekler.
- **Yalnız kural metnine "tekrar yazma" eklemek:** elendi. K-006: kaynak hook'un reddi hâlâ yazdırır, kural tek başına yetmez.
- **Yalnız Stop'a taşımak:** elendi. Bash ile yazılan belgeler `dokunulan`a girmez; PreToolUse imzası bunları da yakalar.

**Sonuçlar:**

- **Olumlu:** belge tek yerde, tek kez görünür; ret turu ve model token'ı kalkar; tüm projelerde geçerli (P-022).
- **Olumsuz:** `systemMessage` sohbet metninin parçası değildir, arayüz uyarı olarak gösterir; satırın yanıtta görünüp görünmediği arayüze bağlıdır.
- **Geri alma:** `ayarlar/belge_bicim.json` `baglanti_kapisi.mod` değerini `golge` yapmak Stop gösterimini keser; eski davranış için bu ADR'nin commit'i geri alınır.

**İlgili iş:** I-083; kurallar K-003, K-006, P-001, P-022
