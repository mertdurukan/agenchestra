<!-- Bu dosya scripts/dokuman_uret.py ile üretilir; elle düzenleme. -->

# CLI: `orkestra`

Kaynak: `scripts/orkestra.py` ve komut modülleri. Aşağıdaki metin `orkestra --help` çıktısıdır; komut başına ayrıntı için `orkestra <komut> --help`.

```text
usage: orkestra [-h]
                {baslat,update,guncelle,kart,defter,maliyet,perspektif,ruya,onay,kural,niyet,ui-ozet,panel,kpi,gunluk,is,teknik,doktor,plan,izin,iz,politika,bakim,harita,standart,kimlik,mcp,push-kapisi,ara,isabet,onbellek,durum,kanit,ortam,hata,adr,konu,yol,niyetler,paralel,olay,kapi,oturum,teslim,git,agac,nesne-karti} ...

orkestra — görev kartları, ortak defter, token defteri ve perspektif için komut satırı aracı.

Kullanım (ajanlar Bash'ten çağırır; `orkestra` plugin bin/ ile PATH'tedir):
  orkestra baslat                                   bu projede durum klasörünü açar
  orkestra kart yeni --baslik T --soru "kartın cevaplayacağı tek soru" --basamak T2 [--sinif S] [--girdi M] [--kabul K]... [--yazma GLOB]... [--bagimli G-001]...
                     [--test-komutu M] [--test-alani GLOB]...     (--sinif kod ise ikisi ZORUNLU; glob proje köküne göre)
                     [--test-koku MUTLAK_DIZIN]                    (kod kartı, isteğe bağlı: test kökü proje yerine bu dizin)
                     [--genislet-onay]   (analiz kartında geniş tarama uyarısını kullanıcı onayıyla kaldırır; --soru ZORUNLU, tek cümle)
  orkestra kart toplu plan.json | --json-dosya plan.json   (liste: [{baslik, basamak, kabul_kriterleri, yazma_alani, bagimliliklar,
                                                    test_komutu, test_alani, ...}])
  orkestra kart goster G-001 | liste [--hepsi] [--json]
  orkestra kart durum G-001 isleniyor|is-bitti|beklemede|iptal|planlandi [--ozet M] [--cikti YOL]... [--not M]
  orkestra kart test-kos G-001 --asama kirmizi|yesil [--zaman-asimi SN]     (kod kartı; geçti → 0, geçmedi → 4)
        kirmizi: kod yokken test BAŞARISIZ olmalı; olursa test dosyaları sha256 ile kilitlenir (kilitliyken hata)
        yesil:   test GEÇMELİ ve test dosyaları kilitle birebir aynı olmalı
  orkestra kart test-kilit-ac G-001 --neden M                                (yalnız ana ajan)
  orkestra kart test-ayar G-001 [--test-koku YOL] [--test-komutu M] [--test-alani GLOB]...   (yalnız ana ajan;
        kilitliyken yalnız test_koku değişir ve yeni kökteki test dosyaları kilitle birebir aynı olmalı)
  orkestra kart denetim G-001 --karar onay|ret --gerekce M [--talimat M]      (yalnız denetçi ajan;
        kod kartında onay için son is-bitti'den sonraki en son test koşusu geçen yeşil olmalı ve dosyalar kilitle aynı)
  orkestra kart yukselt G-001 --basamak T3 --neden M
  orkestra kart teslim G-001 [--ozet M]                                        (yalnız ana ajan, onaylı kart)
  orkestra kart agac G-001 [--taban HEAD]         kart başına git çalışma ağacı (<depo>/.claude/worktrees/kart-<id>; ORKESTRA_AGAC_KOKU varsa
        <kök>/<depo-adı>/kart-<id>; dal kart/<id>). İptalde temiz ağaç kaldırılır (force yok)
  orkestra kart agac-temizle [--uygula]          biten/kartsız kart ağaçlarını listeler (--uygula: kaldırır; kirli ağaç atlanır)
  orkestra kart birlestir G-001                  kart dalını --no-ff birleştirir; çatışmada geri alır, kart beklemede
  orkestra defter ekle G-001 --surec is [--yaptim M] [--sonuc M] [--not M]
  orkestra defter baglam G-001 [--max 2000]     ihtiyacın olan kayıtlar: kart + bağımlılıklar + aynı kartın geçmişi
  orkestra defter oku [--gorev G] [--son N] | ozet
  orkestra maliyet rapor [--gun N] [--md|--csv] [--cikti YOL] | ozet [--json] | anomali [--gun N] [--json] | yeniden-etiketle [--uygula] | yeniden-tip [--uygula]
  orkestra hata en-cok [--gun N] [--kaynak hook|cli|ozet|kart|kural] [--ilk N] [--json] | liste [--ilk N] [--json]   tekrar eden hatalar (salt okuma)
  orkestra onbellek kacak [--gun N] [--defter] [--olay] [--json]   önbellek kaçaklarını sınıfla (5 dk katman, model, boşluk, sıkıştırma) ve USD ile dök
  orkestra iz <istek_id|I-nnn|oturum> [--json|--csv] | iz kapsama [--json]   süre/token ağacı (toplam = defter) ve atıf kapsama ölçümü
  orkestra perspektif durum | basla | bitti | dogrula <rapor> | duzeltme-tara [klasör]   (dogrula: rapordaki Kanıt satırlarını yeniden hesaplar, tutmayan varsa çıkış 1; duzeltme-tara: hafızada tekrar eden düzeltme notları, bulgu varsa çıkış 1)
  orkestra gunluk ozet [--gun 7]
  orkestra onay liste [--durum D] [--tur T] [--json] | goster ID | iste --baslik B --metin M [--secenek S]... [--oturum O]
  orkestra onay karar ID (--onay|--ret) [--secim S] [--not N] | al ID [--oturum O] | uygulandi ID --ozet Z | iptal ID --not N | esitle
  orkestra kural liste [--json] [--katman proje|plugin] | oner --metin M [--neden N] | ekle --metin M [--neden N] [--katman proje|plugin] | duzenle ID --metin M | kaldir ID --not N
  orkestra kural tasi ID --katman proje|plugin [--kimligi-koru] | kapat ID [--not N] | ac ID | esitle   (katmanlar: KURALLAR.md, Kural katmanları)
  orkestra git denetim [--depo YOL]   dal sınıfı (uzakta birleşmiş, tek kopya), stash ve commitsiz sayısı; salt okunur (I-325)
  orkestra standart liste | goster AD | yol AD | ekle AD   (ekip yapı standartları: PR, commit, dal, review, Jira yorumu; ADR-0006)
  orkestra niyet --ne "şu an ne yapılıyor" --neden "neye yarayacak" | --sonuc "ne çıktı" | --goster   (yalnız ana ajan)
  orkestra nesne-karti dogrula KART [--dokum DOSYA] [--json]   nesne kartı derece ve kaynakça denetimi (ADR-0177)
  orkestra yol dallanma <kök> [--sinir N]   dağıtıcı/sınıflayıcı adaylarını listeler (ADR-0171)
  orkestra konu ac "başlık" [--neden N] | liste [--oturum O] [--json] | rapor [--gun N] [--tum] [--etiket] [--yaz DOSYA] [--json]   sohbet konu defteri (ADR-0116)
  orkestra niyetler ekle TÜR "niyet" [--kriter K] [--kisit K] [--ilgili ID] | durum ID DURUM [--kanit K] | liste [--json] | rapor [--json]   niyet defteri (ADR-0156)
  orkestra is istek I-nnn [--mesaj-dosya DOSYA | --mesaj METİN] [--talep METİN]...   kullanıcı mesajındaki bağlantıları ve taleplerini istek_defteri.md'ye R1…Rn yazar (ADR-0112)
  orkestra is dalga I-nnn|KLASÖR|plan.md [--yaz] [--json-cikti DOSYA] [--basamak T2]   plan → dalgalar, kritik yol, `## Dalgalar`, kart JSON'u
  orkestra is bosta I-nnn|KLASÖR|plan.md [--bekleyen P1,P2] [--plan-denetimde] [--json]   bekleme anında başlatılabilecek bağımsız maddeler (ADR-0158)
  orkestra oturum liste [--json] | not HEDEF "metin" | oku | rapor [--gun N]   oturumlar arası farkındalık ve not (veri, talimat değil; ADR-0125)
  orkestra teslim kuyruk ekle --dal D [--teslim ID] [--test gecti|yok] | liste [--durum D] [--json]   teslim kuyruğu: sırayı yazar (I-323)
  orkestra plan dogrula I-nnn|PLAN.md [--yaz] [--json] [--kok DİZİN]... [--komut-kosma] [--ac]   (plan.md iddialarını kanıtla doğrular, ✅/❌ koyar;
        çıkış 0 uygulanabilir, 1 koşullu, 2 uygulanamaz, 3 tamamlanmamış)
