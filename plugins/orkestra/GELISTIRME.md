# Eklenti geliştirme notları

Bu dosya eklentiyi geliştirenler içindir. Kullanım kuralları için `KURALLAR.md` dosyasına bak.

## Yayın akışı
Oturumlar eklentiyi `~/.claude/plugins/cache/claude-orchestration/<plugin>/<sürüm>/` altındaki önbellek kopyasından yükler (göreli yol girdisine rağmen). Sürüm commit SHA'sıdır (12 hane); `version` alanı bilerek yoktur.

1. Eklenti deposunda geliştir.
2. `main` dalına commit at.
3. Post-commit ve post-rewrite hook'u (`araclar/git_hooklar/yayin-esitle.sh`; kurulum `araclar/yayin_kur.py`) yayın klonunu ilerletir. Başka dalda ya da detached HEAD'de hiçbir şey yapmaz.
4. `orkestra guncelle` çalıştır (yayın klonu kirliyse reddeder). Çalıştırmazsan `autoUpdate` ilk mesajdan en çok 10 dk sonra alır.
5. Sonraki oturumda ya da `/reload-plugins` ile yeni sürüm yüklenir.

Notlar:
- Güncelleme commit'i değil, marketplace klasörünün çalışma ağacını kopyalar. Bu yüzden marketplace, geliştirme deposunun temiz git klonudur (yayın klonu). Yayın klonunu elle düzenleme.
- Commitlenmemiş iş yayına girmez.
- SessionStart bayatlık uyarısı önbellek kopyası ile yayın klonu arasındaki farkı bildirir.
- `validate --strict` sürüm alanı olmadığı için hep "No version specified" ile düşer (bilinçli).
- `orkestra` CLI'ı da önbellekten çalışır. HTML paneli geliştirme deposu yolundan `python <depo>/plugins/orkestra/scripts/orkestra.py panel` ile başlat.

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

## Kural katmanları (kod)
- Kütüphane `scripts/onay.py` (kurallar bölümü), CLI `scripts/komutlar/onay.py` (`kural ...`), panel `assets/kurallar.js` + `panel.py` `_onay_islemi`. Kullanım ve öncelik: `KURALLAR.md` "Kural katmanları".
- Eklenti katmanının deposu `kurallar/eklenti_kurallari.json`. `onay.eklenti_kural_yolu()` yolu çözer: önbellekten (`plugins/cache`) çalışırken yazım önbelleğe değil kaynak depoya (`known_marketplaces.json` installLocation) gider, çünkü önbellek güncellemede silinir. Eklenti kuralı eklemek eklenti kodunu değiştirmektir: commit, `orkestra guncelle`, yayın akışı bu dosyadaki gibi işler.
- Yazımda `KURALLAR.md`'deki işaretçili blok (`<!-- eklenti-kurallari:basla/bitis -->`) yeniden üretilir; elle düzenlenmez. Proje kural dosyası SessionStart'ta `onay.kural_dosyasi_esitle` ile yenilenir (içerik aynıysa yazmaz).
- Testler gerçek eklenti deposunu görmesin diye `tests/conftest.py` ve `tests/ic_kos.py` `ORKESTRA_EKLENTI_KURALLARI`'nı var olmayan bir geçici yola çevirir. Eklenti katmanını sınayan test bu değişkeni kendi geçici dosyasına ayarlar (`tests/test_kural_katman.py`).
- Yeni bir kural katmanı alanı eklenirse `kural_gorunum`, `kurallar` ve `_kural_dosya_metni` üçü birlikte güncellenir.
- Terfi kapısı: `scripts/onay.py` içinde `yayin_ayristir` (Yayın: etiketi), `terfi_denetle` (isabet listesi) ve `_terfi_kapisi` (isabette ValueError).
- Yasak terimler proje durum dizinindeki `terfi_yasak.json` dosyasından okunur (liste ya da `{"terimler": [...]}`); dosya yoksa yalnız kalıp denetimi çalışır.
- Testler: `tests/test_terfi.py`.

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

## İzin politikası (hook)
- Karar mantığı `scripts/izin_politikasi.py`, desenler `ayarlar/izin_politikasi.json`; hook'a bağlantı `hook.py` içinde `_izin_karari` / `_kapi_uygula` / `gec()` (varsayılan allow). Eşleşme `hooks/hooks.json` PreToolUse `matcher`ındadır: yeni bir araç ailesi kapıya girecekse eşleşmeye de ekle (`orkestra doktor` MCP kapsamını denetler).
- Karar sırası: kilitli test `deny` > yasak `deny` > kapı `ask` > `orkestra` CLI `allow` > geniş `allow`. Kabukta kapı, kilitli test denetiminden sonra uygulanır (kilidi onayla aşamasın).
- Testler: `tests/test_izin_politikasi.py`. `tests/conftest.py` `ORKESTRA_IZIN=0` verir (eski hook testleri kapı kararlarını boş çıktıyla sınar); izin testleri modu kendileri seçer.

## PostToolUse hook'ları
- `hook.py` `post_tool_use`: Skill, Agent, Task ve Workflow çağrılarını `gunluk.jsonl`'a yazar. `mcp__ccd_session__start_session` sonrasında K-007 detach hatırlatmasını (`detach_hatirlatmasi`) ek bağlam olarak verir. Test: `tests/test_hook_detach.py`.
- `scripts/oto_commit.py`: ayrı girdidir (`Edit|Write|MultiEdit|NotebookEdit`). Her düzenlemede çalıştığı için `hook.py`'yi yüklemez. `ORKESTRA_OTO_COMMIT` boş ya da `0` ise kabuk satırı Python'u hiç başlatmaz. Test: `tests/test_oto_commit.py`.

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
