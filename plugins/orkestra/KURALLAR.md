# Orkestra kuralları

Her projede geçerlidir. Projeye özgü bilgi bu dosyaya girmez; o kısım projenin kendi CLAUDE.md dosyasında durur.

## Ana ajan
- Orkestrada planla, dağıt, topla. Kartlı işte işçi işini kendin yapma; kart açıp açmayacağına aşağıdaki "Ana ajan mı, orkestra mı?" kuralıyla karar ver.
- Onay yazma. Onayı yalnız ayrı denetçi verir.
- Kart gerektiren işi `/orkestra:is` ile yürüt.
- Tekrar eden işte önce var olan skill'lere bak.
- Bilgi sorusu: hook notu "BİLGİ SORUSU" gelirse en çok 5 cümleyle cevapla. İş durumu, tablo ya da kaynak taraması ekleme; ayrıntıyı ancak istenirse ver. Ayar: `ayarlar/soru_sinif.json`; proje ezmesi `.claude/orkestra/soru_sinif.json`.
- Ana ajan mı, orkestra mı? Kart döngüsünün bir bedeli var: işçi, ön kontrol ve denetçi her seferinde bağlamı sıfırdan kurar; bağlam aktarılırken bilgi kaybolur. Bu bedeli yalnız paralellik, bağlam ayrımı ya da bağımsız denetim kazandırıyorsa öde.
  - Doğrudan (kart açma):
    - soru-cevap, açıklama, durum özeti yap;
    - ana ajanın zaten okuduğu bağlamda tek dosyalık, tek adımlık küçük düzenlemeyi kendin yap (koddaysa ilgili testi koş);
    - kod dışı, en çok 2 dosyalık işi (belge, README, ayar, todo) kendin yap; kanonik belge ve dış teslim hariç;
    - hazır betiği ya da skill'i bir kez çalıştır, sonucu aktar;
    - orkestra bakımını (todo, niyet, kart durumu) kendin yap.
  - Orkestra (`/orkestra:is`) kullan:
    - üç ya da daha fazla dosya veya bağımsız parça varsa (paralel kazanç);
    - birden çok dosyaya dokunan kod değişikliğinde;
    - hatası pahalı çıktıda: dış teslim, nihai ya da kanonik belge, DB ölçüm sonucu, iddia kararı, Jira story (bağımsız denetim için);
    - geniş tarama ya da çok dosya okumada (ana ajanın bağlamı şişmesin diye araştırmacıya ver).
  - Ölçülebilir eşik: bir istekte iş belgesi (plan, todo, mevcut durum, sözleşme, çalışma özeti, ADR) dışında üçüncü ayrı dosyaya yazmak üzereysen ve alt ajan çalıştırmadıysan, PreToolUse hatırlatır (ORK-ADR-0099, `ayarlar/devir_hatirlatma.json`); hatırlatma engellemez, kararı sen verirsin.
  - Kuşkuda: ana ajanın bağlamı büyükse (≳150k) işi kısa bir kartla ucuz basamağa ver. Bağlam küçükse ve iş tek adımlıysa doğrudan yap.
  - Doğrudan yapılan işte denetçi yoktur. "Onaylandı" deme; neyi nasıl doğruladığını (test, yeniden okuma) söyle.

## Maliyet basamakları
- T0: hazır betik; T1-T4 basamak→model/effort tablosu tek yerde: ayarlar/model_politikasi.json (`orkestra politika goster`). Planlama T3 basamağında yapılır.
- Bir işe izin veren en düşük basamakla başla.
- Önce T0 (betik ya da deterministik kural), model yalnız kalan belirsizlikte. Sınıf adı görev türü kataloğundan (`ayarlar/gorev_turleri.json`) seçilir; basamak verilmezse katalog varsayılanı uygulanır. Katalog dışı sınıf, katalogdan yüksek basamak ve gerekçesiz T3/T4 golge uyarır (`ORKESTRA_GOREV_TURU_KAPISI=0` kapatır).
- **Opus kapıları (ORK-ADR-0092):** T3/T4 yalnız dört kapıdan girer, kartta `--basamak-neden` ile yazılır.
  - K1: belirsiz ya da çok modüllü plan.
  - K2: iki ret sonrası yükseltme.
  - K3: geri alınamaz ya da dışa dönük karar.
  - K4: plan best-in-class denetimi.
