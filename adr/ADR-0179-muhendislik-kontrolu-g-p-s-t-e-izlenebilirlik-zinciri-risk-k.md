# ADR-0179: Mühendislik kontrolü: G-P-S-T-E izlenebilirlik zinciri, risk kademesi, üç kapı ve 01/02/03 görünümleri

**Durum:**

Kabul edildi (I-447, gölge modu). Kapıların ihlal moduna geçişi bu ADR'nin kapsamı dışındadır; P-028 gereği kapı başına ayrı karar ve ADR ister.

**Tarih:**

12.11.2026

**Bağlam:**

- Orkestra iş belgeleri (mevcut durum, sözleşme, plan, todo, çalışma özeti) ayrı ayrı denetleniyordu; belgeler arasında uçtan uca bir zincir yoktu.
- Sözleşme kriteri (S) ile onu sınayan komut arasında kayıtlı bağ yoktu; "test geçti" bilgisi yalnız todo notunda serbest metindi ve hangi kod sürümüne ait olduğu bilinmiyordu.
- Kanıt sonradan bayatlayabiliyordu: kod değişince eski "geçti" notu geçerli görünmeye devam ediyordu.
- Küçük ve kritik iş aynı belge yükünü taşıyordu; yalnız iki değerli `kucuk` kademesi vardı (ADR-0150).
- Agentic işlerde kanıtın model, prompt sürümü, eval seti ve koşu sayısı kaydı yoktu.
- Dış öneri (EDEL) aşama belgeleri (01/02/03), T/E kimlikleri ve PASS/FAIL/BLOCKED kapıları öneriyordu; ayrı elle yazılan belgeler kaynak kaydı çoğaltacağı için uyarlanarak alındı.

**Karar:**

- **Zincir:** G (mevcut durum gap) → P (plan maddesi, `**Gap:**`, `**Sözleşme:**`) → S (sözleşme başarı kriteri) → T (plan `## Doğrulama planı` satırı) → E (iş klasöründe `kanit.jsonl` kaydı).
- **T satırı:** `- **T1:** S1, S2 — açıklama — Komut: `...``; isteğe bağlı `Eval:`, `Engel: <neden>`, `Kapsam: `glob, glob``. Kapsam verilmezse T'nin S'lerine bağlı P'lerin `**Yazma alanı:**` globları kullanılır. Şablon: `sablonlar/plan_dogrulamali.md`.
- **Kanıt (E):** `orkestra is kanit <iş> T<n>` komutu plandan alır, elle komut verilemez; `plan_dogrulama.komut_yasakli` süzgecinden geçer. Kayıt: komut, çıkış kodu, süre, maskeli çıktı kuyruğu, çıktı sha256, kök, commit, kapsam dosyalarının sha256 imzası, varsa eval alanları.
- **Bayatlık:** kapsam imzası ya da plandaki T komutu E'den sonra değişirse E bayattır; eşleşmeyen glob da imzaya `YOK` olarak girer (dosya sonradan doğarsa bayat).
- **Eval:** komut çıktısındaki `EDEL_EVAL` JSON satırı (kaynak: çıktı) ya da CLI beyanı (kaynak: beyan). Model, prompt sürümü, eval seti ve koşu sayısı zorunlu; asgari koşu `ayarlar/edel.json` `eval_min_kosu`: hafif 1, standart 3, kritik 5.
- **Kademe:** `is ac --kademe hafif|standart|kritik`; kademesiz iş standarttır; eski `kucuk` hafif sayılır ve ADR-0150 davranışı sürer.
- **Üç kapı:** `orkestra is kontrol <iş>` (yan etkisiz). Kapı 1 Başlangıç, kapı 2 Geliştirme, kapı 3 Doğrulama ve yayın. Kademe başına kontrol listesi `ayarlar/edel.json`'dadır; proje ezmesi durum klasöründeki `edel.json`. Karar: eksik varsa FAIL; eksik yok ama engelli T varsa BLOCKED; değilse PASS. Çıkış kodu PASS 0, FAIL 1, BLOCKED 2.
- **Sözleşme sonucu:** sözleşme şablonuna `## Sonuç` bölümü eklendi; kapı 3 her S'nin sözleşme Sonuç bölümünde ya da çalışma özetinde S numarasıyla anılmasını ister.
- **Kapanış:** `is kapat` kapı 3 PASS değilse günlüğe `kapi_golge` (kapi: edel) yazar ve stderr'e tek satır uyarı verir; kapanışı hiçbir koşulda engellemez.
- **Görünümler:** `orkestra is gorunum <iş>` `01-Baslangic.md`, `02-Gelistirme.md`, `03-Dogrulama-ve-Yayin.md` dosyalarını kaynak kayıttan baştan üretir; her dosya "kayıttan üretilmiştir" notu taşır, elle düzenlenmez. Görünüm varsa `is baglanti` yeniler ve bağlantı listesine ekler.
- **Ölçüm:** `muhendislik_kontrol.py olc <durum klasörü>` bütün sıralı işlerde üç kapıyı yazmadan koşar; dağılım, kapanmış işlerde kapı 3, en sık eksik ve tohumlu FAIL/BLOCKED örneklemi verir.

