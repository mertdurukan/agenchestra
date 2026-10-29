# ADR-0097: ADR, kararın etkilediği depoda yazılır (hedef depo = planın Kök deposu)

**Durum:** Önerildi

**Tarih:** 2026-10-30

**Bağlam:** ADR kapısı (P-015) yalnız işin açıldığı projenin `adr/` klasörüne bakıyor. Eklenti davranışını değiştiren kararlar McD'ye yazıldı (84 dosyanın 36'sı eklentiyi anıyor); eklenti deposunda 13 ADR var, ADR-0096 iki depoda farklı içerik taşıyor, McD'nin uzak deposu olmadığından 77 ADR dosyası yedeksiz. Kullanıcı: "Orkestra içerisinde tutmak daha best in class değil midir?"

**Karar:**

- **Hedef depo:** Planın `**Kök:**` satırının git deposu. Kök başka bir depoyu gösteriyorsa ADR o deponun `adr/` klasörüne yazılır ve kapı orada arar; `**Kök:**` yoksa ya da aynı depoysa eski davranış (proje kökü).
- **Üretim noktası:** `orkestra adr yeni <iş> "<başlık>"` hedef depoyu çözer, o depodaki en büyük numaranın sonrasını verir ve altı alanlı iskeleti yazar; ADR elle doğru yere konmaz, doğru yerde doğar.
- **Numara:** her deponun numarası kendi içinde ardışıktır; depo dışından atıf `eklenti ADR-0097` gibi depo adıyla yazılır. Yeni önek biçimi getirilmez.
- **Yedek:** `orkestra doktor` uzak deposu olmayan ADR deposunu uyarır; uzak depo açmak kullanıcı kararıdır.

**Seçenekler:**

- **Hep işin projesine yazmak (bugün):** elendi; eklenti kararı eklentiyi kullanan başka kullanıcıya gerekçesiyle gitmez, depolar arası numara çakışır.
- **Depo adı için ayrı ayar dosyası:** elendi; planda zaten `**Kök:**` var, ikinci kaynak tutarsızlık doğurur.
- **Tek global numara uzayı ya da `ADR-E-nnnn` öneki:** elendi; harita, anlatı ve kapı desenlerini değiştirir, kazancı depo adıyla atıftan küçük.
- **Toplu taşıma (36 ADR):** bu işte yapılmaz; içerik yargısı ve yeniden numaralama riski.

**Sonuçlar:**

- **Olumlu:** karar kodla aynı depoda yayınlanır ve yedeklenir; numara üretimi elle yapılmaz.
- **Olumsuz:** iki depoda aynı numara sürer (geçmiş çakışma); depo adı atıfta zorunlu olur.
- **Geri alma:** `**Kök:**` çözümünü kapıdan çıkarmak eski davranışı geri getirir; komut ve doktor kontrolü bağımsız silinir.

**İlgili iş:** I-256 (McD); P-015, P-022; ADR-0098 (McD, I-254) bu karara taşınır.
