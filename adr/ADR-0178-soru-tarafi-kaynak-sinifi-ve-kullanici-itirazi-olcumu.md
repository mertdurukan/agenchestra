# ADR-0178: Kanıtsız ilk cevap soru tarafında önlenir: kaynak sınıfı, sınıf anahtarlı gölge kapı, kullanıcı itirazı ölçümü

**Durum:**

Kabul edildi (I-226 P7/P8, gölge dönemi başlangıcı). McD deposundaki ADR-0085'in (veriye dayalı yanıt, kanıt kapısı) P7/P8 ekidir; ADR-0085 eklenti deposunda değil, McD `adr/` klasöründedir.

**Tarih:**

11.11.2026

**Bağlam:**

- Kullanıcı aynı sorunu tekrar yaşıyor: ilk cevap kaynağa bakılmadan yazılıyor, sonra düzeltiliyor.
- Hakemli taban (ADR-0085): bilgi sorusu turlarında A oranı (bakılmadan, işaretsiz olgu iddiası) %22,4, Jeffreys üst %29,7.
- P4 yanıt-metni tetiğinin holdout kesinliği 0,29 (Wilson %14–%50). Yanıt metni A ile B'yi (bağlama dayanan iddia) ayıramıyor.
- Taban etiketindeki 10 A vakasının hepsi dört kaynaktan birine ait: yerel dosya/ayar/kayıt, geçmiş oturum, ürün belgesi, canlı bulut durumu. Bu bilgi soru metninde yanıttan önce vardır.
- Kullanıcının yaşadığı hata (itiraz) şimdiye kadar sayılmıyordu. `olay_duzeltme.py` günlükteki ham istek metnine bakıyordu; ADR-0169'dan beri ham metin yazılmadığı için girdisi yok.

**Karar:**

- **Soru sınıfı (P7.1):** `scripts/kaynak_sinif.py` kullanıcı mesajını model çağırmadan dört sınıftan birine eşler: `yerel`, `gecmis_oturum`, `urun_belgesi`, `canli_bulut`. Kalıplar, sıra ve şablon `ayarlar/kaynak_sinif.json`'dadır; proje durum dizinindeki aynı adlı dosya anahtar bazında ezer.
  - `cipa_kaliplari` somut çıpadır ve her zaman sınıflar: dosya yolu/uzantısı, ters tırnaklı ad, ADR/iş/kural kimliği, `ayarlar/` gibi klasör, "bu projede", "bizde", "orkestra".
  - `kaliplar` genel sözcüktür. Sınıfta `kavram_haric` açıksa kavram sorusunda ("nedir", "ne demek", "nasıl çalışır", "farkı ne") sınıflamaz.
  - `yerel` yalnız çıpayla eşleşir; çıpasız genel sözcük ("kural", "ayar", "dosya") yerel saymaz.
  - Düzenli ifade süresi sınırlıdır: giriş `giris_max_karakter` (2000) karakterine kesilir, tekrarlar `{1,200}` gibi üst sınır taşır. 100 000 karakterlik boşluksuz girdide her çağrı 0,5 sn altındadır (test).
- **İlk araç satırı (P7.2):** sınıf eşleşirse UserPromptSubmit bağlamına P1 KAYNAK satırının yerine tek satır gider: sınıfın ilk aracı ve "araç sonucundan önce olgu cümlesi yazma; bakamazsan 'doğrulanmadı'". En çok 200 karakter. Eşleşmezse P1 satırı aynen kalır; çift satır yoktur.
- **Sınıf anahtarlı kapı (P7.3):** Stop'ta bilgi sorusu turu sınıfa eşleşti ve turda kanıt aracı yoksa günlüğe `kural_ihlal / kanitsiz_iddia_sinif` (sınıf alanıyla) yazılır. Kip yalnız `golge`: block ve kullanıcı uyarısı yoktur, ayarda `block` yazılsa da gölge sayılır. Önceki tur kanıtlıysa ya da yanıt kaynak işareti taşıyorsa susar. `ORKESTRA_KANIT_KAPISI=0` kapatır; hata sessiz geçer. P4 yanıt-metni kapısı değişmeden ayrı kuralıyla sürer.
- **Kullanıcı itirazı (P8):** UserPromptSubmit'te mesaj önceki asistan yanıtına itirazsa ve o turda kanıt aracı yoksa günlüğe `ilk_cevap_itiraz` (kalıp kimliği, önceki sorunun sınıfı) yazılır; ham mesaj yazılmaz.
  - Tanım: itiraz = kullanıcı önceki yanıta olgu hatası atfı; garanti değil (kalıp eşleşmesidir).
  - Atıf kalıbı önceki yanıta göndermeyi hata işaretiyle birlikte ister ("ilk cevabın … yanlış", "dediğin … doğru değil", "emin misin", "yanılıyorsun").
  - "Hayır, …" başlangıcı tek başına yetmez; mesajda hata işareti de gerekir ("o değil", "olamaz", "nasıl söylersin").
  - Sayılmayanlar: kısa komut, övgü ("doğruydu", "haklısın"), komut ("dosyaya yaz"), "özetle/kısalt", "yanlış pozitif" ve soruyla biten yanıta verilen "hayır".