- Yükseltmeyi denetçi reddi tetikler.
- Kart başına ajan tavanı vardır (varsayılan 8; workflow `args.kart_ajan_tavani`). Tavan dolan kart `tavan` sonucuyla durur; ana ajan nedeni okuyup kartı `beklemede` yapar, yeniden koşturmaz.
- Kart kilidi: teslim/onaylı/iptal kart ve başka ajanda işlenen kart yeniden işlenmez (`kart durum isleniyor` çıkış 6). Aynı kartı iki koşuya verme.

## Denetim
- Her işçi çıktısını ayrı bir denetçi (`orkestra:denetci`) incelesin. Kimse kendi işini onaylamaz.
- Denetçi işçiyle aynı modelde koşsun (T2 işi, Sonnet denetçi); T3/T4 işçide denetçi en çok Sonnet'tir (`model_politikasi.json` `denetci` bloğu).
- Opus denetçi yalnız toplam ret ≥ 2 ya da kartta `denetim_opus: true` iken kullan; sonuç `denetim_politika.py tablo --kesim` ile izlenir.
- Test ve T0 ön kontrol (`on_kontrol.py`: yeni test hatası, CRLF/BOM, kapsam dışı yazma, eksik token) ajan değildir: işçinin `kart durum is-bitti` çağrısında CLI koşar. Geçmezse is-bitti kaydedilmez ve işçi aynı oturumda düzeltir; denetçi çağrılmaz.
- Denetçi testi yeniden koşmaz; CLI kaydına ve diff'e bakar.
- Denetçi yalnız mekanik farkı (biçim, sayı) `Edit` ile düzeltir (`Write` kapalı); içerik eksiği işçiye döner (ORK-ADR-0083). Düzeltme `kart denetim --karar onay --duzeltmeler-dosya <json>` ile bildirilir (`dosya`, `tur`, `once`, `sonra`, `kanit_komutu`); A9 kapısı is-bitti'den beri değişen her dosyanın bir satırla anıldığını, `sonra`nın dosyada olduğunu ve `kanit_komutu`nun yeniden koşunca geçtiğini sınar. Düzeltme ret defterine `duzeltildi:<neden>` olarak da düşer.
- Kayıtlı ön kontroller (`ayarlar/on_kontrol.json`, proje ezmesi `.claude/orkestra/on_kontrol.json`): `kanit-satiri` (`K<n>:` kanıt satırı) ve `sayi-tutarli` kontrolü yalnız bağlı etkin bir kural varsa koşar (`kural bagla K-xxx --kontrol <kimlik>`; kural kaldırılınca kapanır). `kanit-satiri` `ihlal` modundadır (is-bitti'yi reddeder), `sayi-tutarli` `golge` (uyarı + kayıt) kalır; ihlal geçişi kullanıcı kararıdır (ORK-ADR-0082). İşçi her kriter için `--kanit "K<n>: ..."` verir.
- Denetim politikası (`ayarlar/denetim_politikasi.json`, varsayılan `mod: golge`): grup (sınıf×basamak) ilk-ret oranı, tdd/yüksek risk hariç tutma ve deterministik örnekleme ile denetçiyi atlayabilir; `golge` yalnız kaydeder, `etkin` ancak geçit (`denetim_politika.py gecit`) açıkken ve CLI'de otomatik onay yazar. Açma kullanıcı kararıdır.
- Kart başına testler `test_alani` dosyalarıyla sınırlıdır (geniş komut otomatik daralır); tam paket koşulmaz.
- Test-önce (test yazarı + kırmızı kapı) yalnız riskli kod kartında (`tdd: true`): davranış değişikliği olan çok dosyalı ya da kanonik mantık. Diğer kod kartında işçi kodu ve testi birlikte yazar.
- Yeniden denetim yalnız önceki retteki karşılanmayan kriterlere ve gerilemeye baksın.

## Dağıtım
- Bağımsız işleri paralel koştur; plan maddesi `Önce`/`Yazma alanı` taşır, dalgalar `orkestra is dalga` ile çıkar, dalga işçileri tek mesajda dağıtılır (P-035).
- Paralel işlerin yazma alanları kesişmesin.
- Test ve test benzeri süreçler (pytest, lint, derleme, doğrulama) varsayılan paralel koşar, ayrıca istenmez (P-041): test komutunu `scripts/test_paralel.py <yol>` ile yaz; kart ve ön kontrol çıplak `pytest <yol>` komutunu kendisi çevirir. Işçi sayısı CPU, bellek ve CI sınırından otomatik türer; `ORKESTRA_PARALEL_N=1` seri, `ORKESTRA_PARALEL=0` dönüşümü kapatır. Bağımsız test dışı süreçler: `orkestra paralel -- "komut1" "komut2"`.
  - Yazma alanı kesişen (aynı dosyayı değiştiren) işlere zincir kurma; tek kartta birleştir, kriterler ayrı satır olsun.
  - Birleşik kart 8 kriterden fazlaysa en çok 2 kartlık zincire böl.
  - Mantıksal bağımlılık (çıktısını okuma) ile dosya çakışmasını ayrı değerlendir; yalnız çıktısını bekleyen iş bağımlılık olur.
- Kart dağıtımını varsayılan olarak `Workflow` aracıyla `orkestra:calistir` üzerinden yap.
- Workflow kullanılamazsa kartları elle dağıt.
- Workflow izni yalnız orkestra kartı dağıtımı içindir; başka iş türlerine genişlemez.

## Defterler
- Ortak defter `.claude/orkestra/ortak_defter.md`: herkes ne yaptığını yazar (hook otomatik düşer).
- Defteri elle düzenleme. Tamamını okuma; ihtiyacın olanı `orkestra defter baglam <id>` ile oku.
- Token ve maliyet defteri `.claude/orkestra/maliyet.jsonl` (ajan x süreç x model). Rapor için `/orkestra:maliyet`.
- Paralel oturumlar ortak dosyaya yazmadan önce dosyayı yeniden okusun ve yalnız sona eklesin.

## Kural katmanları
- Kullanıcının `orkestra kural` ya da panel ile girdiği kurallar iki katmandan birinde durur; kayıtta `katman` alanı vardır.
  - **plugin**: orkestra eklentisine ait, projeden bağımsız, eklentiyi kullanan her projede geçerli kurallar (ör. konu değişiminde yeni oturum, okunabilirlik düzeni, kök neden, belge bağlantısı). Eklenti deposunda `kurallar/eklenti_kurallari.json` içinde tutulur; bu dosyanın sonundaki "Kayıtlı eklenti kuralları" bölümü ondan üretilir.
  - **proje**: yalnız o projeye özgü kurallar (proje süreci, müşteri, ölçüt, iş akışı). `<proje>/.claude/orkestra/kurallar/kurallar.json` içinde tutulur.
- Katmanı seç: kural başka bir projede de doğru kalıyorsa ve içinde proje adı, süreç ya da müşteri bilgisi yoksa plugin; aksi halde proje.
  - `orkestra kural ekle --metin M [--neden N] [--katman proje|plugin]` (varsayılan proje); sonradan `orkestra kural tasi <id> --katman plugin|proje`.
  - Öneri (`kural oner`) her zaman proje katmanında açılır; onaylandıktan sonra gerekirse taşınır.
- Projeye gelen kural dosyası: `.claude/rules/orkestra_kurallari.md` iki katmanın etkin kurallarından üretilir; oturum açılışında eklenti katmanı değişmişse yenilenir. Elle düzenlenmez.
- Öncelik: çakışmada proje kuralı eklenti kuralından önce gelir. Bir eklenti kuralı bu projede geçerli olmasın diye `orkestra kural kapat <id> --not N` (yalnız o proje; eklenti deposu değişmez), geri almak için `kural ac <id>`.
- Kimlikler: proje kuralı `K-nnn`, eklentide yeni kural `P-nnn`. Eklentiye taşınan eski `K-nnn` kimlikleri `--kimligi-koru` ile korunur (belgeler ve kod o kimliğe atıf yapar); proje için sonraki `K` numarası iki katmandaki en büyükten türer.
- Eklenti kuralına projeye özgü bilgi (Jira kodu, müşteri, kart kimliği) girmez; böyle bir kural proje katmanında kalır.
- Perspektif önerisinin gövdesinde `Yayın: kapsam=<proje|evrensel>; hedef=<kural|skill|yok>` etiketi bulunur; altında `Eklenti metni:` ve `Neden:` satırları gelir. Etiket yoksa kapsam proje, hedef yok sayılır.
- Eklenti katmanına terfi, onaydan önce terfi kapısından (`onay.terfi_denetle`) geçer: sır, kart kimliği, Windows yolu, e-posta, Jira kodu ve `terfi_yasak.json` terimleri isabet sayılır; isabet varsa kural yazılmaz.
- Terfi yalnız kuralı eklenti deposundaki `kurallar/eklenti_kurallari.json` dosyasına yazar; yayın (commit, `orkestra guncelle`, push) değildir ve ayrıca, açık istekle yapılır.

## Kapsam ve ayarlar
- Ayarlar bilgisayara değil çalışma alanına özgüdür: yeni ayarı genel dosyaya değil `<proje>/.claude/settings.json` içine yaz.
- Eklentileri proje kapsamında (`--scope project`) kur. Genel ayar dosyasını boş tut.
- Orkestrasyon projeden bağımsızdır. Eklenti koduna ve belgelerine projeye özgü bilgi girmez.
- Bir projeye orkestra kurulacaksa yalnız `araclar/projeye_kur.py <proje>` çalıştır; projenin alan işine geçme.
- Orkestra işi istendiğinde görev yalnız çok ajanlı orkestrasyonu kurmaktır; kapsam dışına çıkma.
- Git worktree'sinde (Claude'un oturum başına açtığı ağaç dahil) orkestra durumu ana klasörden çözülür; eski durum kopyaları `orkestra durum devral` ile ana duruma eklenir (ORK-ADR-0033, GELISTIRME.md).
- Otomatik commit (her Edit/Write sonrası yalnız o dosya, `scripts/oto_commit.py`) varsayılan kapalıdır. Projede açmak için `.claude/settings.json` `env` bloğuna `"ORKESTRA_OTO_COMMIT": "1"` yaz; atıf satırı `ORKESTRA_OTO_COMMIT_ATIF` ile değişir. Açıkken hook'u atlama, `--no-verify` kullanma.

