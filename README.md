# Claude-Orchestration

Claude ekosistemini kullanan kişisel bir ajan orkestrasyon sistemi. Hepsi Claude Code içinde çalışır: plugin, subagent, skill, hook, workflow, mod ve otomatik hafıza.

- **Maliyet merdiveni:** Her iş, izin verilen en ucuz basamakta başlar. Basamaklar: betik → Haiku 5.5 → Sonnet 5.5 → Opus 5.5 medium → Opus 5.5 xhigh. Fable kullanılmaz: denetçi hiçbir basamakta işçinin altında kalmasın diye en üst basamak da Opus 5.5'tir.
- **Ana ajan planlar, dağıtır, toplar:** Planlama Opus 5.5 medium'da yapılır. Ana ajan işçi işi yapmaz ve onay yazmaz.
- **Ayrı denetçi:** Her işçi çıktısını ayrı bir `denetci` ajanı kabul kriterlerine göre denetler. Kimse kendi işini onaylayamaz. Kural üç katmanda zorlanır: ajan araç kısıtı, hook kimlik enjeksiyonu ve CLI kontrolü.
- **Paralellik:** Görev kartları bağımlılık grafiği olarak yürür. Yazma alanı kesişmeyen işler aynı anda koşar. Bir hook alan dışına yazmayı reddeder.
- **Ortak defter:** Her ajan bitince ne yaptığı otomatik olarak deftere eklenir. İhtiyacı olan ajan yalnız ilgili kayıtları okur.
- **Token defteri:** Her ajanın her süreç için harcadığı token ve maliyet kaydedilir; kırılım ajan × süreç × model.
  - Kesin değeri `sayac` modülü yazar: motorun her tur sonunda bildirdiği kullanımı kaydeder.
  - Yedek kaynak, hook'ların transkript okumasıdır. Alt ajan transkriptleri çıkış tokenını eksik tuttuğu için bu yalnız tahmindir.
- **Sohbet maliyeti:** Çalışma alanındaki her sohbet, kenar çubuğundaki adıyla ve maliyetiyle panelde listelenir.
  - Kapanmış sohbetlerde motorun kendi hesabı (`cost-state`) gösterilir.
  - Açık sohbetlerde defter değeri gösterilir ve `≈` ile işaretlenir.
