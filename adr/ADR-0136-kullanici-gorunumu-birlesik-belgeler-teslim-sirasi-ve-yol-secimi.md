# ADR-0136: Kullanıcı görünümü, birleşik belgeler, teslim sırası; doğrulanabilir şey "doğrulanamayan" yazılmaz; yol seçimi kırılma noktasından başlar

**Durum:** Kabul edildi

**Tarih:** 2026-11-01

**Bağlam:** Kullanıcı şablon örneklerini inceledi ve şunları belirtti: plan ve todo kayıt kimlikleriyle (P1, G1, S1, R1, MD §, Dayanak, Gap, Geri alma, Dalgalar, denetim "bekliyor") okunamıyor; todo'dan ne yapılacağı anlaşılmıyor; sözleşme kullanıcıyı ilgilendirmiyor; çalışma özetinde "Özet" ve "Şef Özeti" başlığı yinelendi, "Harita" anlamsız, Dal ve Commit gereksiz; veritabanından doğrulanabilecek şey "doğrulanmayanlar"a yazılmış; planda V1'de geliştirme sürdürülürken V2'ye taşıma tartışılmamış; belgelerin teslim sırası belirsiz.

**Karar:**

- **Kullanıcı görünümü:** `plan.md` ve `todo.md` kapıların okuduğu kayıt olarak kalır. Kullanıcıya `plan_gorunum.md` ve `todo_gorunum.md` verilir; bunlar kayıttan betikle üretilir (`plan_gorunum.uret`), elle yazılmaz. Görünümde kimlik, Dayanak, Gap, Alternatifler, Üretim noktası, Önce, Dalgalar, Gap kapsama, denetim bloğu ve Geri alma yoktur; maddeler 1, 2, 3 diye numaralanır ve düz başlıkla anılır (P ön eki yok). Hazırlanma saati başlığın altında küçük yazılır.
- **Todo anlaşılırlığı:** todo satırı tam ve düz cümledir (ne yapılacak, nerede, nasıl biter); görünüm satırları plan maddesinin başlığı ve "Bitti sayılır" ölçütü altında gruplar.
- **Sözleşme iç kayıttır:** kullanıcıya bağlantı verilmez. İşin sonunda sözleşme ve rapor tek belgede ("Sözleşme ve rapor") birleşir.
- **Birleşik belgeler:** mevcut durum ve bulgu tek belge olur ("Mevcut durum ve bulgular"); sözleşme ve rapor tek belge olur. Birleşik şablonların yazımı ve kapı uyarlaması ADR'nin uygulama aşamasıdır.
- **Teslim sırası (plan ya da auto fark etmez):** belgeler üretilip tamamlandıktan sonra verilir. İşin başında: 1) Mevcut durum ve bulgular, 2) Plan, 3) Todo. İşin sonunda: 1) Çalışma özeti, 2) Sözleşme ve rapor, 3) Jira önerisi.
- **Çalışma özeti:** kullanıcıya tek başlık görünür ("Şef Özeti", "Özet" yinelenmez); "Nasıl karar verildi?" yerine "Neden bu yol?" gibi düz bir alan adı kullanılır; "Harita" adı kullanıcıya anlamlı bir ada çevrilir; Dal, Commit, Geri alma ve "İlgili dosyalar" yazılmaz.
- **Doğrulanabilir şey doğrulanamayan yazılmaz:** veritabanı, kod, komut ya da API ile bakılabilen her şey belge yazılmadan önce çalışılır. "Doğrulanamayanlar"a yalnız denenip engele takılan şey girer ve engel somut yazılır (erişim, yetki, süre). "Bakılmadı" engel sayılmaz.
- **Yol seçimi kırılma noktasından başlar:** bir işte iki yol varsa (örn. V1'i geliştirmek, V2'ye taşımak), plan önce hangi yolun geleceğe taşınacağını mevcut durumdaki kanıtla belirler (hangisi yaşıyor, hangisi emekli, taşıma maliyeti). Seçilmeyen yola yatırım yapılmaz; yapılıyorsa gerekçe "Kararlar"da yazılır. Yanlış yapıyı doğru şekilde sürdürmek best in class sayılmaz.

**Seçenekler:**

- **Kayıt dosyasını doğrudan sadeleştirmek:** elenen; P/G kimlikleri ve alanlar onlarca kapı, dalga ve todo kontrolü tarafından okunur, kaldırmak hepsinin yeniden yazılmasını gerektirir.
- **Kayıt ile görünümü iki ayrı elle yazmak:** elenen; yinelenen içerik zamanla ayrışır (K-006). Türev görünüm tek kaynaktan üretilir.
- **Kimlikleri görünümde bırakıp küçük yazmak:** elenen; kullanıcı kimlikleri hiç görmek istemiyor.

**Sonuçlar:**

- **Olumlu:** kullanıcı yalnız anlaşılır belge görür; kapılar değişmez.
- **Olumsuz:** görünüm dosyası ikinci bir çıktıdır; kayıt değişince yenilenmesi gerekir (bağlantı komutu her çağrıda yeniler).
- **Geri alma yolu:** `belge_baglantilari` içindeki görünüm yönlendirmesi kaldırılır; kayıt dosyaları zaten değişmedi.
- **Uygulama durumu:** plan ve todo görünümü, sözleşme bağlantısının kaldırılması, Geri alma alanının kalkması ve kurallar (P-050 teslim sırası, P-051 doğrulanabilir şey, P-052 yol seçimi) hazır. Birleşik şablonlar (mevcut durum + bulgu, sözleşme + rapor), çalışma özeti alan adları (tek "Şef Özeti", "Neden bu yol?", "Harita" adı) ve teslim sırasının kod zorlaması sonraki adımlardır; bu adımlar kapı değişikliği gerektirir.

**İlgili iş ya da kural kimliği:** I-305; K-003, K-005, K-006, P-018, ADR-0126.