## Yöntem seçimi
- Birden çok yol varsa en az token harcayan, en verimli yolu öner ve seç.
- Seçenekleri maliyetine göre sırala; en ucuzunu önerilen olarak işaretle.
- Tercih sırası:
  1. Kullanıcının bir kez yaptığı dışa aktarım (CSV) + yerel betik (T0) + yalnız özeti okuma.
  2. API ya da MCP çağrısı; sonucu bağlama almadan önce betikle süz ve topla.
  3. Tarayıcıda sayfa içi JS ile toplanmış sonuç.
  4. Sayfa metni ya da ekran görüntüsü okuma (son çare).
- En ucuz kanıt: soruyu cevaplayan en dar ölçümle başla (ör. "kolon var mı" varlık kontrolü, sayımdan ve tam taramadan önce). Genişletmeyi yalnız kullanıcıya sorarak yap.
- Toplu sınıflamada kuralları ana ajan yazsın, satırları Haiku işlesin.
- Tespit ve düzeltmeyi önce deterministik Python kurallarıyla kur (kod, regex, sayaç, oturum bağlantısı).
- LLM'i yalnız kuralla ayrılamayan belirsiz durumlarda kullan.
- Kullanıcıya giden LLM yanıtının kısıtları kodla doğrulanır, prompt yalnız ek katmandır (P-032); planlarda `**LLM çıktısı:**` beyanı zorunludur.
- Kuralları mevcut LLM etiketleriyle karşılaştırarak doğrula.

