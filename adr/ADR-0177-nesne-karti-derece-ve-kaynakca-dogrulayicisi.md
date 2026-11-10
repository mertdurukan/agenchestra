# ADR-0177: Nesne kartı derece ve kaynakça doğrulayıcısı ayrı modül olur, sohbet yanıtında gölge kapıyla ölçülür

**Durum:**

Kabul edildi (I-430, gölge dönemi başlangıcı).

**Tarih:**

10.11.2026

**Bağlam:**

- Tablo, kolon ve prosedür gibi nesneleri anlatan çıktıda iddialar kesinlik derecesi ve kaynak kimliği taşımıyordu.
- Aynı sohbette kaynaksız bir iddia üç kez düzeltildi (fact_transfer_actual_analysis ve is_applied konuları).
- İddia-kaynak kapısı (ADR-0169) gölge moddadır ve yalnız kaynak türü etiketi arar (scripts/iddia_kaynak.py).
- Kapı dereceyi, kaynak sırasını ve kaynakçanın yeniden çalıştırılabilirliğini denetlemez.
- Nesne anlatımı iki yoldan çıkar: sohbet yanıtı (Stop hook'ları görür) ve belge çıktısı (hiçbir hook görmez).

**Karar:**

- `scripts/nesne_karti.py` doğrulayıcısı eklenir, model çağırmaz. Dereceler KESİN, GÜÇLÜ, DOĞRULANMADI; kaynak türleri ve birincil/ikincil sırası `ayarlar/nesne_karti.json`'dadır, projeler ezebilir (P-022).
- KESİN iddia yalnız birincil kaynağa (veritabanı kataloğu, prosedür gövdesi, kod, ölçüm çıktısı) dayanabilir.
- Kaynakça girdisi komut ya da yol, ortam ve ölçüm saati taşır, sır değeri taşımaz.
- Belge çıktısı için `orkestra nesne-karti dogrula KART [--dokum DOSYA] [--json]` komutu eklenir. `--dokum` ile KESİN kaynağın komutu ya da yolu dökümde tam eşleşmeyle aranır.
- Sohbet yanıtı için `scripts/nesne_karti_golge.py` gölge Stop kapısı eklenir: kartı doğrular, kartsız ve en az üç şema.tablo(.kolon) tanımlayıcılı yanıtı `kapi_golge` olarak günlüğe yazar. Hiçbir kipte engellemez ve mesaj vermez.
- scripts/hook.py'ye yalnız `_nesne_karti_yanit` işlevi ve tek çağrı satırı eklenir. iddia_kaynak.py ve kanitsiz_iddia.py değişmez.
- `ihlal` (engelleyen) kipe geçiş bu ADR'nin kapsamı dışındadır, gölge günlüğü ölçümünden sonra ayrı ADR ile karara bağlanır (P-028).

**Seçenekler:**

- Seçilen: ayrı modül, belgede CLI komutu, sohbet yanıtında ayrı gölge kapı.
- Elenen: iddia_kaynak.py'ye derece kuralı eklemek. Kapının kendi gölge kaydına (sayi_kaynaksiz, etiketsiz_iddia) yeni bulgu türü karışır, o ölçüm okunamaz.
- Elenen: yalnız CLI ve skill. Sohbet yanıtındaki üretim anını ölçmez, kullanıcının yaşadığı yol bu.
- Elenen: kartı model ile denetletmek. Aynı girdiye farklı karar çıkar, token harcanır, kural deterministik yazılabiliyor.
- Elenen: belge yazımına PostToolUse/Write hook'u. Hangi dosyanın nesne kartı olduğunu yol adı sezgisine bağlar ve her Write'ta çalışır.
- Elenen: kapıyı doğrudan `ihlal` kipinde açmak. Yanlış pozitif oranı bilinmeden yanıt engellenir.

**Sonuçlar:**

- Nesne kartları kodla denetlenir: derecesiz, kaynakçasız ya da ikincil kaynaklı KESİN iddia çıkış kodu 1 ile yakalanır.
- Doğrulayıcı biçimi ve kaynak hiyerarşisini denetler, iddianın doğruluğunu denetlemez. Doğruluk için kart ayrı denetçiyle kaynağıyla eşlenir (skills/nesne-karti).
- Sohbet yanıtlarında derece zorunluluğu bu kararın dışındadır, yalnız ölçülür (P-001 ile çakışma ölçülmedi).
- Gölge günlüğü (kapi_golge / nesne_karti_bulgu, kartsiz_nesne_anlatimi) biriktikçe yanlış pozitif oranı okunur.

**İlgili:**

- ADR-0169 (iddia-kaynak kapısı), P-028 (gölge önce), P-022 (genel davranış eklentide), P-058 (kanıt kapısı), skills/iddia-dogrula, skills/nesne-karti.
