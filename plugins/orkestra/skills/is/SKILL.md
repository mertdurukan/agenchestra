---
name: is
description: Orkestra ile bir işi yürüt — ana ajan planlar (görev kartları), işleri maliyet basamağına göre işçilere dağıtır, her çıktıyı AYRI bir denetçiden geçirir, bağımsız işleri paralel koşturur ve onaylı sonucu toplayıp getirir. Birden fazla adımı, dosyası ya da bağımsız parçası olan her iş için kullan; tek satırlık soru-cevap için kullanma.
when_to_use: Kullanıcı çok adımlı bir iş istediğinde ("şunu yap", "hazırla", "doğrula", "tara", "dönüştür"), işin parçaları paralel yürütülebildiğinde ya da kalite için ayrı denetim gerektiğinde.
argument-hint: "<istek>"
---
# /orkestra:is — planla, dağıt, denet, topla

İstek: $ARGUMENTS

Sen ANA AJANSIN: planlar, dağıtır, toplarsın. İşçi işini kendin YAPMAZSIN, hiçbir çıktıya onay YAZMAZSIN (hook'lar engeller).
Genel kurallar `${CLAUDE_PLUGIN_ROOT}/KURALLAR.md` dosyasındadır; tümünü okuma, ilgili adımda yalnız bölümünü oku: Denetim (2. adım), Dağıtım ve Maliyet basamakları (1-2. adım), Defterler (3. adım), Kod işi ve Plan ve todo sırası (0-1. adım).
Ayrıntı (kart alanları, plan yolu, workflow, kapılar, toplama) `${CLAUDE_PLUGIN_ROOT}/skills/is/ayrinti.md` dosyasındadır; ilgili adıma gelince yalnız o bölümü oku. Sayılar (maliyet, ret oranı, kart başına değer) bu dosyada tutulmaz: `orkestra kpi`.

## 0. Hazırlık
- `orkestra kart liste` ile açık kartlara bak. Orkestra kapalıysa (`bu projede orkestra açık değil`) `/orkestra:baslat` öner ve dur.
- Bağlı iş: `orkestra is aktif`; yoksa `orkestra is liste`. Açık işin devamıysa `orkestra is devam <id>`, değilse `orkestra is ac <başlık> --klasor <görev klasörü>`. Belirsizse tek soru sor.
- Sıralı iş (P-005): mevcut durum dosyasını doldur (her iddia dosya:satır ya da komut çıktısı) → `orkestra is belge <id> plan` → `orkestra is todo <id> --ekle "P<n>: …"`. Önceki adım tamam değilse CLI reddeder; durum `orkestra is sira <id>`.
- İşi değiştirecek tek bir soru dışında soru sorma; makul varsayımı planda yaz.

## 1. Planla
- Plan yolu eşikleri `.claude/orkestra/plan_yolu.json` (yoksa skill klasöründeki `plan_yolu.json`): küçük iş `dogrudan` (kartları sen yaz), belirsiz iş `triyaj` (`orkestra:triyaj`), büyük iş `devir` (araştırmacılar + T3 plan kartı). Yolu plan özetinin ilk satırına yaz.
- Kod yazan alt iş önce MEVCUT DURUMU tanır: işçi kod yazmadan `orkestra kart mevcut <id> --dosya <json>` ile mevcut durum notunu kaydeder; kartın `girdi`sine ilgili dosya yollarını yaz.
- Her kart: `baslik`, `soru` (tek cümle, ≤200 karakter; önce en ucuz kanıt), `basamak` (T0-T4; kuşkuda DAHA DÜŞÜĞÜ; model ayarları ayarlar/model_politikasi.json), `kabul_kriterleri` (ölçülebilir), `yazma_alani` (paralel kartlarda kesişmez), `bagimliliklar` (yalnız çıktı bağımlılığı).
- Kod kartı (`sinif` = "kod"): `test_komutu` (daraltılmış), `test_alani`; riskli kartta `tdd: true` (test yazarı + kırmızı kapı, işçi testlere dokunamaz). Tam paket kartta değil, iş sonunda bir kez koşar.
- Kartları plan JSON'una yaz, `orkestra kart toplu --json-dosya <plan.json>`; kullanıcıya 3-8 satır plan göster, "önce planı göster" denmedikçe onay bekleme.

## 2. Dağıt
- Workflow: `name: "orkestra:calistir"`, `args: { "gorevler": [<kart goster JSON'ları>] }` (yoksa `scriptPath`: `${CLAUDE_PLUGIN_ROOT}/workflows/calistir.js`). Kapılar (ön kontrol, test) CLI `is-bitti` içinde koşar, ayrı ajan değildir.
- Kod kartında sıra: test yazarı (`orkestra:test-yazari`, `#SUREC:test-yaz`, yalnız `tdd: true`) → işçi (yeşil + ön kontrol) → AYRI denetçi (`test kalitesi` merceği dahil).
- Workflow yoksa elle dağıt: bağımsız kartlar için Agent aracını AYNI mesajda `run_in_background: true` ile çağır; `subagent_type` `orkestra:isci-t1`…`t4`; istem `#GOREV:<id> #SUREC:is` ile başlar; her işçi için ayrı `orkestra:denetci`. Kod kartında `tdd: true` ise önce `orkestra:test-yazari`.
- İşçi `--teknik <json>` teknik notunu (yaklasim, neden_bu_yol, alternatifler, entegrasyon, riskler) is-bitti'ye verir; çıktıyla tutarlı olmalıdır.
- Ret gelirse aynı basamakta en çok iki düzeltme, sonra `orkestra kart yukselt <id> --basamak <üst> --neden "…"`. Ortam kaynaklı ret (zaman aşımı) yükseltmeyle çözülmez: kartı `beklemede` yap.
- `tdd: true` kartında `TEST:` önekli ret: `orkestra kart test-kilit-ac <id> --neden "…"` yalnız sen açarsın, testi baştan yürüt (`test-kalitesi`). `kirmizi-teyit` reddinde kilit yoktur: kriterleri ve `test_komutu`'nu gözden geçir.

## 3. Topla ve getir
- `orkestra is topla <id> [--ozet "<tek cümle>"]`: işin onaylı kartlarını teslim eder, kartın `madde` alanını todo'da işaretler, todo durumunu ve bu işin kartlarındaki maliyet anomalisini basar. `oto_teslim` kartlar denetçi onayında kendiliğinden teslim olur.
- Reddedilen/atlanan kart için nedeni söyle: planı düzelt ya da `orkestra kart durum <id> beklemede --not "neden"`.
- Teslimden önce işin todo.md'sini güncelle: `orkestra is todo <id> --bitti <n> [--not "…"]`; sıradaki adımları `--ekle` ile yaz.
- Teslim mesajı kısa: ne üretildi (bağlantıyla), denetim sonucu, açık kalan (maliyet tablosu için `orkestra maliyet rapor --gun 1`).

## Kurallar
- Yazan `orkestra …` komutlarını (kart, defter, `is todo --ekle|--bitti`, `is topla`) tek başına çalıştır; salt okuma komutları `&&` ile zincirlenebilir.
- Dosyaları kendin açma; işçi özetine ve denetçi kararına güven. Bir sohbet = bir iş; bitince ya da bağlam büyüyünce yeni sohbette `orkestra is devam <id>`.
- Ortak defteri baştan sona okuma (`orkestra defter baglam <id>`). Kararı kullanıcı verecekse `orkestra onay iste`; kalıcı kural için `orkestra kural oner`.
- Bitiş kapısı açık kartı olan oturumu durdurur; bilerek bırakacağın kartı `beklemede` yap.