## Odak ve sıradaki adımlar
- Her sohbet ilk işte bir işe bağlanır: mevcut işse `orkestra is devam <id>`, yeni işse `orkestra is ac <başlık> [--klasor <görev klasörü>]` (`--klasor` isteğe bağlı: verilmezse oturum kökü altında sıradaki NNN klasörü türetilir; kök dışı yol kök altına çevrilir). Sıradaki adımlar sohbet hafızasında değil işin todo.md'sinde tutulur: ortaya çıkınca `orkestra is todo <id> --ekle "…"`, bitince `orkestra is todo <id> --bitti <n|parça> [--not]`; yeni sohbet listeyi oradan okuyup devam eder. Not: is todo birden çok --bitti/--ekle alabilir; art arda todo yazmalarını tek çağrıda birleştir.
- Yanıt sonunda "sıradaki adım" yazma.
- Sıradaki adımları `orkestra is todo <id> --ekle` ile işin `todo.md` dosyasına yaz.
- Yalnız kullanıcıdan karar ya da onay gerekiyorsa bunu tek cümleyle söyle.

## Kod işi: önce mevcut durum
- Kod kartı (sinif=kod) açmadan önce ana ajan işin dokunacağı mevcut kodu tanır (kendisi ya da `orkestra:arastirmaci`): ne var, ne yapıyor, nerede bağlanır. İlgili dosya yolları kartın `girdi`sine yazılır; kriterler "mevcut X değişsin / eklensin"i yansıtır, var olan yok sayılıp yeniden yazdırılmaz.
- İşçi kod yazmadan önce mevcut durum notunu kaydeder: `orkestra kart mevcut <id> --dosya <json>` (okunan[dosya, satir, alinti, rol], yetenekler, karar degistir|ekle|yeni, neden, etkilenenler). Kanıt deterministiktir: dosya var, satır dosya içinde, alıntı o satırın ±2 satırında geçer; karar degistir/ekle ise okunan dosyalardan biri yazma alanındadır.
- Zorlama: PreToolUse hook'u not kaydedilene kadar işçinin yazma alanına yazmasını reddeder (test yazarı muaf); not yoksa is-bitti çıkış 4 verir (kapatma: `ORKESTRA_MEVCUT_KAPISI=0`). Denetçi notun diff'le tutarlılığına bakar (mevcut yapı yok sayılmışsa ret).