**Seçenekler:**

- Seçilen: kaynak kayıt aynı kalır, zincir onun üstünde okunur; aşama belgeleri üretilmiş görünümdür. Neden: tek kaynak; belge ile kayıt ayrışamaz.
- Elenen: EDEL'in 01/02/03 belgelerini elle yazılan kaynak yapmak. Neden elendi: mevcut durum, plan ve sözleşmeyi ikinci kez yazdırır; ayrışma kaçınılmaz.
- Elenen: kanıtı todo notunda serbest metin bırakmak. Neden elendi: komut, sürüm ve bayatlık yeniden hesaplanamaz.
- Elenen: kapıları doğrudan ihlal modunda açmak. Neden elendi: P-028; mevcut 309 sıralı işin 308'i Doğrulama planı taşımadığı için kapı 1 FAIL verir, ölçüm yeni işlerde alınmalıdır.

**Sonuçlar:**

- Gölge ölçümü (12.11.2026 07:29, `python plugins/orkestra/scripts/muhendislik_kontrol.py olc C:/Mert/McD/.claude/orkestra`): 309 sıralı iş; kapı 1 PASS 1 / FAIL 308; kapı 2 PASS 170 / FAIL 139; kapı 3 PASS 188 / FAIL 121; kapanmış işlerde kapı 3 PASS 185 / FAIL 87; BLOCKED 0 (hiçbir iş `Engel:` taşımıyor).
- Kapı 1'deki 308 FAIL beklenen sonuçtur: `## Doğrulama planı` bu ADR ile gelir, eski işlerde yoktur.
- Yanlış pozitif örneklemi: 10 genel FAIL örneğinde 42 iddia, kapanmış işlerde 10 kapı 3 FAIL örneğinde 10 iddia; düz metin aramasıyla bağımsız sınandı, yanlış pozitif 0/52 (Wilson %95 üst sınır %6,9). Sınama betikleri McD I-447 iş klasöründe `olcum/`.
- Ölçüm sırasında bir yanlış pozitif kaynağı bulundu ve kaynakta düzeltildi: sözleşme şablonunda `## Sonuç` yoktu (52 RNV sözleşmesinin 3'ünde vardı); kontrol artık S'yi Sonuç ya da çalışma özetinde arar, şablon bölümü taşır.
- İhlale geçiş önerisi: eşik (yanlış pozitif ≤ %10) karşılandı. Geçiş kullanıcının kararıdır; ölçüm bu ADR'den sonra açılan işlerde `is kontrol` sonuçlarıyla tekrarlanmalı, kapı başına ayrı ADR yazılmalıdır.
- Mod `golge` (`ayarlar/edel.json`); hiçbir mevcut kapı ya da komut davranışı değişmedi.

**İlgili:**

- İş: I-447 (McD, `RNV/126-20261112-belge-sureci-izlenebilirlik-zinciri-risk`).
- ADR-0150 (küçük kademe), ADR-0086 (gölge kapanış), P-018 (todo kanıt notu), P-028 (gölge önce), P-050 (belge teslim sırası).
- Kod: `plugins/orkestra/scripts/muhendislik_kontrol.py`, `plugins/orkestra/scripts/belge_gorunum.py`, `plugins/orkestra/ayarlar/edel.json`, `plugins/orkestra/scripts/komutlar/isler.py` (`is kontrol`, `is kanit`, `is gorunum`), `plugins/orkestra/scripts/is_sirasi.py` (kademe).
- Testler: `tests/test_edel_kademe.py`, `tests/test_muhendislik_kontrol.py`, `tests/test_belge_gorunum.py`.
