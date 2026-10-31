# ADR-0118: Proje bilgi grafiği: konu kartları ve tipli kenarlar

**Durum:** Kabul edildi

**Tarih:** 2026-10-31

**Bağlam:**

Sistem haritası (`harita.py`) düz envanterdir; kayıtlarda ilişki ve konu kavramı yoktur. Bu yüzden bir istek geldiğinde hangi alanlara dokunulacağı haritadan anlaşılamıyor ve bağlı yüzeyler (ör. skill ekleme ile arayüz aç/kapa kaydı) kaçırılabiliyor.

**Karar:**

Harita iki yeni katmanla genişletilir. (1) Konu kartları: kabiliyet başına kısa `md` dosyası (amaç, eşanlamlılar, yüzeyler, değişmezler). (2) Tipli kenar listesi: JSONL; her kenar köken (statik, bildirilen, geçmiş, LLM), güven düzeyi, kanıt (`dosya:satır`) ve kaynak hash'i taşır.

Orkestra planlaması ve kapanışı bu haritayı baz alır: istek konuya eşlenir, plan kapsamı etki kümesinden türer, kapanışta etki yeniden doğrulanır. Kapılar P-028 gereği gölge modda açılır. Her iki katman proje durum dizininde dosya olarak tutulur (`<durum>/sistem_haritasi/bilgi_grafigi/`; durum dizini çoğu projede git dışıdır). Kenarlar `orkestra harita yenile` ile modelsiz yeniden türetilir, kartlar `harita-kur` skill'iyle yeniden üretilir; bu yüzden git'e girmeleri şart değildir.

**Seçenekler:**

- Saf vektör arama (RAG): elendi, yapıyı ve bağları kaybeder, etki kümesi deterministik çıkmaz.
- Graf veritabanı: elendi, bu ölçek için gereksiz yük; git'te okunamaz ve diff'lenemez.
- Yalnız elle yazılmış bağ listesi: elendi, eskir ve kaçırılan bağ yine insana kalır.
- Seçilen: dosya tabanlı kart ve kenar listesi, statik analiz ve LLM semantik geçişiyle üretilir.

**Sonuçlar:**

Olumlu: istek eşleme ve etki kümesi deterministik çıkar; backtest ile doğruluk ölçülebilir. Ölçüm (2026-10-31, 142 commit, alan düzeyi, olasılık eşiği 0.3): recall 0.707, precision 0.570; dosya düzeyi 0.357/0.249. Hedef 0.80/0.50 recall'da tutmadı; kapılar bu yüzden gölgede kalır, ihlale geçiş recall ≥0.80 ölçülünce ayrı kararla yapılır. Olumsuz: kurulum ve bakım maliyeti, yanlış kenar yanlış kapsam üretebilir (güven düzeyi ve backtest bunu sınırlar). Geri alma: yeni katmanlar ve kapılar ayrı dosya ve ayar olduğundan kapatılır (kapı ayarı `mod: kapali`), mevcut harita katmanları değişmez.

**İlgili iş ya da kural kimliği:** I-296; P-015, P-019, P-022, P-028
