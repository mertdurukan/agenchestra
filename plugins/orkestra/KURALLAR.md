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
  - Kuşkuda: ana ajanın bağlamı büyükse (≳150k) işi kısa bir kartla ucuz basamağa ver. Bağlam küçükse ve iş tek adımlıysa doğrudan yap.
  - Doğrudan yapılan işte denetçi yoktur. "Onaylandı" deme; neyi nasıl doğruladığını (test, yeniden okuma) söyle.

## Maliyet basamakları
- T0: hazır betik. T1: Haiku. T2: Sonnet. T3: Opus medium (planlama burada). T4: Opus xhigh.
- Bir işe izin veren en düşük basamakla başla.
- Yükseltmeyi denetçi reddi tetikler.
- Kart başına ajan tavanı vardır (varsayılan 8; workflow `args.kart_ajan_tavani`). Tavan dolan kart `tavan` sonucuyla durur; ana ajan nedeni okuyup kartı `beklemede` yapar, yeniden koşturmaz.
- Kart kilidi: teslim/onaylı/iptal kart ve başka ajanda işlenen kart yeniden işlenmez (`kart durum isleniyor` çıkış 6). Aynı kartı iki koşuya verme.

## Denetim
- Her işçi çıktısını ayrı bir denetçi (`orkestra:denetci`) incelesin. Kimse kendi işini onaylamaz.
- Denetçi işçiyle aynı modelde koşsun (T2 işi, Sonnet denetçi).
- Opus denetçi yalnız T3-T4 işlerinde ve kartta ikinci retten sonra kullan.
- Test ve T0 ön kontrol (`on_kontrol.py`: yeni test hatası, CRLF/BOM, kapsam dışı yazma, eksik token) ajan değildir: işçinin `kart durum is-bitti` çağrısında CLI koşar. Geçmezse is-bitti kaydedilmez ve işçi aynı oturumda düzeltir; denetçi çağrılmaz.
- Denetçi testi yeniden koşmaz; CLI kaydına ve diff'e bakar.
- Kayıtlı ön kontroller (`ayarlar/on_kontrol.json`, proje ezmesi `.claude/orkestra/on_kontrol.json`): `kanit-satiri` (`K<n>:` kanıt satırı) ve `sayi-tutarli` kontrolü yalnız bağlı etkin bir kural varsa koşar (`kural bagla K-xxx --kontrol <kimlik>`; kural kaldırılınca kapanır). İlk mod `golge` (uyarı + kayıt); `mod: ihlal` is-bitti'yi reddeder ve kullanıcı kararıdır. İşçi her kriter için `--kanit "K<n>: ..."` verir.
- Denetim politikası (`ayarlar/denetim_politikasi.json`, varsayılan `mod: tam`): grup (sınıf×basamak) ilk-ret oranı, tdd/yüksek risk hariç tutma ve deterministik örnekleme ile denetçiyi atlayabilir; `golge` yalnız kaydeder, `etkin` ancak geçit (`denetim_politika.py gecit`) açıkken ve CLI'de otomatik onay yazar. Açma kullanıcı kararıdır.
- Kart başına testler `test_alani` dosyalarıyla sınırlıdır (geniş komut otomatik daralır); tam paket iş sonunda bir kez koşar, kart başına değil.
- Test-önce (test yazarı + kırmızı kapı) yalnız riskli kod kartında (`tdd: true`): davranış değişikliği olan çok dosyalı ya da kanonik mantık. Diğer kod kartında işçi kodu ve testi birlikte yazar.
- Yeniden denetim yalnız önceki retteki karşılanmayan kriterlere ve gerilemeye baksın.

## Dağıtım
- Bağımsız işleri paralel koştur.
- Paralel işlerin yazma alanları kesişmesin.
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
- Kuralları mevcut LLM etiketleriyle karşılaştırarak doğrula.

