# Eklenti geliştirme notları

Bu dosya eklentiyi geliştirenler içindir. Kullanım kuralları için `KURALLAR.md` dosyasına bak.

## Yayın akışı
Oturumlar eklentiyi `~/.claude/plugins/cache/claude-orchestration/<plugin>/<sürüm>/` altındaki önbellek kopyasından yükler (göreli yol girdisine rağmen). Sürüm commit SHA'sıdır (12 hane); `version` alanı bilerek yoktur.

1. Eklenti deposunda geliştir.
2. Değişikliği kendi dalında commitle; `main`'e yalnız `--ff-only` ya da PR ile gir (aşağıda "Yan işler").
3. Uzak `main`'e push et (yalnız kullanıcının açık isteğiyle). Git hook'u yoktur; hiçbir betik yayın klonuna yazmaz.
4. `orkestra guncelle` çalıştır: yayın klonu GitHub `origin`'den çekilir (klon kirliyse reddeder). Çalıştırmazsan `autoUpdate` ilk mesajdan en çok 10 dk sonra alır.
5. Sonraki oturumda ya da `/reload-plugins` ile yeni sürüm yüklenir.

Notlar:
- Güncelleme commit'i değil, marketplace klasörünün çalışma ağacını kopyalar. Bu yüzden marketplace, GitHub deposunun temiz git klonudur (yayın klonu; `python araclar/yayin_kur.py` kurar, `origin` GitHub adresidir). Yayın klonunu elle düzenleme.
- Push edilmemiş iş (commitli olsa bile) yayına girmez.
- SessionStart bayatlık uyarısı önbellek kopyası ile yayın klonu arasındaki farkı bildirir.
- `validate --strict` sürüm alanı olmadığı için hep "No version specified" ile düşer (bilinçli).
- `orkestra` CLI'ı da önbellekten çalışır. HTML paneli geliştirme deposu yolundan `python <depo>/plugins/orkestra/scripts/orkestra.py panel` ile başlat.

## Yan işler
- Her iş kendi dalında ve `git worktree` ile ayrı klasörde yürür (`git worktree add ../co-wt/<iş> -b <dal> main`). Desktop kökü `main` çalışma ağacıdır; yeni özellik orada başlatılmaz.
- `main`'e yalnız `git merge --ff-only <dal>` ya da PR ile girilir; ayrışmış dal önce `main` üzerine alınır.
- Dal ve worktree iş bitince (ve başka oturum kullanmıyorsa) kaldırılır: `git worktree remove` + `git branch -d`.
- Yayın akışı ("Yayın akışı" bölümü) yalnız `main` içindir; yan dal push edilse bile marketplace'e girmez.

## Panelde güncelleme bildirimi (ADR-0039)
Panel Gelen kutusu, `origin/main` SHA'sı kurulu SHA'dan farklıysa ve aralıkta konusu `Yenilik:` ile başlayan en az bir commit varsa "Orkestra güncellemesi var" kartı gösterir (Güncelle, Sonra, Neler değişti); kartta yalnız bu commit'ler listelenir. Yeni özellik içeren yayın commit'ine `Yenilik: <ne eklendi>` konusu verilir, aksi halde kart çıkmaz.
- Kontrol `guncelle.kontrol()`: `git fetch` + `origin/main` karşılaştırması; ağ hatası kartı silmez. Koşu `guncelle.Kosu`: CLI ile aynı `calistir`, arka plan iş parçacığı, tek koşu.
- `panel_guncelleme.Guncelleme`: panel açılışında ve sonra 30 dk'da bir yoklar (`ORKESTRA_GUNCELLEME_YOKLA=0` kapatır), "Sonra" SHA'sını `guncelleme_ertele.json`'a yazar.
- Uçlar `GET /api/guncelleme`, `POST /api/guncelle`, `POST /api/guncelle-ertele`: çalışma alanı almaz, `alan=*` reddinden muaftır (`KULLANICI_YOLLARI`).
- Panel kendini yenilemez: güncelleme yeni oturumda ya da `/reload-plugins` ile yüklenir. Çalışan panel sunucusu eski kodla sürer; `app.js`/`panel.py` değişince `SURUM` artırılır.
- Önizleme: panel testi `tests/test_panel_guncelleme*.py`; görsel doğrulama için `panel.GUNCELLEME` sahte nesneyle değiştirilip `panel.calistir` çağrılabilir.

## Paylaşılan git indeksi tuzağı
Aynı depoda birden çok oturum aynı indeksi kullanır. Başka oturumun commit'i senin sahnelediğin dosyaları da alır. Bu yüzden commit'i ana indeksle değil, geçici `GIT_INDEX_FILE` ile kur.

