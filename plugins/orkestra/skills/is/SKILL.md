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
- Planı bir JSON dosyasına yaz (scratchpad'e; `ref` alanı ile birbirine bağla) ve kartları oluştur:
  `orkestra kart toplu --json-dosya <plan.json>` → çıktıdaki kart listesini sakla.
- Kullanıcıya planı 3-8 satırla göster (kart, basamak, paralel gruplar). Kullanıcı açıkça "önce planı göster" demediyse onay beklemeden devam et.

## 2. Dağıt
Tercih edilen yol, orkestra workflow'u (kayıtlı betik):
- Workflow aracını `name: "orkestra:calistir"` ve `args: { "gorevler": [<kart toplu çıktısındaki id'lerle, kart goster JSON'ları>] }` ile çağır. Her kart nesnesinde `id, baslik, basamak, girdi, kabul_kriterleri, yazma_alani, bagimliliklar` olsun.
- Ad ile bulunamazsa betiği `scriptPath` ile çalıştır: `${CLAUDE_PLUGIN_ROOT}/workflows/calistir.js`.
- Betik her kart için şunu yapar:
  - basamağa uygun işçi ajanı çalıştırır;
  - ardından AYRI bir `orkestra:denetci` çalıştırır (işçinin bir üst basamağında);
  - T3 ve üstünde iki mercekle denetler;
  - aynı basamakta iki ret gelirse basamağı yükseltir;
  - bağımlılık onaylanmadıysa o işi atlar.

Workflow kullanılamıyorsa (izin yok ya da kapalı) elle dağıt:
- Bağımsız kartlar için Agent aracını AYNI mesajda birden çok kez çağır, `run_in_background: true` ile.
- `subagent_type` işçi kartın basamağına göre seçilir: `orkestra:isci-t1` … `orkestra:isci-t4`.
- Her ajanın istemi `#GOREV:<id> #SUREC:is` satırıyla başlar.
- Her işçi bitince ayrı bir `orkestra:denetci` çalıştır. Çağrıda `model` işçinin bir üstü olsun: T1→sonnet, T2→opus, T3/T4→opus. İstem `#GOREV:<id> #SUREC:denetim` ile başlar.
- Ret gelirse aynı basamakta en çok iki düzeltme dene (`#SUREC:duzeltme`). Hâlâ ret varsa `orkestra kart yukselt <id> --basamak <üst> --neden "..."` ile yükselt ve bir üst işçiyle yeniden dene.

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

## Kurallar
- `orkestra …` komutlarını tek başına çalıştır (zincir, boru ya da yönlendirme yok).
- Ortak defteri baştan sona okuma. Gerektiğinde `orkestra defter baglam <id>` ya da `orkestra defter ozet` kullan.
- Bitiş kapısı açık kartı olan oturumu durdurur. Bilerek bırakacağın kartı `beklemede` yap.