## Odak ve sıradaki adımlar
- Her sohbet ilk işte bir işe bağlanır: mevcut işse `orkestra is devam <id>`, yeni işse `orkestra is ac <başlık> --klasor <görev klasörü>`. Sıradaki adımlar sohbet hafızasında değil işin todo.md'sinde tutulur: ortaya çıkınca `orkestra is todo <id> --ekle "…"`, bitince `orkestra is todo <id> --bitti <n|parça> [--not]`; yeni sohbet listeyi oradan okuyup devam eder. Not: is todo birden çok --bitti/--ekle alabilir; art arda todo yazmalarını tek çağrıda birleştir.
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

## Teknik not
- İşçi is-bitti'si `--teknik <json_dosya>` (yaklasim, neden_bu_yol, alternatifler, entegrasyon, riskler) olmadan geçmez (çıkış 4; kapatma: `ORKESTRA_TEKNIK_KAPISI=0`). Denetçi teknik notun çıktıyla tutarlılığına bakar; tutarsızsa ret.

## İzin politikası
- Kural P-010 (kayıtlı eklenti kuralları): halka açık ve geri alınamaz eylemler dışında onay istenmez. Orkestra açık her projede eklentinin PreToolUse hook'u kapı dışı çağrıya `allow` verir; kapı eylemlerinde `ask`, zorla/silme/ayna push'ta `deny` verir.
- Kapı (sorulur): `git push`; `gh pr|issue|release|repo|gist|workflow|label|secret|variable` yazma komutları; `gh api` ile yazma; GitHub ve Jira/Atlassian adreslerine yazan `curl`/`Invoke-RestMethod`; `mcp__github__*` ve Atlassian/Jira MCP araçlarının okuma (`get_`, `list_`, `search_`, `fetch`, `lookup`) dışındakileri. Yeni eklenen bir yazma aracı otomatik kapıya düşer.
- Neden hook: Claude Code eklentinin `settings.json`'ında `permissions` ve `defaultMode` uygulanmaz (yalnız `agent`, `subagentStatusLine`); eklentinin kullanıcıya taşıyabildiği tek mekanizma hook'tur. Hook `allow` dese de kullanıcının settings `deny`/`ask` kuralları geçerlidir; kapı bu yüzden settings'i aşmaz.
- Ayar: `ayarlar/izin_politikasi.json` (mod `genis` | `kapi` | `kapali`, desenler); proje ezmesi `<durum klasörü>/izin_politikasi.json`; `ORKESTRA_IZIN=0|kapi|genis` ortam değişkeni ikisini de ezer. Görmek için `orkestra izin goster`, sınamak için `orkestra izin sina --arac Bash --komut "git push"`. SessionStart bağlamı politikayı tek satırla duyurur.
- Sınır: kabuk desenleri en iyi çabadır (betik içinden API çağrısı yakalanmaz); `bypassPermissions` modunda hook kararının geçerliliği belgelenmemiştir, bu moda güvenme. Politika yalnız orkestra açık (`.claude/orkestra/` olan) projelerde çalışır.

<!-- eklenti-kurallari:basla -->
## Kayıtlı eklenti kuralları

Bu bölüm `orkestra kural` komutuyla yönetilir (`kurallar/eklenti_kurallari.json`); elle düzenleme.