## Plan ve todo sırası
- Kural P-005 (kayıtlı eklenti kuralları): `mevcut_durum_<YYYYMMDD>.md` → `plan.md` → `todo.md`; her adım bir öncekinden beslenir. Motor sırayı kendisi yönetir (`ORKESTRA_SIRA_KAPISI=0` kapatır; testlerde varsayılan kapalıdır).
- `orkestra is ac` sıralı iş açar (is.json `sira`): yalnız mevcut durum iskeleti (`sablonlar/mevcut_durum.md`: Amaç, Ölçüm saati, Yöntem, Sınır, §1 istek/veri yolu, §2 bugünkü davranış ve korumalar, §3 etki haritası, §4 git durumu, §5 bilinmeyenler) ve `oturumlar.md` yazılır.
- Tamam tanımı deterministiktir (`scripts/is_sirasi.py`): mevcut durumda 5 bölümün her biri dolu, `**Ölçüm saati:**` dolu, §3'te madde var; planda ilk 20 satırda mevcut duruma bağlantı, en az bir `### P<n>` maddesi ve her maddede geçerli `MD §<k>`; todo satırı `P<n>:` ile başlar ve P<n> planda vardır.
- Zorlama (kaynaktan sona): `is ac` şablonu → `is belge <id> plan` ve `is todo --ekle` ön koşulu (çıkış 2) → PreToolUse yazım anı kapısı (Write/Edit ile doğrudan `plan.md`/`todo.md`; yalnız sıralı işte). `orkestra is sira <id>` adımı ve eksikleri gösterir; `--ac` eski işi sıralıya çevirir. Bayraksız eski işler değişmez.
- `orkestra is baglanti <id>` çıktısının ilk satırı `mevcut durum: …`dır (K-003 teslim satırları).
- Kod kartındaki mevcut durum notu (`orkestra kart mevcut`) bunun kart düzeyindeki karşılığıdır, yerine geçmez.

