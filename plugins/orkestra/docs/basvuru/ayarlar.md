<!-- Bu dosya scripts/dokuman_uret.py ile üretilir; elle düzenleme. -->

# Ayarlar ve kapılar

Kaynak: `ayarlar/*.json`. Proje ezmesi: `.claude/orkestra/<ad>.json`. `mod`: `golge` (uyarır, engellemez), `ihlal` (reddeder), `kapali`.

Toplam 100 ayar; `açıklama yok` işaretli: 33.

| Ayar | Mod | Açıklama |
|---|---|---|
| `ajan_kapsam` | ihlal | Ajan türüne göre araç kapsamı (I-292 P3, ADR-0120). |
| `arka_plan_yas` | — | ADR-0123 (G3): Stop arka plan satırına yaş eki. |
| `arsiv_dugmesi` | ihlal | açıklama yok |
| `arsiv_surec_kapat` | golge | mod: ihlal = arşivli oturumun `--resume` kimliğiyle eşleşen claude.exe süreç ağacı bakım turunda kapatılır; golge = yalnız kapi_golge kaydı (P-028: ihlal geçişi >=7 gün gölge, yanlış eşleşme 0 ölçümünden sonra ayrı kara… |
| `auto_devam` | golge | mod: golge = /auto işi açıkken ve çalışma özeti yokken tur biterse gunluk.jsonl'a kapi_golge olarak düşer, tur engellenmez; ihlal = tur başına bir kez devam hatırlatmasıyla block. |
| `auto_karar_alan` | golge | mod: golge = auto işin çalışma özetinde `## Otomatik kararlar` girdilerinde karar, gerekçe, alternatifler ya da geri alma alanı eksikse uyarılır ve gunluk.jsonl'a kapi_golge olarak düşer, is kapat engellenmez; ihlal = a… |
| `auto_kararlar` | ihlal | mod: golge = auto modundaki işin çalışma özetinde `## Otomatik kararlar` bölümü yok ya da boşsa uyarılır ve gunluk.jsonl'a kapi_golge olarak düşer, is kapat engellenmez; ihlal = bölüm olmadan özet doldurulmuş sayılmaz. |
| `bagsiz_kabuk` | ihlal | mod: ihlal = bağsız oturumda geçici dizin dışına dosya yazan kabuk komutu reddedilir ve gunluk.jsonl'a kapi_ret düşer; golge = yalnız kapi_golge kaydı, iş engellenmez. |
| `bagsiz_otomatik_bagla` | golge | mod: ihlal = bağsız oturumda yazılan yol tek net açık işle örtüşüyorsa oturum o işe bağlanır ve yazım reddedilmez; golge = yalnız kapi_golge kaydı, ret sürer (P-028: ihlal geçişi ölçümden sonra ayrı kararla). |
| `bash_sozdizimi` | golge | açıklama yok |
| `bekleme_kapisi` | golge | açıklama yok |
| `belge_bicim` | — | açıklama yok |
| `belge_duzelt` | acik | açıklama yok |
| `bellek_kapisi` | golge | Açılışta bellek uyarısı (I-397, ADR-0155, P-028). |
| `best_in_class` | ihlal | P-030 best in class kapısı. |
| `bolme_kapisi` | golge | Bölme kapısı (I-297 P5, ADR-0114). |
| `bosta` | golge | Bekleme anı aday listesi (ADR-0158, I-376). |
| `cikti_butce` | golge | Kullanıcıya giden sohbet çıktısı bütçesi (P-001, ADR-0075). |
| `cikti_butce_deney` | golge | Çıktı bütçesi geri bildirim deneyi (I-319 P6; rapor 149 §4). |
| `cikti_sirasi` | block | Karar sırası kapısı (ADR-0135, I-321, P-001/P-029 tamamlayıcısı): karar bekleyen bölüm yanıtın son bölümü olmalı. |
| `dal_temizle` | ihlal | Tek main için artık dal temizliği (I-201, ADR-0050). |
| `db_olcum` | — | db-olcum skill varsayılanları. |
| `denetim_politikasi` | golge | açıklama yok |
| `devir_esigi` | ipucu | I-271: ana ajanın tek turunda (Stop'tan Stop'a) önbellek okuması esik_onbellek_okuma token'ı aşarsa sonraki kullanıcı mesajında tek satırlık devir ipucu bağlama eklenir; engellemez. |
| `devir_hatirlatma` | hatirlat | açıklama yok |
| `dis_skill_kaynaklari` | — | açıklama yok |
| `durum_satiri` | acik | mod: acik = iş bağlıyken SessionStart ve UserPromptSubmit bağlamına tek satırlık durum özeti (iş kimliği, onay durumu, sıradaki belge/adım; en çok 200 karakter) eklenir; kapali = eklenmez. |
| `etkilenen_karar` | golge | P-056 etkilenen karar yoklaması. |
| `genis_tarama_hatirlatma` | reddet | açıklama yok |
| `gorev_alt_turleri` | — | Paket GOREV_ROUTING_56.json (07.11.2026) 56 alt tür önerisi; benchmark edilmedi, yalnız gölge karşılaştırmada kullanılır (I-419). |
| `gorev_turleri` | ihlal | Görev türü kataloğu (v2 ataması, ADR-0092). |
| `gorunum_olcumu` | golge | mod: golge = görünen yerleşim/konum değiştiren P maddesinin Kabul alanı tarayıcı ölçümü içermiyorsa uyarılır ve gunluk.jsonl'a kapi_golge düşer, iş engellenmez; ihlal = plan reddedilir. |
| `hafiza_duzeltme` | ihlal | açıklama yok |
| `harita_etki` | golge | ADR-0118 etki kapısı: isteğin konu kartlarına eşlenen yüzeyleri plan maddelerinin `**Etki:**` alanında anılmalı. |
| `harita_iliski` | — | Proje bilgi grafiği şeması (ADR-0118, I-296). |
| `hata_onleme_siniflari` | — | ADR-0151 P4: tekrar eden hata imzası → önleme basamağı (standartlar/onleme_merdiveni.md L0-L6) ve sahip (sorunun doğduğu kaynak). |
| `hedef` | — | açıklama yok |
| `iddia_dogrula` | — | iddia-dogrula skill varsayılanları. |
| `iddia_kaynak` | golge | açıklama yok |
| `is_baglama` | etkin | açıklama yok |
| `is_esleme` | — | açıklama yok |
| `istek_defteri` | golge | ADR-0112 istek defteri kapısı. |
| `iz_kapsama` | — | açıklama yok |
| `izin_politikasi` | genis | genis: kapı dışındaki her araç çağrısı onaysız (hook allow; kullanıcının settings deny/ask kuralları yine geçerli). |
| `jira_bagimlilik` | ihlal | Jira görev bağımlılığı girdi kapısı (ADR-0086). |
| `kabuk_profili` | etkin | ADR-0102, P-043: kullanıcıya verilen komut kullanıcı kabuğunun sözdizimiyle yazılır. |
| `kanit_rubrik` | — | açıklama yok |
| `kanitsiz_iddia` | golge | açıklama yok |
| `kapanis_birlestirme` | ihlal | Kapanışta güvenli birleştirme ve biten worktree temizliği (I-225, ADR-0086). |
| `kapanis_surec` | golge | ADR-0163 (I-387, P-014, P-045): kullanıcıya giden son mesajda ajanın kendi iç sürecini anlatan cümleler günlüğe kural_ihlal / kapanis_surec düşer. |
| `karar_kapisi` | ihlal | ADR-0112 açık karar kapısı. |
| `kart_kontrol` | ihlal | Kart açılışında her kabul kriteri ölçülebilir 'kontrol:' alanı taşır (komut, dosya:satır ya da sayı) ve ölçüsüz ifade içermez. |
| `kart_soru` | — | açıklama yok |
| `kaynak_kira` | ihlal | Makine genelinde test koşusu kirası ve ortak işçi bütçesi (I-309 P4, scripts/kaynak_kira.py). |
| `kimlik_hatirlatma` | block | açıklama yok |
| `kok_neden_enjeksiyonu` | etkin | ADR-0101, P-042: sorun/hata anında kök neden önce, çözüm ilk denemede kalıcı. |
| `konu_defteri` | golge | ADR-0116 sohbet konu defteri. |
| `konu_kaymasi` | etkin | Kayma sınıflayıcısı (I-297 P4, ADR-0114). |
| `kpi_esikleri` | — | açıklama yok |
| `kucuk_kademe` | golge | Küçük iş kademesi (ADR-0150, I-353). |
| `kuyruk` | golge | mod: golge = oturum teslimi kuyruğa verilmeden (orkestra teslim kuyruk ekle) tam paket koşulduysa ya da kuyruk eksiği varsa uyarılır ve gunluk.jsonl'a kapi_golge olarak düşer, iş engellenmez; ihlal = eksik varsa reddedi… |
| `main_kopya_kapisi` | golge | Korunan deponun birincil main kopyasına Edit/Write (I-302, ADR-0122). |
| `mcp_kimlik` | — | MCP kimlik kaydı (ADR-0096, ADR-0097). |
| `model_politikasi` | — | açıklama yok |
| `niyet_defteri` | golge | ADR-0156 niyet defteri kapısı. |
| `olay_esleme` | — | açıklama yok |
| `olay_kategorileri` | — | açıklama yok |
| `olay_kaydi` | golge | açıklama yok |
| `on_baglam` | — | açıklama yok |
| `on_kontrol` | — | açıklama yok |
| `onbellek_buda` | — | orkestra guncelle sonrası eklenti önbelleği budaması (I-271 P8). |
| `onleme_yanit` | golge | ADR-0123 (G4, P-045): düzeltme önerisi sonradan yakalayan ya da alışkanlığa bağlı çözümse ve yanıtta önleme merdiveni akıl yürütmesi yoksa günlüğe kural_ihlal / onleme_basamagi düşer. |
| `ortam` | golge | açıklama yok |
| `oturum_farkindalik` | ihlal | Oturumlar arası çakışma farkındalığı (ADR-0125, ADR-0127, I-308). |
| `ozet_baslik` | ihlal | mod: golge = çalışma özeti başlığı yalnız Jira kodu ya da genel ise uyarılır ve gunluk.jsonl'a kapi_golge olarak düşer, is kapat engellenmez; ihlal = başlık tamam olmadan özet doldurulmuş sayılmaz. |
| `paralel_kosu` | — | Paralel koşu (P-041, ADR-0100). |
| `paralellik` | ihlal | Plan paralellik kapısı (ADR-0080). |
| `paralellik_kapanis` | ihlal | ADR-0080 kapanış paralellik kapısı (S6a/S6b, K6-K8). |
| `perspektif_zaman` | — | açıklama yok |
| `plan_dogrulama` | ihlal | mod: golge = todo yazımı engellenmez, uyarı verilir ve gunluk.jsonl'a düşer; ihlal = engelli P<n> için todo yazımı reddedilir. |
| `postgres_mcp` | — | postgres-mcp sarmalayıcısı (scripts/postgres_mcp.py) varsayılanları. |
| `refleks` | acik | Refleks katmanı (ADR-0149): '/ok <komut>' modelsiz çalışır. |
| `secim_ekrani_hatirlatma` | block | açıklama yok |
| `sef_ozeti` | ihlal | İki katmanlı Şef Özeti kapısı (ADR-0085, ADR-0091). |
| `sir_kaliplari` | — | açıklama yok |
| `skill_surekli` | — | ADR-0119: her projede oturum açılışında gövdesi bağlama yüklenen (sürekli açık) eklenti skill adları. |
| `soru_sinif` | — | açıklama yok |
| `sozlesme` | ihlal | mod: golge = sözleşme eksiği uyarılır ve gunluk.jsonl'a kapi_golge olarak düşer, plan/todo yazımı engellenmez; ihlal = sözleşme tamam olmadan plan ve todo yazılamaz. |
| `taban_oranlari` | — | açıklama yok |
| `teknoloji_kategorileri` | — | açıklama yok |
| `teslim` | ihlal | mod: golge = teslim eksiği (PR, CI, inceleme) uyarılır ve gunluk.jsonl'a kapi_golge olarak düşer, is kapat engellenmez; ihlal = eksik varsa is kapat reddedilir. |
| `test_yonlendirme` | ihlal | Çıplak tam test koşusu yönlendirmesi (I-309 P6, scripts/hook.py _test_yonlendirme, PreToolUse Bash). |
| `uretim_enjeksiyonu` | etkin | ADR-0111, P-045: Write/Edit hedefi bir belge türüne denkse ilgili kapı kuralı yazım anında kısa bağlam olarak eklenir (merdiven L4). |
| `uretim_noktasi` | ihlal | K-006 üretim noktası kapısı (ADR-0069). |
| `uretim_olcum` | — | ADR-0111 etki ölçümü. |
| `yapamam_kaniti` | golge | ADR-0153 (P-045): yanıtta gerçek yapamama iddiası denenen komut ya da engel kanıtı olmadan yazılmışsa günlüğe kapi_golge / yapamam_kaniti düşer. |
| `yetki` | — | Yeni işlerin ve iş bağlanmamış oturumların varsayılan çalışma modu: plan \| auto. |
| `yol_karari` | golge | mod: golge = yeni sıralı işin mevcut durumunda `## Yol kararı` (giriş noktasından dallanmalar dosya:satır, gerçek trafik ölçümü ya da ölçülemedi + kapatan plan maddesi, karar) yoksa ya da eksikse plan öncesi uyarılır ve… |
| `yontem_enjeksiyonu` | etkin | ADR-0068: best in class yöntemi (standartlar/best_in_class.md '## Üretim anı' bölümü) iş mesajlarında ana ajana, kartlı işçilerde SubagentStart'ta bağlama eklenir. |
| `zaman_etkin` | — | I-257/I-259: ana tur süresi (zaman.jsonl tur=ana sure_ms) bu eşiği (dakika) aşarsa kullanıcı beklemesi sayılır ve etkin_ms 0 yazılır; eşiğin altındaki turda etkin_ms = sure_ms. |