- **Ölçüm:** `orkestra kanit olc` sınıf kapsamını (`sinif_eslesen`, `sinif_kanitsiz`, sınıf dağılımı) ve itiraz sayısı/oranını (itiraz / soru turu) ek satırlarla yazar; eski satırlar değişmez. `--itiraz-ornek` elle doğrulama örneği çıkarır.

**Seçenekler:**

- Elenen: yanıt-metni tetiğini sıkılaştırmak. Holdout kesinliği 0,29; metin A ile B'yi ayırmıyor.
- Elenen: sorudaki terimi otomatik grep edip sonucu bağlama koymak. A vakalarının yarısı yerelde yok; satır yalnız hangi araçla bakılacağını söyler.
- Elenen: yalnız tur sonu uyarısı. Yanıt kullanıcıya ulaştıktan sonra çalışır, kaynakta önlemez.
- Elenen: itiraz ölçümünü LLM etiketleyiciyle yapmak. Etiketleyici A uyumu 0,62; yavaş ve pahalı.

**Sonuçlar:**

- Kapsam ölçümü (11.11.2026 13:50, McD dökümleri, son 14 gün, 673 dosya), çıpa daraltmasından sonra:
  - 668 bilgi sorusu turunun 98'i sınıfa eşleşti; 46'sında turda kanıt aracı yoktu.
  - Dağılım: canlı bulut 32, geçmiş oturum 33, yerel 28, ürün belgesi 5.
  - Kapsam düştü: ilk sürümde (13:24) 139 eşleşen / 70 kanıtsız, yerel 60 idi. Düşüşün tamamı yerel ve canlı bulut kavram sorularından geliyor; bu bilinçli bir değiş tokuştur (yanlış yönlendirme yerine kapsam kaybı).
  - Taban etiketindeki 10 A vakasının 8'i hâlâ sınıfa eşleşip kanıtsız yakalanıyor (önceki sürümde de 8). Kaçan ikisi: biri sınıfa eşleşmiyor, birinde önceki tur kanıtlı. Kalıplar bu vakalar görülerek yazıldığı için bu örneklem içi kapsamdır, genelleme değildir.
- Yanlış yönlendirme: çıpasız 21 genel soru (kavram, nasıl yapılır, genel bilgi) testte 0/21 sınıfa eşleşiyor (Wilson üst %15,5); 13 gerçek yerel sorunun 13'ü `yerel` sınıflanıyor. Soru listesi kalıplar yazılırken görüldü; örneklem içidir.
- Kesinlik ölçülmedi, P6. Sınıf kapısının A kesinliği ve gerçek yanlış yönlendirme oranı P6'daki yeni etiketlemeyle ölçülür.
- İtiraz ölçümü (11.11.2026 13:51, elle okundu), olgu hatası işaretiyle daraltmadan sonra:
  - 30 gün: 6 olay, 4'ü olgu hatası atfı (Wilson %30–%90). Diğer ikisi soru yanlış anlaşıldı ya da konu değiştirildi ("hayır, … soruyorum", "hayır o değil, …"); olgu hatası atfı sayılmadı.
  - 14 gün: 4 olay, 3'ü olgu hatası atfı (Wilson %30–%95); itiraz oranı 4/668.
  - İlk sürümde 30 günde 8 olay / 7 gerçek, 14 günde 5 / 5 sayılmıştı; o sayımda "gerçek itiraz" daha geniş okunmuştu (yeniden yönlendirme dahil). Sayı yeni tanımla değişti.
  - 30 olay hedefi veri yetmediği için karşılanmadı.
- **Block'a geçiş koşulu:** sınıf kapısının P6 etiketinde ölçülmüş A kesinliğinin Wilson alt sınırı ≥%75 olmalı. Geçiş ayrı kararla ve yeni ADR'yle yapılır (P-028). Kullanıcı uyarısı için de aynı koşul geçerlidir.
- Olumsuz:
  - Sınıf satırı bağlamı büyütmez: P1 satırının yerini alır.
  - Çıpa şartı kapsamı düşürür: "kural nerede?" gibi çıpasız yerel sorular sınıflanmaz ve P1 satırı kalır.
  - `canli_bulut` genel sözcüklerle eşleşir (kavram sorusu hariç); gerçek yanlış yönlendirme oranı P6 etiketiyle ölçülür.
- Geri alma: `kaynak_sinif.json` içinde `sinif_kapisi.mod: kapali` ve `itiraz.acik: false`; ilk araç satırı için `sira: []`. Kalıcı geri alma commit revert'üdür.

**İlgili:** ADR-0085 (McD), ADR-0169, I-226, P-021, P-022, P-028, P-032.
