---
name: is
description: Orkestra ile bir işi yürüt — ana ajan planlar (görev kartları), işleri maliyet basamağına göre işçilere dağıtır, her çıktıyı AYRI bir denetçiden geçirir, bağımsız işleri paralel koşturur ve onaylı sonucu toplayıp getirir. Birden fazla adımı, dosyası ya da bağımsız parçası olan her iş için kullan; tek satırlık soru-cevap için kullanma.
when_to_use: Kullanıcı çok adımlı bir iş istediğinde ("şunu yap", "hazırla", "doğrula", "tara", "dönüştür"), işin parçaları paralel yürütülebildiğinde ya da kalite için ayrı denetim gerektiğinde.
argument-hint: "<istek>"
---
# /orkestra:is — planla, dağıt, denet, topla

İstek: $ARGUMENTS

Sen ANA AJANSIN. Planlar, dağıtır, toplarsın. İşçi işini kendin YAPMAZSIN ve hiçbir çıktıya onay YAZMAZSIN (hook'lar bunu zaten engeller).

## 0. Hazırlık
- `orkestra kart liste` ile açık kartlara bak. Bu projede orkestra kapalıysa (`orkestra: bu projede orkestra açık değil`) önce `/orkestra:baslat` öner ve dur.
- İstek belirsizse, işi değiştirecek tek bir soru sor. Değiştirmeyecek ayrıntılar için makul varsayım yap ve planda yaz.

## 1. Planla (sen, Opus 5.5 medium)
- İsteği alt işlere böl. Büyük ya da dağınık isteklerde önce ucuz ön sınıflama al: Agent aracı ile `orkestra:triyaj` (Haiku). Kararı yine sen verirsin.
- Önce projedeki skill'lere bak. Bir alt iş için uygun skill varsa işçiye "şu skill'i kullan" diye yaz.
- Her alt iş için şunları belirle:
  - `baslik`
  - `basamak`: T0 betik (T1 işçi çalıştırır), T1 Haiku, T2 Sonnet, T3 Opus medium, T4 Opus xhigh. Kuşkudaysan DAHA DÜŞÜK basamağı seç; yükseltmeyi denetçi reddi tetikler.
  - `kabul_kriterleri`: ölçülebilir, kanıtla doğrulanabilir.
  - `yazma_alani`: glob listesi. Paralel işlerin alanları KESİŞMEMELİ. README, notlar günlüğü gibi ortak dosyaları yalnız sentez adımında sen güncellersin.
  - `bagimliliklar`: yalnız gerçekten çıktısını bekleyen işler. Gereksiz bağımlılık paralelliği öldürür.
- Kod üreten (program, betik, modül değiştiren) her alt iş test-önce yürür. Kartına ayrıca şunları yaz:
  - `sinif`: `"kod"`;
  - `test_komutu`: proje kökünde kabukla koşulan, geçince 0 dönen test komutu (ör. `python -m unittest discover -s tests -p test_x.py`);
  - `test_alani`: test dosyalarının glob listesi (proje köküne göre). Testleri `orkestra:test-yazari` yalnız buraya yazar.
  - İşçinin `yazma_alani` `test_alani`'nı İÇERMEZ (kesişmez). İşçi testi değiştiremez, yalnız testleri geçirecek kodu yazar.
  - CLI, `sinif: kod` kartında `test_komutu` ve `test_alani` olmadan kartı kabul etmez.
- Planı bir JSON dosyasına yaz (scratchpad'e; `ref` alanı ile birbirine bağla) ve kartları oluştur:
  `orkestra kart toplu --json-dosya <plan.json>` → çıktıdaki kart listesini sakla.
- Kullanıcıya planı 3-8 satırla göster (kart, basamak, paralel gruplar). Kullanıcı açıkça "önce planı göster" demediyse onay beklemeden devam et.

## 2. Dağıt
Tercih edilen yol, orkestra workflow'u (kayıtlı betik):
- Workflow aracını `name: "orkestra:calistir"` ve `args: { "gorevler": [<kart toplu çıktısındaki id'lerle, kart goster JSON'ları>] }` ile çağır. Her kart nesnesinde `id, baslik, basamak, girdi, kabul_kriterleri, yazma_alani, bagimliliklar` olsun; kod kartında ayrıca `sinif, test_komutu, test_alani`.
- Ad ile bulunamazsa betiği `scriptPath` ile çalıştır: `${CLAUDE_PLUGIN_ROOT}/workflows/calistir.js`.
- Betik her kart için şunu yapar:
  - basamağa uygun işçi ajanı çalıştırır;
  - işten önce T0 ön kontrol `taban`, her işçiden sonra denetçiden önce `kontrol` çalıştırır (`scripts/on_kontrol.py`; ihlalde denetçi çağrılmaz, ret sayılır);
  - ardından AYRI bir `orkestra:denetci` çalıştırır (işçiyle aynı basamak modelinde; kartta toplam 2 retten sonra opus; yeniden denetim yalnız önceki karşılanmayan kriterler + gerileme);
  - T3 ve üstünde iki mercekle denetler;
  - aynı basamakta iki ret gelirse basamağı yükseltir;
  - bağımlılık onaylanmadıysa o işi atlar.
- Kod kartında (`sinif: kod`) sıra şöyledir:
  1. **Test:** `orkestra:test-yazari` (`#SUREC:test-yaz`) kabul kriterlerinden testleri `test_alani`'na yazar.
  2. **Kırmızı kapı:** `orkestra:isci-t1` (`#SUREC:test-kapisi`) `orkestra kart test-kos <id> --asama kirmizi` çalıştırır. Kod yokken testler başarısız olmalıdır; geçerse test dosyaları kilitlenir. Geçmezse test yazarına geri bildirimle en çok 2 yeniden deneme yapılır; yine geçmezse kart `reddedildi` (neden `kirmizi-teyit`).
  3. **İş:** basamağa uygun işçi kodu yazar (testlere dokunmaz).
  4. **Yeşil kapı:** aynı kapı ajanı `--asama yesil` çalıştırır. Geçmezse denetçi ÇAĞRILMAZ; işçiye test çıktı kuyruğuyla düzeltme turu açılır. Bu tur ret sayılır ve basamak yükseltmeye dahildir.
  5. **Denetim:** mercekler + `test kalitesi` merceği. Denetçi yeşil kayıt yoksa onay yazamaz (CLI zorlar).
  - Denetçi `TEST:` önekli bulgu ile ret verirse kart `reddedildi` (neden `test-kalitesi`) döner; işçiye düzeltme açılmaz.

Workflow kullanılamıyorsa (izin yok ya da kapalı) elle dağıt:
- Bağımsız kartlar için Agent aracını AYNI mesajda birden çok kez çağır, `run_in_background: true` ile.
- `subagent_type` işçi kartın basamağına göre seçilir: `orkestra:isci-t1` … `orkestra:isci-t4`.
- Her ajanın istemi `#GOREV:<id> #SUREC:is` satırıyla başlar.
- Her işçi bitince ayrı bir `orkestra:denetci` çalıştır. Çağrıda `model` işçiyle aynı basamakta olsun: T1→haiku, T2→sonnet, T3→opus (high), T4→opus (xhigh); kartta toplam ret ≥2 olduktan sonra opus. İşçiden önce `python ${CLAUDE_PLUGIN_ROOT}/scripts/on_kontrol.py taban <id>`, işçiden sonra denetçiden önce `... kontrol <id> --ciktilar a,b` çalıştır; `gecti=false` ise denetçiyi çağırma, ret say. İstem `#GOREV:<id> #SUREC:denetim` ile başlar.
- Ret gelirse aynı basamakta en çok iki düzeltme dene (`#SUREC:duzeltme`). Hâlâ ret varsa `orkestra kart yukselt <id> --basamak <üst> --neden "..."` ile yükselt ve bir üst işçiyle yeniden dene.
- Kod kartında (`sinif: kod`) elle dağıtımda da aynı sıra izlenir:
  1. `orkestra:test-yazari` çalıştır (istem `#GOREV:<id> #SUREC:test-yaz`; test komutu ve test alanını yaz).
  2. Kırmızı kapı: `orkestra:isci-t1` ile (istem `#GOREV:<id> #SUREC:test-kapisi`) `orkestra kart test-kos <id> --asama kirmizi` koştur. Geçmezse test yazarına geri bildirimle en çok 2 kez yeniden dene; yine geçmezse kartı reddedilmiş say (neden `kirmizi-teyit`) ve planı düzelt.
  3. İşçiyi çalıştır.
  4. Yeşil kapı: aynı biçimde `--asama yesil`. Geçmezse denetçiyi çağırma; işçiye test çıktı kuyruğuyla `#SUREC:duzeltme` turu aç (ret sayılır, iki retten sonra yükselt).
  5. Yeşil geçince denetçiyi çalıştır; mercek listesine `test kalitesi` ekle.

## Test kalitesi reddi (kod kartı)
- Denetçi `TEST:` önekli bulgu ile ret verdiyse sorun koddaki değil testteki eksiktir. Testler kilitli olduğu için işçi bunu düzeltemez.
- Kilidi yalnız sen açarsın: `orkestra kart test-kilit-ac <id> --neden "<denetçinin TEST: bulgusu>"`.
- Sonra kartı yeniden planla (gerekirse kabul kriterlerini ya da `test_alani`'nı düzelt) ve test-önce akışını baştan yürüt: test yazarı → kırmızı → işçi → yeşil → denetim.
- Kırmızı teyit reddinde (`kirmizi-teyit`) kilit yoktur. Kriterlerin test edilebilirliğini ve `test_komutu`'nu gözden geçirip yeniden dağıt.

## 3. Topla ve getir
- Workflow sonucunu ya da işçi ve denetçi yanıtlarını oku. `orkestra kart liste` ile durumları doğrula.
- Onaylı her kart için çıktıları kendin gözden geçir (dosyaları aç). Sonra `orkestra kart teslim <id> --ozet "<tek cümle>"`.
- Reddedilen ya da atlanan kart için kullanıcıya nedenini söyle. Ya planı düzelt ya da `orkestra kart durum <id> beklemede --not "neden"` (ya da `iptal`) yap.
- Ortak dosyalar (README, dizinler, notlar günlüğü) gerekiyorsa şimdi sen güncelle.
- Kullanıcıya tek teslimat mesajı ver:
  - ne üretildi (dosya bağlantılarıyla);
  - denetim sonucu;
  - kart başına basamak ve maliyet (`orkestra maliyet rapor --gun 1` çıktısından kısa tablo);
  - açık kalanlar.

## Panelden karar ve kural
- Belirsiz ve kullanıcının vermesi gereken bir karar varsa ve kullanıcı paneli izliyorsa: `orkestra onay iste --baslik "..." --metin "..." --secenek "A" --secenek "B"`. Cevap sonraki mesajda hook bağlamıyla gelir.
- Kalıcı bir kural kararı alınırsa: `orkestra kural oner --metin "..." --neden "..."`; kullanıcı panelde etkinleştirir.

## Kurallar
- `orkestra …` komutlarını tek başına çalıştır (zincir, boru ya da yönlendirme yok).
- Ortak defteri baştan sona okuma. Gerektiğinde `orkestra defter baglam <id>` ya da `orkestra defter ozet` kullan.
- Bitiş kapısı açık kartı olan oturumu durdurur. Bilerek bırakacağın kartı `beklemede` yap.