## Plan doğrulama (✅/❌)
- Plan, iddiaları tek tek yazar: `- **C<n>** cümle` ve altında kanıt satırı (`Kanıt: dosya|ara|say|komut|deneme|kaynak …`). Sözdizimi `sablonlar/plan_dogrulamali.md` başındaki yorumdadır. ✅ ve ❌ işaretini `orkestra plan dogrula I-nnn|PLAN.md [--yaz]` kanıttan üretir; plan yazarı elle koymaz.
- Kanıt türleri: `dosya` (yol:satır "alıntı", ±2 satır), `ara` (düzenli ifade, dosyalar => sayı), `say` (glob => sayı), `komut` (proje kökünde bash, beklenen çıktı; yasak kalıp listesi), `deneme` (kayıtlı dosya "alıntı"), `kaynak` (URL; tek başına ✅ vermez).
- Her ❌ için `Spike:` (kanıtı kapatacak deneme), `Alternatif:` ve `Risk:` satırı yazılır. Plan maddesi `**İddialar:** C1, C2` ile bağlıdır; ❌ iddiaya bağlı madde todo'ya girmez, `**Kapatır:** C<n>` ile o iddiayı kapatan deneme maddesi girebilir.
- Karar bloğu `<!-- plan-dogrulama:basla -->` ile `<!-- plan-dogrulama:bitis -->` arasındadır: UYGULANABİLİR, KOŞULLU, UYGULANAMAZ ya da TAMAMLANMAMIŞ (yüzde ya da ağırlık yoktur). Plan özeti değişince blok bayat sayılır ve komut yeniden koşulur.
- Zorlama: `is todo --ekle` ve hook yazım anı kapısı aynı işlevleri çağırır (`plan_dogrulama.todo_onkosulu`, `todo_satir_engelleri`). Mod `ayarlar/plan_dogrulama.json` (ya da projede `.claude/orkestra/plan_dogrulama.json`): `golge` uyarır ve `gunluk.jsonl`a yazar, `ihlal` reddeder. Kapatma: `ORKESTRA_DOGRULAMA_KAPISI=0`; komut kanıtını kapatma: `ORKESTRA_PLAN_KOMUT=0`. `is ac` iddia sözdizimli planı varsayılan açar, `--dogrulamasiz` ile açmaz.
- Sınır: kapı kanıtın var olduğunu ve beklenen değeri verdiğini sınar; kanıtın cümleyi anlamca desteklediğini sınamaz. Bu karar bloğunda "Sınır" olarak yazılır ve okuyana kalır.
- Kanıt derinliği (ADR-0181): `yuklem` kanıt (tam sayılı `ara`/`say` `=> N`, `komut`) iddiayı sınar; `varlik` kanıt (`dosya`, `deneme`, `>=N`) yalnız alıntının bulunduğunu sınar. CLI ve karar bloğu iki sayı yazar ("N ✅: a yüklemle sınandı, b yalnız alıntı") ve yorumu sınanmayan ✅'ları adıyla listeler. "8/8 kanıtlı" tek sayısı yazılmaz.
- Kapsam iddiası: cümle `ayarlar/plan_dogrulama.json` `kapsam_kaliplari` sözcüğünü (yalnız, hiç, tümü, asla, only, never…) taşıyorsa yüklem kanıtı ister; yalnız alıntıyla ❌ olur. Tanım içinde aramak için `ara "<re>" yol.py::Sinif.ad => N` (AST aralığı, dekoratör dahil) yazılır.
- Kanıt izi: karar bloğu her iddia için kanıtın okuduğu içeriğin özetini (`**Kanıt izi:**`) taşır. Kaynak değişince blok bayat sayılır ve todo kapısı "kanıt değişti (C<n>)" der; plan yeniden doğrulanmadan madde todo'ya girmez. `komut` kanıtı ize girmez.
- Sohbette kapsam: Read `offset`/`limit` ile kısmi okuyunca PreToolUse oturum ve dosya başına bir kez not verir. Stop'ta kısmi okuma + aramasız turda kapsam sözcüklü kod adı cümlesi `kural_ihlal/kapsam_iddia` gölge kaydı olur (`ayarlar/kapsam_iddia.json`; block yok, ihlale geçiş kesinlik ≥%75 ve ayrı ADR ister). Kapatma: `ORKESTRA_KAPSAM_KAPISI=0`.

## Kapılar: sözleşme, teslim, izole ortam (ORK-ADR-0035)
- Üç yeni kapı önce `golge` modunda koşar: eksik stderr'e uyarı olarak yazılır ve `gunluk.jsonl`a `kapi_golge` olayı düşer, iş engellenmez. Mod `ayarlar/<kapı>.json` (`mod: golge|ihlal`); projede `.claude/orkestra/<kapı>.json` ezer. `orkestra is rapor` kapı başına gölge uyarı sayısını gösterir; ölçüm yeterince temizse mod `ihlal` yapılır.
- **Görev sözleşmesi** (`ayarlar/sozlesme.json`, `ORKESTRA_SOZLESME_KAPISI=0` kapatır): `is ac` mevcut durumdan önce `sozlesme_<YYYYMMDD>.md` açar (Özet, Problem, Başarı kriterleri `- **S<n>:**`, Kapsam dışı, Kısıtlar). Plan maddesi `**Sözleşme:** S<n>` ile bir kritere bağlanır, her kriter bir maddeye bağlıdır; çalışma özeti `Plana göre gerçekleşen` bölümünde her S<n>'i anar (bu özet denetimi kalite bayraklı işte çalışır; `ORKESTRA_KALITE_KAPISI=0` onu da kapatır). İhlal modunda sözleşme tamam olmadan plan ve todo yazılamaz.
- **Teslim kapısı** (`ayarlar/teslim.json`, `ORKESTRA_TESLIM_KAPISI=0` kapatır): `is kapat`, işin git ağacında `origin` varsa ve iş açıldığından beri kod dosyası değiştiyse PR, CI sonucu (`gh pr view`) ve inceleme kaydını arar. İnceleme kanıtı GitHub onayı ya da `orkestra is teslim <iş> --pr <bağlantı> --inceleme "<kim/ne>"`dir (`is kapat --pr --inceleme` aynı kaydı yapar). Uzak deposuz proje ve yalnız belge işi muaftır. `--ozetsiz` kapanışı teslim kapısını da atlar (hiç iş yapılmayan iş için). Panelden kapatma aynı kapıyı kullanır; ihlal modunda PR kaydı önce `is teslim` ile yapılır. `gh` kurulu değilse ya da PR bulunamazsa eksik "doğrulanamadı" diye yazılır, `--pr`/`--inceleme` kaydı çıkış yoludur.
- **İzole ortam uyarısı** (`ORKESTRA_IZOLE_UYARI=0` kapatır): kod kartı git deposunun ana çalışma ağacında koşuyorsa `on_kontrol` çıktısında `izole-ortam` uyarısı ve gölge kaydı oluşur. İzole ortam şart değildir; hiçbir modda reddetmez.