- ZORUNLU, istisnasız: Okunmak üzere üretilen belgelerden (mevcut durum, plan, todo, bulgu, rapor, özet) yalnız bu turda yeni oluşan ya da içeriği değişen belge, yanıtın sonunda her belge için bir satırla verilir: '<belge türü>: <bağlantı>' ('mevcut durum', 'plan dosyası', 'to-do dosyası' dahil). Değişmeyen belge tekrar verilmez. Todo'da yalnız madde işaretleme (bitti, not) değişiklik sayılmaz; madde eklenir, çıkarılır ya da yeniden yazılırsa verilir. Yeni iş klasöründe mevcut durum, plan ve todo birlikte verilir. Çalışma dosyaları (kural, kod, betik, test, ayar) verilmez. Bağlantı proje köküne göre göreli, tıklanabilir markdown bağlantısıdır. Turu bitiren bir araç ya da kutu varsa bağlantı satırları ondan önce yazılır. (K-003, 2026-10-16)
  - Neden: Kullanıcı 16.10.2026: onaylanıp devam edilen plan, mevcut durum ve todo her yanıtta tekrar verilmesin; yalnız yeni klasör açıldığında ya da içerik (plan, mevcut durum, todo maddeleri) değiştiğinde verilsin; todo'da yalnız madde bitirme bağlantı gerektirmez.
- ZORUNLU, istisnasız: Oturum bir işe bağlıyken bağlı işten farklı bir konu gelirse (başka açık iş, yeni iş ya da yan konu) o konu bu sohbette yapılmaz; yanıtın ilk mesajında, başka hiçbir araçtan önce, başlıkla yeni oturum önerilir (start_session, initiation offer). Kullanıcı 'burada yap' derse o zaman orkestra is devam <id> ya da orkestra is ac ile işe bağlanıp yapılır. Bağlı işin parçası olan devam, soru ve düzeltme mesajları öneri tetiklemez. Hook (is_yonlendirme.yonlendir) bu kuralı her yeni görev mesajında hatırlatır. (K-004, 2026-10-16)
  - Neden: Kullanıcı 16.10.2026: bir sohbette 50 farklı konu konuşuluyor (bir Jira kapsamından orkestra güncellemesine geçildi); orkestra konu değişince yeni sohbet önermeliydi, hiçbir kural ya da hook bunu zorlamıyordu.
- ZORUNLU, istisnasız: Maksimum okunabilirlik için hem sohbette hem de oluşturulan her belgede (plan, todo, çalışma özeti, bulgu, jira_onerisi, rapor) şu düzen uygulanır: (1) Başlık ve ona bağlı etiketli alanlar (Amaç, Arıza sınıfı, Neden, Kanıt, Durum gibi) ayrı paragraflarda alt alta yazılır, tek paragrafta birleştirilmez; etiket kalın yazılır. (2) Liste ve sıralı maddeler (yapılacak işler, adımlar, bulgular) her madde ayrı satırda, madde işaretiyle yazılır; maddeler virgül, noktalı virgül ya da ' · ' ile tek satıra ya da tek paragrafa sıkıştırılmaz. (3) Belgeyi insan okuyacağı için uzun tek paragraf yerine kısa paragraflar ve boş satırlar kullanılır. Belge teslim edilmeden önce bu düzene karşı gözden geçirilir. (4) Yazılan her şey, okuyanın bağlamı bilmediği varsayımıyla yazılır: 'kendi sunucumuz', 'bizim kod' gibi belirsiz sahiplik ifadeleri yerine ilk yazımda somut ad (adres, sürüm, yol, tablo, müşteri) kullanılır. (K-005, 2026-10-16)
  - Neden: Kullanıcı 16.10.2026: 'Son yapılacak işler' tek satırda sıkıştırılmış verildi; amaç ve arıza sınıfı birleşik yazıldı. Dosyaları insan okuyor; plan, todo ve çalışma özetleri maksimum okunabilirlikte, her madde ayrı satırda olmalı.