`--ajan-id/--ajan-tipi` argümanlarını PreToolUse hook'u ekler; elle verilenler silinir.

positional arguments:
  {baslat,update,guncelle,kart,defter,maliyet,perspektif,ruya,onay,kural,niyet,ui-ozet,panel,kpi,gunluk,is,teknik,doktor,plan,izin,iz,politika,bakim,harita,standart,kimlik,mcp,push-kapisi,ara,isabet,onbellek,durum,kanit,ortam,hata,adr,konu,yol,niyetler,paralel,olay,kapi,oturum,teslim,git,agac,nesne-karti}
    update (guncelle)   yayın klonunu GitHub'dan çek, kurulu plugin'leri kendi
                        kapsamıyla güncelle (LLM'siz)
    niyet               sohbetin şu an ne yaptığını ve neye yarayacağını
                        kaydet (panel 'Şu an' şeridi)
    kpi                 8 KPI salt okuma ölçümü
    is                  kalıcı iş katmanı (bir iş birden çok sohbete/karta
                        yayılır)
    teknik              kartın teknik detayı (betikle derlenir, LLM'siz)
    doktor              ilk çalıştırma sağlık denetimi ve güvenli onarım (A
                        otomatik, B --evet, C rehber)
    plan                plan.md iddia doğrulaması: kanıtı yeniden doğrular,
                        ✅/❌ koyar, uygulanabilirlik kararı verir
    izin                izin politikası: goster | sina (kapı kararı;
                        ayarlar/izin_politikasi.json)
    iz                  istek / iş / oturum için süre ve token ağacı; `iz
                        kapsama` atıf kapsama ölçümü
    politika            model politikası: goster
                        (ayarlar/model_politikasi.json)
    bakim               durum klasörü hijyeni: eski lock, eski oturum kaydı,
                        defter özeti, boş açık işler (varsayılan kuru koşu)
    harita              proje sistem haritası: yapılandırma, süreç, altyapı
                        kayıtlarını betikle üretir ve günceller
    standart            ekip yapı standartları: PR, commit, dal, review, Jira
                        yorumu
    kimlik              kimlik bilgisi klasörü (kullanıcı-düzeyi, proje bazlı
                        .env; değer yazmaz)
    mcp                 MCP kaydı: kimlikli sarmalayıcı config'i üret ve kur
                        (değer yazmaz)
    push-kapisi         yasak yola dokunan commit uzak depoya gitmez (pre-push
                        kapısı)
    ara                 iş klasörü, ADR ve kural metninde ara (TF-IDF; model
                        çağırmaz)
    isabet              kapanmış işlerde anılan dosyalar ile değişen
                        dosyaların kesinlik ve duyarlılığını ölç
    onbellek            önbellek kaçakları
    durum               oturum worktree durum kopyaları
    kanit               kanıtsız iddia ölçümü (ADR-0085): örnek çıkar, ana
                        ölçüyü hesapla
    ortam               codebase ortamları: manifestten kilitli ortam kur,
                        doğrula, komutu ortamdan koştur
    hata                tekrar eden hatalar (hook, CLI, özet, kart reti, kural
                        ihlali)
    adr                 ADR hedef deposu ve numarası (ADR-0097)
    konu                sohbet konu defteri: ac, liste, rapor (ADR-0116)
    yol                 plan öncesi yol kararı yardımcıları (ADR-0171)
    niyetler            niyet defteri: ekle, durum, liste, rapor (ADR-0156)
    paralel             bağımsız komutları (lint, derleme, doğrulama, test)
                        paralel koşar
    olay                olay kaydı: tür, kategori, sonuç ve gidiş yolu
                        önerileri (salt okuma)
    kapi                kapı modları: etkin modu ayardan oku
    oturum              oturumlar arası farkındalık: canlı oturumlar, not
                        bırak/oku, ölçüm
    teslim              teslim kuyruğu: işi toplu entegrasyon koşusuna ver
    git                 git durumu: dal, stash, gönderilmemiş commit (salt
                        okunur)
    agac                iş çalışma ağacı: deponun .claude/worktrees altında aç
    nesne-karti         nesne kartı doğrulayıcısı (ADR-0177): derece, kaynak
                        hiyerarşisi, kaynakça

options:
  -h, --help            show this help message and exit
```