## Mühendislik kontrolü: zincir, kademe, üç kapı (ORK-ADR-0179)
- Zincir: G (mevcut durum gap) → P (`**Gap:**`, `**Sözleşme:**`) → S (sözleşme kriteri) → T (plan `## Doğrulama planı`: `- **T1:** S1 — ne — Komut: `...``; isteğe bağlı `Eval:`, `Engel:`, `Kapsam:`) → E (`kanit.jsonl`). Her S en az bir T ile sınanır; T geliştirmeden önce yazılır.
- Kanıt yalnız `orkestra is kanit <iş> T<n>` ile alınır: komut plandan okunur, çıkış, commit ve kapsam dosyası imzası yazılır. Kapsam dosyası ya da T komutu sonra değişirse E bayattır, yeniden koşulur. Agentic T (`Eval:`) model, prompt sürümü, eval seti ve koşu sayısı taşır (çıktıda `EDEL_EVAL` JSON satırı ya da `--model --prompt-surum --eval-seti --kosu`).
- Kademe `is ac --kademe hafif|standart|kritik` (varsayılan standart; `--kucuk` hafiftir). Kapı kontrolleri ve eval asgari koşusu kademeye göre `ayarlar/edel.json`'dadır.
- `orkestra is kontrol <iş>` kapı 1 (Başlangıç), 2 (Geliştirme), 3 (Doğrulama ve yayın) için PASS/FAIL/BLOCKED verir (çıkış 0/1/2); `Engel:` taşıyan T BLOCKED yapar, FAIL'i örtmez. Kapanıştan önce koşulur; sözleşme `## Sonuç` (ya da çalışma özeti) her S'yi anar.
- `orkestra is gorunum <iş>` 01-Baslangic, 02-Gelistirme, 03-Dogrulama-ve-Yayin görünümlerini kayıttan üretir; elle düzenlenmez, kaynak düzeltilir.
- Mod `golge`: `is kapat` kapı 3 PASS değilse `kapi_golge` (kapi: edel) yazar, kapanışı engellemez. İhlale geçiş kapı başına ayrı ORK-ADR ister (P-028).

## Teknik not
- İşçi is-bitti'si `--teknik <json_dosya>` (yaklasim, neden_bu_yol, alternatifler, entegrasyon, riskler) olmadan geçmez (çıkış 4; kapatma: `ORKESTRA_TEKNIK_KAPISI=0`). Denetçi teknik notun çıktıyla tutarlılığına bakar; tutarsızsa ret.

