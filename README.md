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
- **Rüya:** Oturumlar arasında arka planda hafıza bakımı ve skill avı yapılır. Yalnız öneri üretir; hafızayı onayınla değiştirir.
- **Arayüz (üç sayfa, tek veri kaynağı):** Hook'lar ve CLI her durum değişikliğinde `.claude/orkestra/ozet.json` anlık görüntüsünü yazar; arayüzler yalnız bu dosyayı okur.
  - **Claude içinde** (`/orkestra`): sohbetin yanında bir özet açılır. En üstte dikkat isteyen kartlar (ret, denetimde, teslim bekleyen), altta çalışan kartlar (en çok altı). Sonra bu sohbetin ve bugünün maliyeti tek satırda, son üç olay, rüya raporu hazırsa bir satır ve veri yaşı. Ayrıntı için `/orkestra-web`.
  - **Prompt üstü bant:** Yalnız kullanıcıdan eylem beklenen durumda çıkar: ret, teslim bekleyen kart ya da hazır rüya raporu. Yalnız maliyet varsa görünmez. **Gizle** o durumu gizler; yeni bir ret, teslim ya da rapor gelince bant geri gelir.
  - **HTML canlı panel** (`/orkestra-web`, ya da Bash'te `orkestra panel`, ya da `araclarpaneli_ac.cmd`): `http://127.0.0.1:8765/` adresinde üç sayfa açar. Sayfalar üç saniyede bir yenilenir. Yalnız koyu temadadır ve yalnız bu bilgisayardan erişilebilir.
    - **Şimdi** (`/`): ne oluyor, senden ne bekleniyor. Sohbetler (kimi bekliyor), görev kartları, son olaylar.
      "Kimi bekliyor"u hook'lar yazar (UserPromptSubmit → Claude çalışıyor, Stop → seni bekliyor, SessionEnd → kapandı). "Ne/neden"i ana ajan yeni bir iş başlarken `orkestra niyet --ne "…" --neden "…"` ile yazar, bitince `--sonuc "…"` ekler. Kayıt bütün projeler için tek dosyada: `~/.claude/orkestra-panel/niyet.jsonl`.
    - **Maliyet** (`/maliyet`): ne kadar harcanıyor, nereye. Kapsam seçici, iş türü × model, ajan tablosu, zaman içinde harcama, kota, tüm projeler.
    - **Verim ve sağlık** (`/verim`): sistem iyi çalışıyor mu. Basamak verimliliği, birim maliyet, kart akışı ve paralel zaman çizelgesi, skill getirisi, sağlık (hafıza sınırı, son rüya, etiketsiz ajan, hook hataları).
    - `/analitik` ve `/analitik.html` adresleri `/verim`'e yönlendirilir (301, sorgu dizesi korunur).
    - Çalışma alanı başlıktaki seçiciden seçilir. Orkestra kurulu alanda tam görünüm, kurulu olmayanda yalnız maliyet gösterilir.
    - Şimdi sayfasındaki **Sohbeti aç** düğmesi sohbeti Claude uygulamasında açmayı dener.
  - **Kota kaydı:** Claude kullanım sınırlarını yalnız durum satırı komutuna verir (Pro/Max). `projeye_kur.py`, proje ayarında `statusLine` yoksa `scripts/kota.py`'yi bağlar; betik değerleri `~/.claude/orkestra-panel/kota.jsonl`'a yazar.

## Yapı

```
.claude-plugin/marketplace.json     yerel klasör marketplace'i (claude-orchestration)
plugins/orkestra/                   çekirdek plugin
  agents/      triyaj, isci-t1..t4, denetci, arastirmaci, hafiza-bakimcisi, skill-avcisi, arsivci
  skills/      is, baslat, maliyet, defter, ruya, skill-avi        →  /orkestra:<ad>
  workflows/   calistir.js   (DAG yürütme, işçi → ayrı denetçi, 2 ret → basamak yükseltme)
  hooks/       hooks.json → scripts/hook.py (9 olay); sayac.ts (turn.complete → kesin token kaydı)
  scripts/     ork_lib.py, orkestra.py (CLI), hook.py, ruya.py, ozet.py (anlık görüntü), panel.py (HTML sunucusu: üç sayfa, /analitik → /verim),
               analitik.py (analitik hesapları), kota.py (durum satırı: kota kaydı), niyet.py (Şimdi sayfasındaki Sohbetler bölümü: ne/neden/kimi bekliyor)
  assets/      simdi.html (/), maliyet.html (/maliyet), verim.html (/verim); ortak.css ve ortak.js üç sayfanın ortak kabuğu
  bin/         orkestra, orkestra.cmd (CLI'yı PATH'e koyar), fiyat.json
  tests/       test_cekirdek.py (python -m unittest)
  evals/       claude plugin eval vakaları
plugins/orkestra-ui/                arayüz modu (Pane + AbovePrompt bandı + /orkestra)
araclar/sifre_temizle.py            oturum kayıtlarından düz metin şifre temizleme (elle çalıştırılır)
```

## Yeni bir projeye kurmak (tek komut)

```
python C:\Users\PC\Desktop\Claude-Orchestration\araclar\projeye_kur.py <proje klasörü>
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

## Kurulum ayrıntısı (çalışma alanına özgü)

Ayarlar bilgisayara değil çalışma alanına bağlıdır. Plugin'ler **proje kapsamında** kurulur ve yalnız o projede etkindir. Genel ayar dosyası (`~/.claude/settings.json`) boş kalır.

```
cd <proje klasörü>
claude plugin marketplace add C:\Users\PC\Desktop\Claude-Orchestration
claude plugin install orkestra@claude-orchestration --scope project
claude plugin install orkestra-ui@claude-orchestration --scope project
```

Komutlar `<proje>\.claude\settings.json` dosyasına `enabledPlugins` ve `extraKnownMarketplaces` alanlarını yazar.

Model, effort, hafıza ve rüya ayarları da aynı dosyadadır. Proje ayarı, genel ayardan önce gelir.

Masaüstü uygulamasında `claude` PATH'te yoktur. Gömülü ikili `%APPDATA%\Claude\claude-code\<sürüm>\…\claude.exe` altında bulunur. Hook'ların içinde aynı yol `CLAUDE_CODE_EXECPATH` değişkeninde durur.

Claude Code plugin'leri bu klasörden değil, kurulumda alınan kopyadan okur: `~/.claude/plugins/cache/claude-orchestration/<plugin>/<sürüm>/`. Kopya yalnız sürüm numarası değişince yenilenir. Bir değişikliği oturumlara geçirmek için:
- `plugins/<plugin>/.claude-plugin/plugin.json` ve `.claude-plugin/marketplace.json` içindeki `version` değerini artır.
- Proje klasöründe `claude plugin marketplace update claude-orchestration`, ardından `claude plugin update <plugin>@claude-orchestration --scope project` çalıştır.
- Yeni bir oturum aç ya da açık oturumu yeniden başlat.

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
| `/orkestra:ruya [şimdi]` | Rüya raporunu gösterir, onaylananları uygular |
| `/orkestra:skill-avi` | Tekrar eden işlerden skill taslağı çıkarır |
| `orkestra …` (Bash) | Kart, defter, maliyet, rüya CLI'ı (`orkestra --help`) |

## Basamaklar ve denetim eşlemesi

| İşçi basamağı | İşçi | Denetçi |
|---|---|---|
| T0 betik / T1 | Haiku 5.5 | Sonnet 5.5 medium |
| T2 | Sonnet 5.5 | Opus 5.5 medium |
| T3 | Opus 5.5 medium | Opus 5.5 high, iki mercek |
| T4 | Opus 5.5 xhigh | Opus 5.5 xhigh (ayrı örnek), iki mercek |

Bir iş aynı basamakta iki kez reddedilirse bir üst basamakta yeniden denenir.

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
