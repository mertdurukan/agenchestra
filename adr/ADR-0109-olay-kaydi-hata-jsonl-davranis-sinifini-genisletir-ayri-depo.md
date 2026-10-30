# ADR-0109: Olay kaydı hata.jsonl davranış sınıfını genişletir, ayrı depo açılmaz

**Durum:** Kabul edildi

**Tarih:** 2026-10-30

**Bağlam:**

Kullanıcı, orkestranın süreçteki olayları ve sonuçlarını kaydedip gidiş yolu önermesini istedi. Olaylar `gunluk.jsonl` ve `hata.jsonl` içinde kategorisiz ve sonuçsuz dağınık duruyor (30.10.2026 17:28: 9987 ve 466 satır).

**Karar:**

Ayrı depo açılmaz. `hata.jsonl` davranış sınıfı ve perspektif hattı genişletilir: ana ve alt kategori `ayarlar/olay_kategorileri.json` eşlemesiyle okuma anında verilir, sonuç (acik, duzeldi, tekrarladi) okuma anında türetilir, yazılmaz. Gidiş yolu önerisi yalnız n en az 5 ve Wilson alt sınırı en az 0,5 çiftlerde, şablonla çıkar. Kapı `ayarlar/olay_kaydi.json` ile gölgede açılır.

**Seçenekler:**

- Elenen: ayrı `olay.jsonl` deposu. İmza, maskeleme ve okuyucuları yineler.
- Elenen: olay anında `sonuc` yazmak. Sonuç sonradan belli olur, güncelleme geçmişi yeniden yazmayı gerektirir.
- Elenen: LLM ile transkriptten çıkarma. Maliyet ve belirsizlik; ikinci faz.

**Sonuçlar:**

Olumlu: geçmiş satırlar da sınıflanır, yeni depo bakımı yok. Olumsuz: sonuç her okumada hesaplanır; kategori eşlemesi elle bakım ister. Geri alma: iki ayar dosyası ve yeni modüller silinir, defterlere dokunulmadığı için veri etkilenmez.

**İlgili iş:** I-286