## İyi uygulamalar: veri ve agentic ürünler
Sorgu üreten, veriyle cevap veren ya da araç çağıran bir sistem (ajan, rapor, panel) tasarlanırken ya da incelenirken bu listeye bakılır. Kaynak: RNV agentic kod okuması (18.10.2026).
- **Anlamsal katman:** metrik bir kez tanımlanır (ad, formül, kapsam; ör. ciro KDV dahil mi, hangi kanal, hangi tarih kolonu), sorgular oradan üretilir. Aynı metriği her istemde ya da sorguda yeniden yazmak tutarsız sayı üretir.
- **Değerlendirme odaklı geliştirme:** altın soru seti (soru, beklenen cevap ya da sorgu) önce kurulur; her değişiklik bu sete karşı ölçülür. Set olmadan "iyileşti" denmez.
- **Katmanlı güvenlik ve izleme:** girdi kapısı, üretilen SQL'in doğrulayıcısı (salt okuma, izinli tablo), kullanıcıya özgü veri sınırı ve çağrı izi (ör. Langfuse). Tek kapıya güvenilmez.
- **Netleştirme sorusu:** soru birden çok biçimde okunabiliyorsa (dönem, metrik, kapsam) tahmin edilip cevaplanmaz, tek soruyla netleştirilir.
- **Çoklu araç planlayıcı:** birden çok araç gerektiren soruda önce adım planı çıkarılır, araçlar sırayla ya da paralel çağrılır, sonuçlar birleştirilir.
- **Sonuç önbelleği:** aynı soru, parametre ve veri sürümü için tekrar hesaplanmaz; anahtar bu üçlüdür, veri yenilenince geçersiz olur.

## İzin politikası
- Kural P-010 (kayıtlı eklenti kuralları): halka açık ve geri alınamaz eylemler dışında onay istenmez. Orkestra açık her projede eklentinin PreToolUse hook'u kapı dışı çağrıya `allow` verir; kapı eylemlerinde `ask`, zorla/silme/ayna push'ta `deny` verir.
- Kapı (sorulur): `git push`; `gh pr|issue|release|repo|gist|workflow|label|secret|variable` yazma komutları; `gh api` ile yazma; GitHub ve Jira/Atlassian adreslerine yazan `curl`/`Invoke-RestMethod`; `mcp__github__*` ve Atlassian/Jira MCP araçlarının okuma (`get_`, `list_`, `search_`, `fetch`, `lookup`) dışındakileri. Yeni eklenen bir yazma aracı otomatik kapıya düşer. Atlassian kapısı sunucu bazlıdır: araç adı Jira ya da Atlassian içermeyen sunucuda (ör. `mcp__<uuid>__executeWrite`) da okuma listesi dışındaki her araç sorulur; ayrıca sunucu kimliğinden bağımsız her `execute(Write|Destructive)` aracı kapıdadır. Sunucu kimliği `ayarlar/izin_politikasi.json` `mcp` listesindedir.
- Neden hook: Claude Code eklentinin `settings.json`'ında `permissions` ve `defaultMode` uygulanmaz (yalnız `agent`, `subagentStatusLine`); eklentinin kullanıcıya taşıyabildiği tek mekanizma hook'tur. Hook `allow` dese de kullanıcının settings `deny`/`ask` kuralları geçerlidir; kapı bu yüzden settings'i aşmaz.
- Ayar: `ayarlar/izin_politikasi.json` (mod `genis` | `kapi` | `kapali`, desenler); proje ezmesi `<durum klasörü>/izin_politikasi.json`; `ORKESTRA_IZIN=0|kapi|genis` ortam değişkeni ikisini de ezer. Görmek için `orkestra izin goster`, sınamak için `orkestra izin sina --arac Bash --komut "git push"`. SessionStart bağlamı politikayı tek satırla duyurur.
- Sınır: kabuk desenleri en iyi çabadır (betik içinden API çağrısı yakalanmaz); `bypassPermissions` modunda hook kararının geçerliliği belgelenmemiştir, bu moda güvenme. Politika yalnız orkestra açık (`.claude/orkestra/` olan) projelerde çalışır.

<!-- eklenti-kurallari:basla -->
## Kayıtlı eklenti kuralları

Tam metin ve nedenler `KURALLAR_KAYITLI.md` dosyasındadır (`orkestra kural` yönetir); kuralı kimliğiyle ara.

Etkin kimlikler: K-003, K-004, K-005, K-006, P-001, P-005, P-006, K-007, P-008, P-009, P-010, P-011, P-012, P-013, P-014, P-015, P-016, P-017, P-018, P-019, P-020, P-021, P-022, P-023, P-024, P-025, P-026, P-027, P-028, P-029, P-031, P-030, P-032, P-033, P-034, P-035, P-036, P-037, P-038, P-039, P-040, P-042, P-043, P-044, P-045, P-048, P-046, P-047, P-049, P-050, P-051, P-052, P-053, P-055, P-056, P-057, P-058, P-059, P-060, P-061.
<!-- eklenti-kurallari:bitis -->