- **Perspektif:** Oturumlar arasında arka planda hafıza bakımı ve skill avı yapılır. Yalnız öneri üretir; hafızayı onayınla değiştirir.
- **Arayüz (üç sayfa, tek veri kaynağı):** Hook'lar ve CLI her durum değişikliğinde `.claude/orkestra/ozet.json` anlık görüntüsünü yazar; arayüzler yalnız bu dosyayı okur.
  - **Claude içinde** (`/orkestra`): sohbetin yanında bir özet açılır. En üstte dikkat isteyen kartlar (ret, denetimde, teslim bekleyen), altta çalışan kartlar (en çok altı). Sonra bu sohbetin ve bugünün maliyeti tek satırda, son üç olay, perspektif raporu hazırsa bir satır ve veri yaşı. Ayrıntı için `/orkestra-web`.
  - **Prompt üstü bant:** Yalnız kullanıcıdan eylem beklenen durumda çıkar: ret, teslim bekleyen kart ya da hazır perspektif raporu. Yalnız maliyet varsa görünmez. **Gizle** o durumu gizler; yeni bir ret, teslim ya da rapor gelince bant geri gelir.
  - **HTML canlı panel** (`/orkestra-web`, ya da Bash'te `orkestra panel`, ya da `araclarpaneli_ac.cmd`): `http://127.0.0.1:8765/` adresinde üç sayfa açar. Sayfalar üç saniyede bir yenilenir. Yalnız koyu temadadır ve yalnız bu bilgisayardan erişilebilir.
    - **Şimdi** (`/`): ne oluyor, senden ne bekleniyor. Sohbetler (kimi bekliyor), görev kartları, son olaylar.
      "Kimi bekliyor"u hook'lar yazar (UserPromptSubmit → Claude çalışıyor, Stop → seni bekliyor, SessionEnd → kapandı). "Ne/neden"i ana ajan yeni bir iş başlarken `orkestra niyet --ne "…" --neden "…"` ile yazar, bitince `--sonuc "…"` ekler. Kayıt bütün projeler için tek dosyada: `~/.claude/orkestra-panel/niyet.jsonl`.
    - **Maliyet** (`/maliyet`): ne kadar harcanıyor, nereye. Kapsam seçici, iş türü × model, ajan tablosu, zaman içinde harcama, kota, tüm projeler.
    - **Verim ve sağlık** (`/verim`): sistem iyi çalışıyor mu. Basamak verimliliği, birim maliyet, kart akışı ve paralel zaman çizelgesi, skill getirisi, sağlık (hafıza sınırı, son perspektif, etiketsiz ajan, hook hataları).
    - `/analitik` ve `/analitik.html` adresleri `/verim`'e yönlendirilir (301, sorgu dizesi korunur).
    - Çalışma alanı başlıktaki seçiciden seçilir. Orkestra kurulu alanda tam görünüm, kurulu olmayanda yalnız maliyet gösterilir.
    - Şimdi sayfasındaki **Sohbeti aç** düğmesi sohbeti Claude uygulamasında açmayı dener.
  - **Kota kaydı:** Claude kullanım sınırlarını yalnız durum satırı komutuna verir (Pro/Max). `projeye_kur.py`, proje ayarında `statusLine` yoksa `scripts/kota.py`'yi bağlar; betik değerleri `~/.claude/orkestra-panel/kota.jsonl`'a yazar.

## Yapı

```
.claude-plugin/marketplace.json     yerel klasör marketplace'i (claude-orchestration)
plugins/orkestra/                   çekirdek plugin
  agents/      triyaj, isci-t1..t4, denetci, arastirmaci, hafiza-bakimcisi, skill-avcisi, arsivci
  skills/      is, baslat, maliyet, defter, perspektif, skill-avi        →  /orkestra:<ad>
  workflows/   calistir.js   (DAG yürütme, işçi → ayrı denetçi, 2 ret → basamak yükseltme)
  hooks/       hooks.json → scripts/hook.py (9 olay); sayac.ts (turn.complete → kesin token kaydı)
  scripts/     ork_lib.py, orkestra.py (CLI), hook.py, perspektif.py, ozet.py (anlık görüntü), panel.py (HTML sunucusu: üç sayfa, /analitik → /verim),
               analitik.py (analitik hesapları), kota.py (durum satırı: kota kaydı), niyet.py (Şimdi sayfasındaki Sohbetler bölümü: ne/neden/kimi bekliyor)
  assets/      simdi.html (/), maliyet.html (/maliyet), verim.html (/verim); ortak.css ve ortak.js üç sayfanın ortak kabuğu
  bin/         orkestra, orkestra.cmd (CLI'yı PATH'e koyar), fiyat.json
  tests/       test_cekirdek.py (python -m unittest)
  evals/       claude plugin eval vakaları
plugins/orkestra-ui/                arayüz modu (Pane + AbovePrompt bandı + /orkestra)
araclar/sifre_temizle.py            oturum kayıtlarından düz metin şifre temizleme (elle çalıştırılır)
araclar/yayin_kur.py                yayın klonunu açar, git hook'larını yazar; araclar/git_hooklar/ hook şablonları
```

## Yeni bir projeye kurmak (tek komut)

```
python <depo>/araclar/projeye_kur.py <proje klasörü>
```

Komut şunları yapar:
- Plugin'leri proje kapsamında kurar.
- Proje ayarlarına orkestra varsayılanlarını ekler; var olan değerin üstüne yazmaz.
- Durum klasörünü açar.
- Git deposuysa `.gitignore` dosyasına satır ekler.
- `CLAUDE.md` dosyasına kısa bir bölüm ekler.

Genel ayarlara dokunmaz ve tekrar çalıştırmak güvenlidir.
- Önizleme için `--kuru`, arayüz olmadan kurmak için `--ui-yok`, projeden çıkarmak için `--kaldir` kullan.
- Kurulumdan sonra o projede yeni bir Claude oturumu aç.

## Başka bilgisayarda kurulum (GitHub private)

Depo GitHub'da özel (private) tutulur. İki yol vardır; ikisi de marketplace kaynağı olarak GitHub deposunu kullanır (kök `.claude/settings.json` içindeki `extraKnownMarketplaces` → `source: github`).

### Gereksinimler

- **Claude Code:** kurulu ve oturum açılmış (`claude` komutu ya da masaüstü uygulaması).
- **Python 3:** hook'lar ve `orkestra` CLI'ı Python betikleridir. Alt sürüm için resmi bir bildirim yoktur; kod taramasında en yüksek gereksinim 3.8'dir (atama ifadesi `:=`, `plugins/orkestra/scripts/ozet.py:160`). Her sürümde koşturulmadı, bu yüzden 3.8 alt sınırı **doğrulanmadı**; güncel bir 3.x kullan. `python` komutu PATH'te olmalıdır.
- **git** ve özel depoya okuma erişimi: Claude Code marketplace'i makinedeki `git` ile, soru sormadan (etkileşimsiz) klonlar; Claude Code'un kendi git belirteci yoktur. Kimlik doğrulama (kaynak: [Grant access to a private marketplace](https://code.claude.com/docs/en/plugins/host-marketplace#grant-access-to-a-private-marketplace)):
  - SSH: anahtar parolasız çalışmalı (örn. `ssh-agent`) ve `github.com` `known_hosts` içinde olmalı. `owner/repo` biçiminde Claude Code önce `ssh -T git@github.com` dener, olmazsa HTTPS'e düşer.
  - HTTPS: git kimlik yardımcısında (credential helper) kayıtlı bir kimlik bilgisi gerekir; yardımcı soru soramaz. GitHub'da `gh auth login` ve ardından `gh auth setup-git` bunu kaydeder.
  - SSH anahtarı olmayan makinede `CLAUDE_CODE_PLUGIN_PREFER_HTTPS=1` ayarlanır (oturum içi `/plugin` kurulumları ve güncellemeler HTTPS'e kendiliğinden düşmez).
  - Yalnız `GITHUB_TOKEN` ortam değişkeni arka plan denetimini tek başına doğrulamaz; belirteç ancak `gh` gibi bir kimlik yardımcısı üzerinden işe yarar.

### Yol A: depoyu klonla ve Claude Code'da aç

1. Depoyu klonla: `git clone https://github.com/SAHIP/Claude-Orchestration.git` (SAHIP yer tutucusu için aşağıya bak).
2. Klasörde Claude Code'u aç ve klasöre güven (workspace trust).
3. Kök `.claude/settings.json` (`extraKnownMarketplaces` + `enabledPlugins`: `orkestra@claude-orchestration`, `orkestra-ui@claude-orchestration`) devreye girer; plugin'ler marketplace'ten yüklenir.
4. Yeni oturumda `/plugin` ile plugin'lerin listelendiğini doğrula. Sistem yalnız açılmış projelerde iz tutar: bu klasörde izleme istiyorsan `/orkestra:baslat` çalıştır.

### Yol B: kendi projene kur (tek komut)

```
python <depo>/araclar/projeye_kur.py <proje klasörü> --kaynak github
```

- `--repo SAHIP/DEPO` ile GitHub deposu verilir; verilmezse klonun `origin` adresinden türetilir, bulunamazsa komut hata verir.
- `--kaynak yerel` (varsayılan) yayın klonunu kullanır: `--yayin <yol>`, yoksa `ORKESTRA_YAYIN`, yoksa `<depo>/../claude-orchestration-yayin`. `--kaynak github` bu yola ihtiyaç duymaz.
- Önce `--kuru` ile ne yapılacağını görebilirsin. Seçenekler için `python <depo>/araclar/projeye_kur.py --help`.
- Sonra o projede yeni bir Claude oturumu aç. Özel depo için yukarıdaki git kimlik bilgisi bu makinede hazır olmalıdır.

### SAHIP yer tutucusu

Kök `.claude/settings.json` içinde `"repo": "SAHIP/Claude-Orchestration"` yazar. `SAHIP` yer tutucudur: depoyu GitHub'a yüklediğin hesap ya da kuruluş adıyla değiştir ve commitle; aksi halde Yol A marketplace'i bulamaz. Yol B'de bu dosyaya gerek yoktur, `--repo` verilir ya da `origin`'den türetilir.

### Depoya girmeyenler

- Çalışma verisi `.claude/orkestra/` (kartlar, defter, maliyet, özet; `.gitignore`'da). Her makinede `orkestra baslat` ile yeniden açılır.
- Kişisel ve makineye özgü ayarlar: `~/.claude/settings.json`, `~/.claude/orkestra-panel/` (niyet, kota kayıtları) ve plugin önbelleği `~/.claude/plugins/`. Depodaki tek ayar dosyası kök `.claude/settings.json`'dır.
- Bir projeye Yol B ile kurulum, o projenin kendi `.claude/settings.json`, `.gitignore` ve `CLAUDE.md` dosyalarını değiştirir; bunlar o projenin deposuna aittir.

### Resmi dokümanla doğrulama (Claude Code dokümanı, 15.10.2026'da okundu)

| İddia | Sonuç | Kaynak |
|---|---|---|
| (a) `directory` kaynağı göreli yol kabul eder mi, neye göre çözülür | Kısmen doğrulandı: proje `.claude/settings.json` içinde `directory` ya da `file` kaynağında göreli yol, deponun **ana checkout'una** göre çözülür (git worktree'den çalışsan da ana checkout). `directory` için `path` "marketplace kökü"dür (`.claude-plugin/marketplace.json`'u içeren klasör). Başka bir çözüm tabanı (oturum klasörü, ayar dosyası konumu) açıkça belirtilmemiştir: **doğrulanmadı**. Bu depo `directory` değil `github` kaynağı kullanır; göreli `directory` yolu bu kurulum için gerekli değildir. | [Require plugins per repository](https://code.claude.com/docs/en/plugins/org#require-plugins-per-repository), [Marketplace sources](https://code.claude.com/docs/en/plugins/marketplace-reference#marketplace-sources) |
| (b) Proje `.claude/settings.json` içindeki `extraKnownMarketplaces` + `enabledPlugins` güven onayından sonra kurulumu kendiliğinden yapar mı | Kısmen doğrulandı: `extraKnownMarketplaces` yalnız klasöre güvenildikten sonra uygulanır; güvenilmeyen klasörde mesajsız yok sayılır. `enabledPlugins` oturum başında uygulanır. Marketplace'in **göreli yolla** (`./plugins/...`) listelediği plugin'ler marketplace kopyasından yüklenir; harici kaynaklı (örn. kendi GitHub deposu) plugin'ler için `claude plugin install <ad>@<marketplace> --scope project` gerekir. Bu deponun `marketplace.json` girdileri göreli yoldur (`./plugins/orkestra`, `./plugins/orkestra-ui`). Güven onayı sonrası ayrı bir "kurulsun mu" sorusu çıkıp çıkmadığı dokümanda yazmaz: **doğrulanmadı**; çıkarsa kabul et, çıkmazsa `/plugin` ile kontrol et. | [Require plugins per repository](https://code.claude.com/docs/en/plugins/org#require-plugins-per-repository), [When each surface applies the plugin keys](https://code.claude.com/docs/en/plugins/org#when-each-surface-applies-the-plugin-keys), [Settings: key waits for trust](https://code.claude.com/docs/en/settings) |
| (c) Özel GitHub kaynağı için kimlik doğrulama | Doğrulandı: makinedeki `git` ve mevcut kimlik bilgileri (SSH anahtarı ya da kimlik yardımcısı); Claude Code'un kendi belirteci yok, etkileşimli soru yok. GitHub'da `gh auth login` + `gh auth setup-git`. | [Grant access to a private marketplace](https://code.claude.com/docs/en/plugins/host-marketplace#grant-access-to-a-private-marketplace) |

## Kurulum ayrıntısı (çalışma alanına özgü)

Ayarlar bilgisayara değil çalışma alanına bağlıdır. Plugin'ler **proje kapsamında** kurulur ve yalnız o projede etkindir. Genel ayar dosyası (`~/.claude/settings.json`) boş kalır.

```
cd <proje klasörü>
claude plugin marketplace add <yayın klonu klasörü>
claude plugin install orkestra@claude-orchestration --scope project
claude plugin install orkestra-ui@claude-orchestration --scope project
```

Komutlar `<proje>\.claude\settings.json` dosyasına `enabledPlugins` ve `extraKnownMarketplaces` alanlarını yazar.

Model, effort, hafıza ve perspektif ayarları da aynı dosyadadır. Proje ayarı, genel ayardan önce gelir.

Masaüstü uygulamasında `claude` PATH'te yoktur. Gömülü ikili `%APPDATA%\Claude\claude-code\<sürüm>\…\claude.exe` altında bulunur. Hook'ların içinde aynı yol `CLAUDE_CODE_EXECPATH` değişkeninde durur.

Claude Code plugin'leri bu klasörden değil, kurulumda alınan kopyadan okur: `~/.claude/plugins/cache/claude-orchestration/<plugin>/<sürüm>/`. `plugin.json` ve `marketplace.json` içinde `version` alanı bilerek yoktur; git deposundaki göreli yol girdilerinde sürüm commit SHA'sı olur. Bu yüzden bir değişiklik commitlenmeden kopyaya geçmez (`claude plugin validate --strict` yalnız bu eksik sürüm uyarısı yüzünden hata verir; `--strict`siz geçer). Marketplace bu klasörden değil **yayın klonundan** okur (aşağıda). Akış: geliştir → commitle (push gerekmez) → yayın klonu otomatik ilerler → autoUpdate ya da `orkestra guncelle`.
- Değişikliği bu klasörde commitle. Commitlenmemiş (başka oturumların yarım) işler plugin kopyasına girmez.
- Otomatik: projenin `extraKnownMarketplaces.claude-orchestration.autoUpdate` değeri `true` (`projeye_kur.py` yazar). Claude Code ilk mesajdan sonra en çok 10 dakika içinde günceller, yeni kopya sonraki oturumda yüklenir.
- Hemen için: proje klasöründe `orkestra guncelle` (`--kuru` yalnız komutları yazar). Marketplace'i ve projede kurulu her plugin'i günceller; ardından yeni oturum aç ya da `/reload-plugins`.
- Oturum açılışında çalışan kopya kaynaktan farklıysa bağlama tek satır uyarı düşer (kaç dosya farklı, kaynakta commitlenmemiş değişiklik var mı).

### Yayın klonu (plugin_yayin)

`claude plugin update` commit'i değil marketplace klasörünün o anki çalışma ağacını kopyalar. Paralel oturumların commitlenmemiş işi çalışan plugin'e sızmasın diye marketplace bu klasörden değil, bu deponun temiz git klonundan (yayın klonu) okur. Varsayılan konum `<depo>/../claude-orchestration-yayin`, `--yayin` ya da `ORKESTRA_YAYIN` ile değişir (origin = bu klasör).
- Kurulum (tek komut, tekrar güvenli): `python araclar\yayin_kur.py` (`--yayin <yol>` ya da `ORKESTRA_YAYIN` ile yol değişir). Klonu açar ve `.git/hooks/` altına `post-commit`, `post-rewrite` (amend/rebase) ve `orkestra-yayin-esitle.sh` yazar; hook şablonları `araclar/git_hooklar/` altında izlenir.
- `plugin_yayin` elle düzenlenmez: hook klondaki yerel değişikliği `checkout -f` ile ezer; yalnız main'deki commit'ler yayına çıkar (başka dalda atılan commit klona dokunmaz).
- Her commit sonrası hook klonu çalışma dalıyla eşitler. Hata commit'i bozmaz (her zaman 0 çıkar, mesaj stderr'e).
- Yayın klonu elle düzenlenmez. `orkestra guncelle` önce klonu `fetch` + hızlı ileri sarar; klon kirliyse nedenini yazıp reddeder.
- `projeye_kur.py` marketplace kaynağını varsayılan olarak bu klondan alır.

HTML panel bu kuralın dışındadır: `python <bu klasör>\plugins\orkestra\scripts\orkestra.py panel` doğrudan bu klasörden çalışır.

Bir projede orkestrayı açmak için `/orkestra:baslat` kullan; sistem yalnız açılmış projelerde iz tutar.

## Kullanım

| Komut | Ne yapar |
|---|---|
| `/orkestra:is <istek>` | Planla → kart → paralel işçi + ayrı denetçi → topla ve teslim et |
| `/orkestra` | Claude içi özeti açar: dikkat isteyen kartlar, çalışanlar, tek satır maliyet, son olaylar, veri yaşı |
| `/orkestra-web` | HTML panelini başlatır (Şimdi, Maliyet, Verim ve sağlık) ve adresini verir (Bash: `orkestra panel`) |
| `/orkestra:maliyet [gün]` | Ajan × süreç × model token ve maliyet raporu |
| `orkestra niyet --ne … --neden …` | Sohbetin şu an ne yaptığını ve neye yarayacağını "Şimdi" sayfasındaki Sohbetler bölümüne yazar (ana ajan; `--sonuc`, `--goster`) |
| `/orkestra:defter [görev]` | Ortak defterin son kayıtları |
| `/orkestra:perspektif [şimdi]` | Perspektif raporunu gösterir, onaylananları uygular |
| `/orkestra:skill-avi` | Tekrar eden işlerden skill taslağı çıkarır |
| `/orkestra:onay` | Panelde onaylanan kararları (perspektif önerileri, skill taslakları, ajan soruları) uygular |
| `orkestra onay liste/goster/iste/karar/al/uygulandi/iptal/esitle` | Onay kuyruğu: panelin Onaylar sayfasıyla aynı kayıtlar; `iste` ajanın panelden karar istemesi, `karar --onay\|--ret` sohbette verilen kararı kaydeder |
| `orkestra kural liste/oner/ekle/duzenle/kaldir` | Kalıcı kurallar: `oner` panelde Kurallar sayfasında onaya düşer, etkin kurallar `.claude/rules/orkestra_kurallari.md` olarak yazılır |
| `orkestra …` (Bash) | Kart, defter, maliyet, perspektif CLI'ı (`orkestra --help`) |

## Paralel çalışma

Paralel oturumlar ve işçiler aynı commitlenmemiş çalışma ağacını paylaşır. Bir işçi dosyayı baştan yazarsa başka bir oturumun arada yaptığı değişiklik sessizce silinebilir. İki deterministik kapı bunu önler:

- **Çakışma kapısı:** Kart `isleniyor`a geçerken (`orkestra kart durum <id> isleniyor`) yazma alanı, aynı fiziksel ağaçta açık olan bütün kartların (hangi oturumdan olursa olsun) alanlarıyla karşılaştırılır.
  - Kesişim muhafazakârdır: iki desenden birinin literal öneki diğerinin altındaysa ya da desenler fnmatch ile birbirine uyuyorsa kesişir.
  - Kesişme varsa geçiş reddedilir: `çakışma: G-0xx (<desen>) — bekle ya da ayrı çalışma ağacı aç`.
  - Bir git deposunun kökünü ya da `**`ini kapsayan alan paylaşılan ağaçta reddedilir. Bu kural bir izin listesidir. Desenin sabit öneki, ilk joker bileşenden önceki yoldur; göreli desende proje köküne göre hesaplanır. Önek bir git deposunun kesin alt yolu olmalıdır: `RNV/**`, `src/**/*.py`, `docs/a.md`.
  - Önek deponun kökünün kendisiyse desen reddedilir: `**`, `*/**`, `**/*.py`, `*.md`. fnmatch'te `*` `/` dahil her karaktere uyar; kökteki `*.md` de bütün alt klasörlere uzanır.
  - Önek hiçbir deponun içinde değilse joker taşıyan ya da var olan bir klasörü gösteren desen reddedilir: `Üst/**`, `Depo*/**`, `C:/Users/**`. Depo dışında yalnız tek dosya literal yolu geçer.
  - İç içe depoyu fiziksel kesişim yakalar. Dış depodaki `RNV/**`, altındaki bir depoda ya da o deponun worktree'sinde açık olan kartla çakışır.
  - `kart yeni` ve `kart toplu` aynı denetimi yalnız uyarı olarak yazar. Yazma alanı boş kart denetlenmez.
- **Kart çalışma ağacı:** `orkestra kart agac <id>` kartın deposunda `<depo>-kart-<id>` klasörüne `kart/<id>` dalıyla bir git worktree açar.
  - Kartın yazma alanı yeni köke çevrilir. `calisma_agaci` alanı (`depo`, `yol`, `dal`, `taban`) karta yazılır. `Çalışma ağacı: <yol>` satırı kartın girdisinin başına eklenir; işçi istemi bu satırı görür.
  - Ayrık çalışma ağaçlarındaki kartlar birbiriyle çakışmaz. Biri ötekinin içinde kalan (iç içe) depo ayrık sayılmaz.
  - Hook, işçinin yazımını kartın çalışma ağacında denetler; paylaşılan ağaca yazmasını reddeder.
- **Birleştirme:** `orkestra kart birlestir <id>` kart dalını `git merge --no-ff` ile birleştirir, sonra worktree'yi kaldırır ve dalı siler.
  - Kart dalında commitlenmemiş değişiklik varsa reddeder.
  - Ana ağaçta kartın dosyalarında commitlenmemiş değişiklik varsa reddeder; sessiz ezme yoktur.
  - Çatışmada `git merge --abort` yapar, kartı `beklemede`ye alır ve çatışan dosyaları karta not eder. Çatışmayı asla otomatik çözmez.
  - `orkestra kart teslim`, çalışma ağacı olan kartta önce birleştirir; birleşmezse teslimi reddeder.

Çatışma yüzünden `beklemede` kalan kart, çalışma ağacı ve dalı korunmuş hâlde bekler. Yeniden birleştirmek için çatışmayı kart dalında çöz:
1. Kartın çalışma ağacında ana dalı birleştir: `git -C <kart ağacı> merge <ana dal>`.
2. Çatışan dosyaları (`birlestirme_catismasi` alanı) elle düzelt ve commit et.
3. `orkestra kart birlestir <id>` komutunu yeniden çalıştır; bu kez çatışmasız birleşir ve worktree temizlenir.

Çözüm işin kendisini değiştirdiği için kart yeniden işçi ve denetçiden geçer: `isleniyor` → `is-bitti` → onay → `orkestra kart teslim <id>`.

## Basamaklar ve denetim eşlemesi

| İşçi basamağı | İşçi | Denetçi |
|---|---|---|
| T0 betik / T1 | Haiku 5.5 | Haiku 5.5 (T0 kartları T1 yoluyla; denetçiden önce T0 ön kontrol betiği koşar) |
| T2 | Sonnet 5.5 | Sonnet 5.5 medium |
| T3 | Opus 5.5 medium | Opus 5.5 high, iki mercek |
| T4 | Opus 5.5 xhigh | Opus 5.5 xhigh (ayrı örnek), iki mercek |

Bir iş aynı basamakta iki kez reddedilirse (AYNI_BASAMAKTA_EN_COK_RET = 2) bir üst basamakta yeniden denenir; yetenek-yetersiz nedeninde ilk ret de yükseltir. Kartta toplam ret DENETCI_OPUS_RET_ESIGI (= 2) değerine ulaşınca denetimler opus'a geçer (T4'te xhigh).

## Testler

```
python -m unittest discover -s plugins/orkestra/tests -v
claude plugin validate plugins/orkestra --strict
claude plugin test plugins/orkestra-ui
claude plugin eval plugins/orkestra --trust-plugin --runs 1
```

## Bilinen sınırlar

- **Kabuk yazımı:** Yazma alanı kapısı Write ve Edit araçlarını engeller. Kabukla yapılan yazımı yalnız korunan orkestra dosyaları için engeller.
- **Mod API'si:** Mod API'si erken erişimdedir; Claude Code sürümleri arasında değişebilir. Arayüz bozulursa çekirdek çalışmaya devam eder.
- **Maliyet tutarları:** Tutarlar API liste fiyatıyla yapılmış tahminlerdir. Abonelikte gerçek fatura değil, kota karşılığıdır.
- **Diğer araçlar:** Sistem yalnız Claude Code içinde çalışır. Cursor ya da Antigravity'nin kendi ajanları bu plugin'i yüklemez. Ancak bu editörlerin terminalinde ya da Claude Code eklentisinde çalışan Claude Code, sistemi aynen kullanır.