- ZORUNLU, istisnasız: Her hata, kusur ya da ret nedeni kök nedene inilerek çözülür; sorun oluştuğu yerde, oluşmadan önlenir. 'Üret, sonra denetle, sonra düzelt' çözüm sayılmaz; denetim yalnız güvenlik ağıdır. Her hatada önce şu sorulur: 'Bunu üretirken, üretildiği yerde (kural, şablon, skill, betik, kart, istem) hiç oluşmadan çözebilir miydik?' Cevap evetse düzeltme kaynağa yapılır, çıktıyı sonradan yamamak ya da yalnız sonradan yakalayan bir betik, hook ya da denetçi eklemek yetmez. Yeni bir kontrol önerilmeden önce kaynakta çözümün neden olmadığı yazılır. (K-006, 2026-10-16)
  - Neden: Kullanıcı 16.10.2026: özette 'kendi sunucumuz' belirsiz terimi çıktı; ilk önerim sonradan tarayan bir betik ve hook'tu. Kullanıcı bunu reddetti: terim ilk yazımda kesin yazılmalı; sorun oluştuğu yerde çözülmeli.
- ZORUNLU, istisnasız: Yanıt, sorunun ağırlığı kadardır. Bilgi sorusuna ('ne demek', 'nedir', 'neden', 'gerekir mi') en çok 5 cümleyle cevap verilir; iş durumu, tablo, kaynak taraması ve alt ajan eklenmez; tek istisna kullanıcının açıkça kapsamlı inceleme istemesidir. Teslim ve özet mesajı en çok 5 maddedir: ne değişti, ana sayı, karar bekleyen tek konu. İşçi ya da alt ajan raporu sohbete aktarılmaz; ayrıntı rapor dosyasında ve işin todo'sunda kalır. Sıradaki adımlar sohbette tekrarlanmaz, todo'ya yazılır. (P-001, 2026-10-16)
  - Neden: Uzun teslim mesajı asıl kararı gölgeler ve gereksiz token harcatır; ayrıntı dosyada kalınca kullanıcı tek bakışta karar verir.
- ZORUNLU, istisnasız: Her işin tek plan dosyası işin klasöründeki plan.md, tek todo dosyası todo.md'dir (todo orkestra is todo ile yönetilir); kopya liste ya da başka adlı plan tutulmaz, uzun ek analiz ayrı dosyada durabilir ama plan.md'den bağlanır. Plan ve todo gerektiren her konuda sıra şudur ve her adım bir öncekinden beslenir: (1) mevcut_durum_<YYYYMMDD>.md, (2) plan.md, (3) todo.md. Sonraki adım önceki yazılmadan başlamaz. (1) Mevcut durum, değişikliğin dokunacağı mevcut kodu, belgeyi ya da veriyi araştırır: istek ya da veri hangi yoldan geçiyor, bugün ne yapıyor ve hangi korumalar ya da bağlantılar çalışıyor, değişiklik hangi dosya, fonksiyon ve davranışa dokunuyor (etki haritası: yer, bugünkü davranış, dokunmanın riski), işin dalında zaten yapılmış olanlar (git durumu), bilinmeyenler. Her iddia dosya:satır, komut çıktısı ya da ölçüm saatiyle desteklenir; bakılmayan yer 'teyit gerekir' diye yazılır. (2) Plan, mevcut durumdan çıkan sonuçlara dayanır: her plan maddesi dayandığı mevcut durum bölümünü ve sonucunu gösterir, dokunacağı yeri mevcut durumdaki etki haritasından alır; mevcut durumda karşılığı olmayan plan maddesi yazılmaz, önce mevcut durum güncellenir. plan.md başında mevcut duruma bağlantı verilir. (3) Todo yalnız plan maddelerinden türetilir: her todo satırı plan maddesini (P1, P2…) gösterir; plan maddesi olmayan satır eklenmez, önce plan güncellenir. Planlama sırasında mevcut durumda eksik çıkan bilgi mevcut durum dosyasına eklenir, sonra plan ve todo güncellenir; ters yönde, yani todo'dan plana ya da plandan mevcut duruma boşluk yamanmaz. Teslim bağlantıları K-003'e göre verilir; mevcut durum varsa onun satırı en başta yer alır. Kod kartındaki mevcut durum notu (orkestra kart mevcut) bu sıranın kart düzeyindeki karşılığıdır, yerine geçmez. Dosyalar K-005 okunabilirlik düzenine uyar. (P-005, 2026-10-16)
  - Neden: Kullanıcı 16.10.2026: yapılacak değişiklikler mevcut duruma çok dokunuyor; plan ve todo'dan önce projenin bugünkü durumunu gösteren araştırma ve analiz ilk dosya olmalı, orkestra her işte bunu yapmalı.