Adımlar:
1. Güncel HEAD'i al: `OLD=$(git rev-parse HEAD)`.
2. Geçici indeks tanımla: `export GIT_INDEX_FILE=$(mktemp -u)`.
3. Ağacı oku: `git read-tree $OLD`. `read-tree` ile `commit-tree` arasında HEAD değişmemeli; değiştiyse baştan başla.
4. Yalnız kendi dosyalarını ekle: `git add <dosyalar>` (geçici indekse işler; ana indekse dokunmaz).
5. Ağacı yaz: `TREE=$(git write-tree)`.
6. Commit nesnesini oluştur: `NEW=$(git commit-tree $TREE -p $OLD -m "<mesaj>")`.
7. Dalı ilerlet: `git update-ref refs/heads/main $NEW $OLD`.
8. Geçici indeksi kaldır: `unset GIT_INDEX_FILE`, ardından geçici dosyayı sil.
9. Doğrula: `git diff --stat $OLD $NEW` çıktısında yalnız kendi dosyaların olmalı.
10. Ana indeksi eşitle: `git reset -q HEAD -- <yollar>`. Yapmazsan sonraki commit işini geri alır.

## Oturum worktree'si ve durum kaynağı (ADR-0033)
Claude uygulaması oturum başına bir git worktree açar (`<proje>/.claude/worktrees/<ad>-<hex>`, dal `claude/<ad>-<hex>`) ve git dışı `.claude/orkestra` klasörünü ona kopyalar. Durum tek kaynaktan çözülür:
- `ork_lib.proje_dizini`: cwd (ya da `CLAUDE_PROJECT_DIR`) bir worktree ise (`.git` bir DOSYA) ve ana ağaçta `.claude/orkestra` varsa ana ağaç kökünü döndürür. Hook, `orkestra` komutu ve panel aynı kaydı görür. `ORKESTRA_DURUM_YEREL=1` yerel kopyayı seçer (testler ve kaçış kapısı). Belgeler (`Claude_Orkestrasyon/NNN-…`, `adr/`) git izli olduğu için worktree dalında kalır.
- Numara: `is_kaydi.sonraki_klasor_adi` ve `klasor_ayir` `git worktree list` ağaçlarındaki NNN'leri de sayar. ADR numarasının ağaçlar arası tekilliği kodla sağlanmadı: yeni ADR'de ana klasörün `adr/` dizinindeki en büyük numaraya bak.
- Eski kopyalar: `orkestra durum devral` (kuru koşu) ve `--uygula` hedefte olmayan jsonl satırı, iş, onay ve görev dosyalarını ana duruma ekler; yedek `yedek/devral_<zaman>/`, kaynakta `.devralindi` damgası, kaynak silinmez, kimlik çakışması yazılmaz raporlanır. `--tum` deponun bütün ağaçlarını tarar.
- `orkestra kart agac-temizle`: `claude/<ad>-<hex>` ağaçları `oturum` sınıfında listelenir, kaldırılmaz; devralınmamış kayıt varsa uyarır. `todo-denetle` ana ağaçla aynı ya da devralınmış worktree todo kopyasını bayat saymaz.
- Bilinen sınır: iki ağaçta aynı anda açılan iki iş aynı NNN'yi alabilir (klasör diske yazılmadan önceki pencere). Testler: `tests/test_oturum_agaci_durum.py`, `tests/test_durum_devral.py`.

## Kural katmanları (kod)
- Kütüphane `scripts/onay.py` (kurallar bölümü), CLI `scripts/komutlar/onay.py` (`kural ...`), panel `assets/kurallar.js` + `panel.py` `_onay_islemi`. Kullanım ve öncelik: `KURALLAR.md` "Kural katmanları".
- Eklenti katmanının deposu `kurallar/eklenti_kurallari.json`. `onay.eklenti_kural_yolu()` yolu çözer: önbellekten (`plugins/cache`) çalışırken yazım önbelleğe değil kaynak depoya (`known_marketplaces.json` installLocation) gider, çünkü önbellek güncellemede silinir. Eklenti kuralı eklemek eklenti kodunu değiştirmektir: commit, `orkestra guncelle`, yayın akışı bu dosyadaki gibi işler.
- Yazımda `KURALLAR.md`'deki işaretçili blok (`<!-- eklenti-kurallari:basla/bitis -->`) yeniden üretilir; elle düzenlenmez. Proje kural dosyası SessionStart'ta `onay.kural_dosyasi_esitle` ile yenilenir (içerik aynıysa yazmaz).
- Testler gerçek eklenti deposunu görmesin diye `tests/conftest.py` ve `tests/ic_kos.py` `ORKESTRA_EKLENTI_KURALLARI`'nı var olmayan bir geçici yola çevirir. Eklenti katmanını sınayan test bu değişkeni kendi geçici dosyasına ayarlar (`tests/test_kural_katman.py`).
- Yeni bir kural katmanı alanı eklenirse `kural_gorunum`, `kurallar` ve `_kural_dosya_metni` üçü birlikte güncellenir.
- Terfi kapısı: `scripts/onay.py` içinde `yayin_ayristir` (Yayın: etiketi), `terfi_denetle` (isabet listesi) ve `_terfi_kapisi` (isabette ValueError).
- Yasak terimler proje durum dizinindeki `terfi_yasak.json` dosyasından okunur (liste ya da `{"terimler": [...]}`); dosya yoksa yalnız kalıp denetimi çalışır.
- Testler: `tests/test_terfi.py`.

## Hafıza düzeltme kapısı ve rapor kanıt doğrulaması
- Kural P-026, P-021'in rapor ayağı; karar kaydı McD deposunda ADR-0029'dur (eklentiyi kuran başka bir kullanıcıda bulunmaz, kural metni kendi başına anlaşılır).
- Çekirdek `scripts/hafiza_duzeltme.py`: düzeltme notu = parantezli ya da köşeli (`[[bağlantı]]` hariç) bölüm, `ayarlar/hafiza_duzeltme.json` `isaret_kokleri` kökünden birini taşır ve `min_uzunluk` karakterden uzundur. Aynı normalize not hafıza klasöründe `esik` (2) ya da daha çok dosyada geçerse `tara`/`tekrarlar` bulgu verir.
- Yazım kapısı `scripts/hook.py` `_hafiza_duzeltme_kapisi` (PreToolUse, Write/Edit/MultiEdit; yol `hafiza_yolu` kalıbına uyan md): yazımdan sonraki metin hesaplanır, notun toplam sayımı eşiğe ulaşıp artıyorsa `reddet`. Hata olursa açık geçer (fail-open). Mod `ayarlar/hafiza_duzeltme.json` `mod`: `ihlal` (reddet, varsayılan), `golge` (yalnız uyarı), `kapali`; `ORKESTRA_HAFIZA_DUZELTME=0` hepsini kapatır.
- Rapor ayağı `scripts/perspektif.py`: `girdi.json` `duzeltme_tekrari` alanı, `rapor_dogrula`/`rapor_isaretle` (`Kanıt:` satırları `plan_dogrulama.kanit_dogrula` ile, `kos=False`: komut koşulmaz; tutmayan satırın altına `ISARET` yazılır, idempotent), `kaydet` işaretlemeyi kendisi yapar. CLI: `orkestra perspektif dogrula <rapor>` (tutmayanda çıkış 1) ve `duzeltme-tara [klasör]` (bulguda çıkış 1).
- Talimatın tek kaynağı `agents/perspektif-ajani.md`'dir (ADR-0094). Başsız koşu istemi çalışma anında `scripts/perspektif_talimat.py` `uret(hafiza, proje, sd)` ile türetilir (`perspektif.istem`; `perspektif.ISTEM` geriye uyumlu `str.format` şablonu): ön madde ve "Akış" atılır, "Rapor bölümleri" (§9, §10 dahil), "Doğrulama (P-021)", "Vaat satırı", "Yayın satırı", "Kurallar" birebir alınır. Talimat yalnız md'de değiştirilir; `tests/test_perspektif_talimat.py` türetmeyi bağlar.
- `girdi.json` ölçüm modülleri (LLM'siz, salt okuma): `perspektif_zaman.ozet` → `zaman` (ana/alt tur, oturum, iş süresi; K8-K10 anomali, eşikler `ayarlar/perspektif_zaman.json`), `perspektif_gunluk.ozet` → `gunluk` içine kapı gölge/ret, ret nedenleri, kural ihlali, çıktı ölçümü, hook hatası, kullanılmayan skill, `yukseltilen_kart`, `denetim_payi` (ayrıca üst düzey `hata`, `atif`), `perspektif_trend.hesapla` → `trend` (bu 14 gün / önceki 14 gün; kpi, anomali, zaman, gunluk). Zaman damgası `uretim_zamani` anahtarındadır. İmza K8-K10 anomali kümesini de taşır. 64 KB tavanı `perspektif._kisalt`: en uzun liste yarıya iner, sayımlar korunur, `_kisaltma` özgün uzunlukları yazar.
- Otomatik koşu kapalıyken (`ORKESTRA_PERSPEKTIF_OTO` yok) eşik dolunca `hook.session_start` bağlama `perspektif.zaman_uyarisi` satırını koyar ("perspektif zamanı geldi (N oturum / M gün)"); `yoksay` ve okunmamış rapor susturur.
- Başsız perspektif koşusunda yalnız Read/Glob/Grep vardır (Bash yok); `dogrula` orada koşmaz, `kaydet` doğrulamayı yapar.
- Doğrulanmadı: Claude Code'un yerleşik otomatik hafıza yazımının PreToolUse hook'undan geçip geçmediği; geçmiyorsa kapı yalnız ajan yazımlarını tutar, `duzeltme-tara` ve bakımcı ilkesi geri kalanı karşılar.
- Testler: `tests/test_hafiza_duzeltme.py`, `tests/test_hook_hafiza_duzeltme.py`, `tests/test_perspektif_dogrulama.py`, `tests/test_perspektif_talimat.py`, `tests/test_perspektif_girdi.py`, `tests/test_perspektif_zaman.py`, `tests/test_perspektif_gunluk.py`, `tests/test_perspektif_trend.py`.

## Sistem haritası: teknolojiler katmanı
- `scripts/harita.py` dokuzuncu katman `teknolojiler`i taşır; tarama ve md üretimi `scripts/harita_teknoloji.py`'dedir (ADR-0019, kural P-024).
- Kategori eşlemesi `ayarlar/teknoloji_kategorileri.json`: önce tam ad, sonra en uzun önek; eşleşmeyen `diger`. Yeni paket buraya eklenir, koda dokunulmaz. Dosya imzaya girer: değişince katman eskir.
- Çıktı `<durum>/sistem_haritasi/teknolojiler/`: `README.md` (kategoriye göre) ve proje başına md. Her yenilemede klasördeki md'ler silinip yeniden yazılır (elle düzenleme kalmaz).
- Proje = en yakın manifest dizini; `.git` dosyası olan dizin (çalışma ağacı) ve manifestsiz klasör proje sayılmaz. Kapsamı genişletmek (içe aktarma taraması) ayrı karar ister.
- Testler: `tests/test_harita_teknolojiler.py`.

## Hata defteri (McD ADR-0035, iş I-184)
- `scripts/hata_kayit.py`: `kaydet()` hook (`hook.py _hata_yaz`), CLI (`komutlar/_ortak.py hata()`, çıkış kodu 2 hariç) ve özet (`ozet.py`) hatalarını `<durum>/hata.jsonl`e imzalı satır olarak yazar; yazılamazsa stderr'e tek satır, çağıran düşmez. `imza()` sayı, tam yol, `.tmp_` adı ve onaltılık kimliği çıkarır.
- `scripts/hata_en_cok.py` + `orkestra hata en-cok|liste [--gun N] [--kaynak K | --tum] [--ilk N] [--json]`: hata.jsonl, `gunluk.jsonl` `hook-hatasi` (karşılığı hata.jsonl'de olmayanlar) ve kart retleri okuma anında birleştirilir; kopya yoktur. Kural ihlalleri varsayılanda dışarıdadır (`--kaynak kural` ya da `--tum`).
- Oturum başı uyarısı: `hook.py _ss_uyarilar` son 7 günde aynı imzadan 3 ve üzeri varsa tek `HATA:` satırı yazar; kural kaynağı sayılmaz.
- Testler: `tests/test_hata_kayit.py`, `tests/test_hata_en_cok.py`.

## Test takımı
- Tam paket: `python plugins/orkestra/scripts/test_paralel.py` (paralel koşar; yaklaşık 4 dk).
- Değişiklikten sonra commit'ten önce koş.
- CLI çağrıları süreç içinde koşar: test yardımcıları (`test_cekirdek.kos`, `test_test_kapisi.kos` vb.) `tests/ic_kos.py` üzerinden `orkestra.py`/`hook.py` `main()`'ini aynı argv, cwd, ortam ve stdin ile çağırır. Alt süreç başına ~0,5 sn gidiyordu; en yavaş dosyalar 5-10 kat hızlandı (15.10). Ev dizinini değiştiren testlerde içe aktarımda hesaplanan ev yolları (GENEL_DIZIN türevleri) çağrı süresince yeni eve çevrilir.
- Gerçek alt süreçle uçtan uca doğrulama: `ORKESTRA_IC_KOS=0` ile koş (yayın öncesi ya da süreç içi farkından şüphelenince).
- Yeni testte CLI'yi `subprocess.run` ile değil `ic_kos.kos([CLI, ...], cwd=..., env=...)` ile çağır; uçtan uca kalması gereken (hook betiği, git, node) çağrılar alt süreçte kalır.

## Panel sayfa yapısı ve test sunucusu
- Sayfalar: `/` Şimdi, `/maliyet`, `/verim`, `/onaylar`, `/kurallar`, `/isler`, `/etki`, `/yapilacaklar` (`/analitik` `/verim`'e yönlendirir). Yollar `scripts/panel.py` içindeki `SAYFALAR` sözlüğündedir.
- Dosya yapısı (`assets/`): her sayfa kendi `<sayfa>.html` dosyasını ve betiğini `<sayfa>.js` olarak taşır; büyük sayfaların stili `<sayfa>.css` içindedir. Ortak kabuk `ortak.css` ve `ortak.js`'tir. `ortak.js` global `window.O` nesnesini kurar ve yerleştirme yardımcılarını tanımlar: `O.yerlestir`, `O.ciz`, `O.bayatCiz`. Sayfa betikleri (ör. `isler.js`, `etki.js`) `O.yerlestir` kullanır.
- Sunulan dosyalar `scripts/panel.py` içindeki `STATIK` sözlüğüyle belirlenir (satır 70). `ortak.css`, `ortak.js` ve `logo.png` elle girilir; `SAYFA_JS` (satır 74: 8 sayfa betiği) ve `SAYFA_CSS` (satır 75: simdi, isler, maliyet, verim, etki) listelerinden `/<sayfa>.js` ve `/<sayfa>.css` girişleri üretilir (satır 76–77). Yeni bir sayfa dosyası için iki liste de güncellenir; `STATIK`te girişi olmayan dosya sunulmaz (satır 496).
- Sayfa/sunucu sözleşmesi `SURUM = "13"` (satır 80). Değişince sağlık yanıtı (`ok <sürüm>`, satır 616) eşleşmez ve eski sunucu yeniden başlatılır.
- Test sunucusu: `python plugins/orkestra/scripts/panel.py _kos <port> --test` panel.json dosyasını **yazmaz** (satır 641–644; G-096). Gerçek panelin durum dosyası `~/.claude/orkestra-panel/panel.json` yerinde kalır. Bayraksız `_kos <port>` bu dosyanın üzerine yazar; testte bayrağı kullan.
- POST `/ac` gerçek ya da uydurma oturum kimliğiyle denenmez; masaüstü süreci başlatır.

## MCP kimliği (ADR-0096)
- Sarmalayıcı `scripts/mcp_kimlik.py <ad>`; kayıt `ayarlar/mcp_kimlik.json` (proje ezmesi `.claude/orkestra/mcp_kimlik.json`). Kayıtta değer yok, yalnız `ORTAM_DEGISKENI: kimlik anahtarı adı`; şema bilinmeyen alanı ve ad dışı değeri reddeder.
- Sarmalayıcı değeri yalnız MCP alt sürecinin ortamına koyar ve stdio'yu aktarır (`orkestra kimlik calistir` çıktıyı topladığı için stdio MCP'ye uymaz).
- Komutlar: `orkestra mcp liste|config|kur` (`scripts/komutlar/mcp.py`). Yeni MCP = kayıta bir girdi; kod gerekmez. Testler: `tests/test_mcp_kimlik.py`, `tests/test_mcp_komut.py`.
- Şema genişlemesi (ADR-0097): `ortam` değeri `ANAHTAR` ya da `servis.ANAHTAR`; `gerek` = ön koşul komut adları (`liste` gösterir, `kur --hepsi` atlar); `komut` içinde yalnız `${CLAUDE_PROJECT_DIR}` açılır (tanımsızsa hata, başka `${...}` reddedilir).

## İzin politikası (hook)
- Karar mantığı `scripts/izin_politikasi.py`, desenler `ayarlar/izin_politikasi.json`; hook'a bağlantı `hook.py` içinde `_izin_karari` / `_kapi_uygula` / `gec()` (varsayılan allow). Eşleşme `hooks/hooks.json` PreToolUse `matcher`ındadır: yeni bir araç ailesi kapıya girecekse eşleşmeye de ekle (`orkestra doktor` MCP kapsamını denetler).
- Karar sırası: kilitli test `deny` > yasak `deny` > kapı `ask` > `orkestra` CLI `allow` > geniş `allow`. Kabukta kapı, kilitli test denetiminden sonra uygulanır (kilidi onayla aşamasın).
- Testler: `tests/test_izin_politikasi.py`. `tests/conftest.py` `ORKESTRA_IZIN=0` verir (eski hook testleri kapı kararlarını boş çıktıyla sınar); izin testleri modu kendileri seçer.

## PostToolUse hook'ları
- `hook.py` `post_tool_use`: Skill, Agent, Task ve Workflow çağrılarını `gunluk.jsonl`'a yazar. `mcp__ccd_session__start_session` sonrasında K-007 detach hatırlatmasını (`detach_hatirlatmasi`) ek bağlam olarak verir. Test: `tests/test_hook_detach.py`.
- `scripts/oto_commit.py`: ayrı girdidir (`Edit|Write|MultiEdit|NotebookEdit|Bash|PowerShell`). Her düzenlemede çalıştığı için `hook.py`'yi yüklemez. `ORKESTRA_OTO_COMMIT` boş ya da `0` ise kabuk satırı Python'u hiç başlatmaz. Test: `tests/test_oto_commit.py`.
  - Kabuk komutlarında yalnız `ORKESTRA_OTO_COMMIT_BASH_YOLLAR` (virgülle ayrılmış klasör önekleri) altındaki `.md/.json` dosyaları commit edilir; ayar yoksa kabuk commit etmez.
  - `orkestra is|plan` komutlarından sonra `orkestra.py main()` ayarsız olarak `oto_commit.cli_sonrasi` çağırır: komutun çalıştığı depodaki iş klasörlerinin `.md/.json` belgeleri commit edilir (ADR-0034). Ortak işlev `klasorleri_commit`.

## Denetim dersleri
Orkestranın kendi kartları denetlenirken tekrar eden kusurlar. Denetçi ve işçi bu yollara önce bakar.

**Test çıktısı ayrıştırıcıları gerçek çıktıyla sınanır.**

Test kapısı ve ön kontrol ayrıştırıcıları el yazımı sahte çıktıyla geçti, gerçek pytest çıktısında delindi. Gözden kaçan biçimler:
- `SUBFAILED(i=..)` satırları
- traceback içinde geçen "during collection" metni
- tek test kimliğine düşen çok satır (subTest döngüsü, FAILED ile teardown ERROR)
- `-rN`

Sınama: geçici klasörde küçük gerçek test dosyaları kur. Bunları `pytest -q` ile ve `-q`'suz, `-rN`, `-x` ve `--continue-on-collection-errors` ile koş. Çıktıyı ayrıştırıcıya doğrudan ver, sayıları özet satırıyla kıyasla.

**Birleştirmede özellikler birbirinin bağlamında sınanır.**

"Çatışma yok, semboller var, tam takım geçer" yetmez. Bir özellik yolları proje köküne göre hesaplarken öteki dosyaları başka bir çalışma ağacına taşıyorsa güvenlik kapısı sessizce atlanır. Bir örnekte tam takım geçti, ama kilitli test kart çalışma ağacında açık kaldı.

Sınama: her güvenlik kapısını öteki özelliğin bağlamında (ör. ağaç yolu) geçici git deposunda, hook'a stdin JSON vererek sına.

**Çelişen kart kriterleri işçi turlarını döngüye sokar.**

"Tam takım geçer" ile "yalnız şu dosyalar değişir" birlikte istendiğinde, başka işin kırdığı test ya da yazma alanı dışındaki dosya iki kriteri aynı anda karşılanamaz kılar. Kart düzeltilmeden işçi yeniden çağrılınca ret ve tur sayısı artar.

Sınama:
- Ret vermeden önce `kart goster` ile kriterlerin ve yazma alanının son retten sonra değişip değişmediğine bak.
- Grep kriterinde eşleşen dosyanın yazma alanı içinde olup olmadığını kontrol et. Değilse ilk retten kriter-belirsiz ver.
- Eşitlik iddiasında (seri = paralel) iki tarafı da kendin koş. Yüke duyarlı test varsa kriter-belirsiz ver.
- Gizlenmiş alan dışı değişikliği `git status` ile ara.

**Kayıt sayılarında zaman alanının anlamına bakılır.**

`test_kosulari.zaman` koşunun bitişini değil başlangıcını gösterir. Bitiş için `zaman + sure_s` kullan. `reddedildi` kalıcı bir kapanış değil, geçici bir açık durumdur. `kart-duzeltilmeli` yalnız workflow dönüş değeridir, karta yazılmaz.

Sınama: kayıtlardan sayı veren belgede sayıları belgenin kesim kuralıyla yeniden say. Ret talimatında sayıyı değil kesim kuralını düzelttir.

**Paylaşılan depoda commit git durumuyla denetlenir.**

Paralel oturumların commit edilmemiş işi olan depoda görülen kalıplar:
- Testler başkasının değiştirdiği dosyaya eklenip commit dışında kalıyor.
- Geçici indeks ya da kısmi stage sonrası ana indeks o yolları eski hâliyle staged bırakıyor; sıradaki commit işi geri alıyor.
- Test içindeki `git commit` geçici depo yerine gerçek depoda çalışıyor ve yabancı commit bırakıyor.

Sınama: `git show <sha> --stat`, `git diff --cached --stat`, `git status --short` ve `git log --all -3 --name-only` ile bak. Testi `git archive <sha>` ağacında koş.

**Panel UI kusurları gerçek tarayıcıyla sınanır.**

Aynı kusur sınıfı tekrar etti:
- Hata işleyicisi son iyi veriyi siliyor.
- Alan değişiminde eski veri sızıyor.
- Uçuştaki istek her yoklamada iptal ediliyor.
- Sticky başlıkta `scroll-padding-top` unutuluyor; Shift+Tab ile odak başlığın altında kalıyor.

Sınama: fetch'i belge yüklenmeden sar (CDP `Page.addScriptToEvaluateOnNewDocument`; POST `/ac` sahte yanıtla engellenir). Kalıcı hata, toparlanma ve alan değişimi senaryolarında DOM değişimlerini MutationObserver ile say. Odak örtmesini gerçek Tab ve Shift+Tab ile ölç.

## Geliştirme geçmişi ve kararlar (McD hafızasından taşındı, 17.10.2026, I-057)

Kaynak iş klasörleri McD deposundadır (`C:\Mert\McD\Claude_Orkestrasyon\NNN-…`); eklentiyi kuran başka bir kullanıcıda bulunmaz. Sayılar yazıldıkları günün ölçümüdür.

### Kurulum ve ayar kapsamı
- Eklentiler user kapsamında kurulur (`araclar/projeye_kur.py --kullanici`); `~/.claude/settings.json` içine `enabledPlugins`, kota durum satırı, `Bash(orkestra *)` izni ve `PYTHONUTF8` yazılır. Eski karar (13.10: genel ayar bilerek boş, proje kapsamı) 17.10'da değişti (I-054).
- Marketplace kaynağı `Claude_Orkestrasyon\plugin_yayin` yayın klonudur; sürüm = commit SHA. Başka oturumların commitlenmemiş işi çalışan eklentiye sızmasın diye bilerek kullanılır.
- Gömülü CLI PATH'te değil; `projeye_kur.py` `claude_exe()` yolunu kendisi bulur (`CLAUDE_CODE_EXECPATH`).
- Kesin token: `hooks/sayac.ts` (turn.complete) yazar; alt ajan transkriptleri çıkış tokenını eksik tutar, hook kaydı yalnız yedektir.
- Taşınabilirlik: ortam başka makineye taşınırken hafıza `~/.claude/projects/<proje>/memory`, hook'lar `python` çağırır (Mac'te `python3` sorunu), `hooks.json` platforma dayanıklıdır (16.10).
- Eklentinin tek kaynağı `Desktop\Claude-Orchestration`. Yeni skill, ayar ve kayıt buraya yazılır (`skills\<ad>\SKILL.md`, betik skill klasöründe, test `tests\`, README satırı), projenin `.claude\skills\` klasörüne yazılmaz. `plugin_yayin`'e yazılan iş eşitlemede `koruma/klon-*` dalına alınır, main'e girmez. Skill adı `/orkestra:<ad>` olur; betikte projeye özgü yol kalmaz.
- Push yalnız bu depo içindir (`origin/main`); McD deposunun uzak deposu yoktur.

### Yetenekler (14-16.10.2026)
- **İş/todo modeli:** her işin tek `todo.md`'si görev klasöründe; `orkestra is todo <id> --ekle/--bitti`.
- **Kart worktree:** kart çalışması `.claude/worktrees` altında `kart/G-NNN` dalında; teslim `orkestra kart teslim G-NNN`, temizlik `kart agac-temizle`.
- **Yönlendirme ipucu:** `is_yonlendirme.py` (ilk istekte yeni iş mi devam mı).
- **Paralel test:** `scripts/test_paralel.py` (tam takım ~4 dk).
- **Maliyet:** ana ajan toplam maliyetin %65'i (15.10), %71'i (16.10; 663,61 / 937,78 $). En büyük kaçak, 1 saati aşan aradan sonra büyük bağlama dönüşte önbelleğin yeniden yazılması. Önlemler: soğuk önbellek kapısı (UserPromptSubmit; ezme `.claude/orkestra/onbellek_kapisi.json`), T1–T3'te tek çağrıda denetim, `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE`.
- **Öneri sistemi (6926d8b):** `scripts/oner.py basamak` (geçmiş ilk-geçiş onayı Beta(1,1) × kart başı USD → en ucuz başlangıç basamağı; TF-IDF benzer kart; ret nedeninden kriter ipucu) ve `scripts/kural_aday.py rapor` (tekrarlayan ret → kural adayı, medyan+3·MAD anomali, p90×2 bütçe tavanı). Yalnız öneridir. Bandit ve embedding k-NN ≥200 karta ertelendi.
- **Mimari kazanımlar (007):** Faz 0-1 ölçümü hiçbir paketin (K1, K2, K4, K5) koda geçişini desteklemedi; K4/K2 sınaması gölge veride n≥5 ret birikince.
- **Bölme:** `orkestra.py` 8 modüle bölündü (`scripts/komutlar/`, 90a403c, main'de). Testte yama artık `komutlar.<modül>` üzerine yapılır. Sıradaki: `hook.py`, `ork_lib.py`, `kart.py` (iş 012).

### Bilinen anomali: K2 kart-ajan-çok
Eşik 8 ajan; 14 günde 32 kez çıktı. Kök neden: kartlar tek soruya bölünmüyor, denetçi ve yeniden deneme ajanları birikiyor (yeniden deneme çarpanı 4,02 → 3,89). Kart planlarken kriteri ≤5 tut. Açık kod işi: kart açılışında kriter sayısı >5 ya da beklenen dosya çoksa "kartı böl" uyarısı; `kural_aday.py` ajan tavanını 8'de sert uyarıya çevirmek. İzleme sayacı: `kart_ajan_cok_anomalisi`.

### Cursor uyumu (019) ve belge kalitesi (021)
- Karar: orkestra host sohbetinde çalışır (API yok); kural kapıları host hook'undan orkestra CLI'sine taşınır. Cursor CLI 2026.10.14; `.cursor/hooks.json` git kökünden okunur (iç klasördekiler yok sayılır), BOM'lu yazılırsa hook'lar sessizce yüklenmez. Aşama 0 CLI ve TUI'de ölçüldü, IDE sürülemedi (açık risk). Taşınabilirlik yaklaşık %83.
- Belge kalitesi: Ö1+Ö2 uygulandı (şablonlar, `orkestra is belge`, `is baglanti`); Ö3/Ö4 gölge modda (`gunluk.jsonl`'a `kural_ihlal` düşer). Bekleyen karar: ihlal moduna geçiş.
- K-006 kök neden ilkesi eklenti kuralıdır (`kurallar/eklenti_kurallari.json`).

## is-anlati (I-177, ADR-0037)
- Kanıt yalnız iş kaydındandır (`is.json`, mevcut durum, plan, todo, çalışma özeti); git/Jira okunmaz, ayrı günlük yoktur.
- Parçalar: `scripts/is_anlati.py` (paket, durum, izinli fiil), `scripts/is_anlati_denetle.py` (A01-A09), `orkestra is anlati` (`komutlar/isler.py`), `skills/is-anlati/SKILL.md`.
- Testler: `test_is_anlati*.py`; `ORKESTRA_IC_KOS=0` altında `test_guclu_fiil_izni_isin_paketinden` mock'u görmediği için kırılır (bilinen).

## Çalışma özeti tek kaynak (I-239, ADR-0091)

- `sablonlar/calisma_ozeti.md` Özet alanları: Durum, Amaç neydi?, Ne yapıldı?, Nasıl karar verildi?, Ana sayı, Senden beklenen, Açık kalanlar; Harita'da `Teslim` (Değişiklik, Test, Deploy, Geri alma). `Amaç neydi?` ve `Ne yapıldı?` etiketleri kapanış kapısı (`isler._ozet_eksigi`) ve `is_anlati.py` tarafından okunur, yeniden adlandırılmaz.
- Eski/yeni biçim: `Amaca tamamen ulaşıldı mı?` taşıyan özet eski biçimdir, yeni alan uyarısı almaz (`is_kaydi.sef_ozeti_eksigi`). Katman 1 sınırı 1200 (`ayarlar/sef_ozeti.json`); kapı gölgede, ihlal geçişi `gecis_esikleri` ölçülünce ayrı kararla.
- Yönetici anlatısı `orkestra is anlati` (paket alanları `durum`, `nasil_karar`, `ana_sayi`; A10: Durum Kısmen/Engelli iken taslakta sınır ifadesi şart), Jira Done yorumu `orkestra is jira-yorum` (LLM yok) özetten türetilir; ayrıca yazılmaz.
- Test: `tests/test_birlesik_ozet.py` alan adı uyumunu parçalar arası sınar.

## Standartlar

PR, commit, dal, review ve Jira yorumu gibi yapı standartları kural değil dosyadır (ADR-0006): eklentide `standartlar/*.md` varsayılan kalıplar, projede `.claude/orkestra/standartlar/<ad>.md` varsa o önceliklidir. `orkestra standart liste|goster|yol|ekle` okur ve yazar, `orkestra:standart` skill'i PR/commit/Jira yazarken ve incelerken ilgili dosyayı okutur. Kod: `scripts/standart.py`, `scripts/komutlar/standart.py`; test: `tests/test_standart.py`. Hook denetimi bu sürümde yoktur.