- ZORUNLU, istisnasız: Commit'ler yerelde değişiklikleri kayda almak içindir (otomatik commit'ler dahil). Kullanıcı push istediğinde, push'tan hemen önce, yalnız henüz push edilmemiş commit'ler tek commit olarak birleştirilir. Sıra: (1) tek commit mesajı kullanıcıya gösterilir, (2) onaylanırsa birleştirilir, (3) push açık isteğe bağlıdır ve ayrıca sorulur. Birleştirmeden önce dalda başka oturumun ya da işçinin çalışmadığı doğrulanır. Daha önce push edilmiş commit'ler yeniden yazılmaz. Uzak deposu olmayan depolarda kural uygulanmaz. Commit mesajı sonuna ortamın verdiği atıf satırı eklenir. (P-006, 2026-10-16)
  - Neden: Kullanıcı 16.10.2026: commit'in amacı yapılan değişikliği kayda almak; bir dalda 60'tan fazla çoğu otomatik commit gözden geçirene bir şey anlatmıyordu. Push'tan önce tek commit daha okunur bir PR verir.
- ZORUNLU, istisnasız: Başlatılan her yan oturum, başladığı anda aynı turda üst oturumdan ayrılarak kullanıcının kenar çubuğunda ayrı sohbet olarak görünür (start_session sonrası detach_session). Ayrılan oturumun bitiş bildirimi gelmeyeceği için sonucu oturum durumu okunarak alınır. Kural, ayar ve hafıza dosyaları kullanıcıya dosya olarak verilmez; kısa düz metin açıklaması yeterlidir. (K-007, 2026-10-16)
  - Neden: Kullanıcı 16.10.2026: yeni oturumlar mevcut sohbetin altında açılıyordu, hepsi kenar çubuğunda ayrı sohbet olmalı; ayar yok, tek yol detach. Aynı yanıtta CLAUDE.md ve hafıza dosyası bağlantıyla verilince kullanıcı bunu istemedi.
- ZORUNLU, istisnasız: Kullanıcıya 'senin yapman gerekenler' listesi yazmadan önce her madde sınanır: elimde araç, anahtar, API ya da tarayıcı varsa işi kendim yaparım. Listeye yalnız gerçekten kullanıcıya ait olanlar girer: parola girişi, değeri yalnız onda olan sır, hesap açma, iş kapanışı, push ya da PR kararı, başka ekibin işi. Yazma ya da ayar değişikliği onay gerektiriyorsa iş listeye yazılmaz; tek cümlelik tek soruyla onay istenir, kullanıcı genel olarak 'ne gerekiyorsa yap' demişse onay verilmiş sayılır. API'si olmayan iş için önce tarayıcıyla denenir. İzin sistemi bir eylemi engellerse dolanılmaz; neyi neden yapmak istediğim söylenir ve onay istenir. (P-008, 2026-10-16)
  - Neden: Kullanıcı 16.10.2026: erişim anahtarı verildiği halde API ile yapılabilecek işler kullanıcıya liste olarak yazıldı; bu davranış projeden bağımsız, her projede geçerli.
- ZORUNLU, istisnasız: Bir iş (görev) tamamen kapanıyorsa kapanıştan önce görev bitiş raporu yazılır: işin klasöründe doldurulmuş calisma_ozeti_<YYYYMMDD>.md (orkestra is belge <id> ozet; Ana bulgu boş olamaz, ölçülen sayılar komutla, doğrulanmayanlar ve açık işler dahil). Mevcut durum, plan ve todo görev BAŞLANGICI belgeleridir; kapanış teslimi sayılmaz, bitiş raporunun yerine geçmez. Kapanış yanıtında K-003 satırı olarak yalnız çalışma özeti verilir (başlangıç belgeleri bu turda değişmediyse tekrar verilmez). Zorlama: orkestra is kapat doldurulmuş özet yoksa reddeder; iş hiç yapılmadan kapanıyorsa --ozetsiz "neden" gerekir (ORKESTRA_OZET_KAPISI=0 kapıyı kapatır). Hook'un kapıyı hatırlatması yetmez: kapıyı atlayarak kapatmak yasaktır. (P-009, 2026-10-16)
  - Neden: Kullanıcı 16.10.2026: görev bitince bitiş raporu yazılmadı, bunun yerine görev başlangıcında verilecek mevcut durum, plan ve todo dosyaları teslim edildi. Kural metni tek başına yetmedi (K-006): kapanış komutu özet olmadan kapanabiliyordu; kaynak olan kapatma komutuna kapı eklendi.
- ZORUNLU, istisnasız: Halka açık ve geri alınamaz eylemler her seferinde kullanıcıya sorulur: git push, gh ile yazma (PR, issue, release), GitHub MCP yazma araçları, Jira (Atlassian) yazma araçları ve bu adreslere yazan curl/Invoke-RestMethod. Zorla, silme ya da ayna push yapılmaz. Bunların dışındaki her iş (dosya, kabuk, yerel git, tarayıcı, okuma araçları) onay istenmeden yapılır; izin sistemi bir eylemi yine de sorarsa dolanılmaz. Politika ayarlar/izin_politikasi.json dosyasındadır, orkestra izin goster ile görülür; ORKESTRA_IZIN=0 kapatır. Betik içinden API çağrısı en iyi çabayla yakalanır; bu yüzden GitHub/Jira yazma işleri araç ya da gh ile yapılır, betikle değil. (P-010, 2026-10-16)
  - Neden: Kullanıcı 16.10.2026: halka açık ve geri alınamaz süreçler (GitHub push, Jira update/delete/insert) dışında Claude tam yetkili olmalı ve onay istememeli; politika orkestra eklentisini içe aktaran her projede aynı olmalı. Eklenti permissions taşıyamadığı için politika PreToolUse hook'u ile taşınır (Claude Code dokümanı: plugin settings yalnız agent ve subagentStatusLine uygular).
- ZORUNLU, istisnasız: Panelde iki ayrı yerde durum satırı gösterilir. (1) Onaylar sayfasındaki perspektif şeridi yalnız onaylarla ilgili süren arka plan görevlerini (perspektif koşusu, onaylı kararların uygulanması) 'Arka plan görevleri · N sürüyor' satırıyla listeler; hiç yoksa satır gösterilmez. (2) İşler sayfasındaki durum şeridi, arka plan işi süren sohbetleri aynı satırla (yoksa gösterilmez) ve açık işlerin todo sayımını 'Todo: X yapıldı · Y kaldı' satırı ve iş başına kırılımla her zaman gösterir. Todo sayımı ve sohbet görevleri Onaylar sayfasında gösterilmez; sohbette perspektif durumu özetlenirken yalnız (1), iş durumu özetlenirken (2) verilir. Kaynak: panel.py _arka_plan, _sohbet_arka_plan, _todo_sayac; onaylar.js perspDurumCiz; isler.js durumSeridiCiz. (P-011, 2026-10-16)
  - Neden: Kullanıcı 16.10.2026: perspektif panelinde devam eden arka plan görevleri ve todo sayımı görünsün. Kullanıcı 17.10.2026: Onaylar'daki 'Todo: 287 yapıldı · 176 kaldı' satırı onayla ilgisiz (tüm açık işleri sayıyor); todo sayımı ve sohbet görevleri İşler sayfasına taşındı.
<!-- eklenti-kurallari:bitis -->
