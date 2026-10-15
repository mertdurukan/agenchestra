# Orkestra kuralları

Her projede geçerlidir. Projeye özgü bilgi bu dosyaya girmez; o kısım projenin kendi CLAUDE.md dosyasında durur.

## Ana ajan
- Orkestrada planla, dağıt, topla. Kartlı işte işçi işini kendin yapma; kart açıp açmayacağına aşağıdaki "Ana ajan mı, orkestra mı?" kuralıyla karar ver.
- Onay yazma. Onayı yalnız ayrı denetçi verir.
- Kart gerektiren işi `/orkestra:is` ile yürüt.
- Tekrar eden işte önce var olan skill'lere bak.
- Bilgi sorusu: hook notu "BİLGİ SORUSU" gelirse en çok 5 cümleyle cevapla. İş durumu, tablo ya da kaynak taraması ekleme; ayrıntıyı ancak istenirse ver. Ayar: `ayarlar/soru_sinif.json`; proje ezmesi `.claude/orkestra/soru_sinif.json`.
- Ana ajan mı, orkestra mı? Kart döngüsünün bir bedeli var: işçi, ön kontrol ve denetçi her seferinde bağlamı sıfırdan kurar; bağlam aktarılırken bilgi kaybolur. Bu bedeli yalnız paralellik, bağlam ayrımı ya da bağımsız denetim kazandırıyorsa öde.
  - Doğrudan (kart açma):
    - soru-cevap, açıklama, durum özeti yap;
    - ana ajanın zaten okuduğu bağlamda tek dosyalık, tek adımlık küçük düzenlemeyi kendin yap (koddaysa ilgili testi koş);
    - kod dışı, en çok 2 dosyalık işi (belge, README, ayar, todo) kendin yap; kanonik belge ve dış teslim hariç;
    - hazır betiği ya da skill'i bir kez çalıştır, sonucu aktar;
    - orkestra bakımını (todo, niyet, kart durumu) kendin yap.
  - Orkestra (`/orkestra:is`) kullan:
    - üç ya da daha fazla dosya veya bağımsız parça varsa (paralel kazanç);
    - birden çok dosyaya dokunan kod değişikliğinde;
    - hatası pahalı çıktıda: dış teslim, nihai ya da kanonik belge, DB ölçüm sonucu, iddia kararı, Jira story (bağımsız denetim için);
    - geniş tarama ya da çok dosya okumada (ana ajanın bağlamı şişmesin diye araştırmacıya ver).
  - Kuşkuda: ana ajanın bağlamı büyükse (≳150k) işi kısa bir kartla ucuz basamağa ver. Bağlam küçükse ve iş tek adımlıysa doğrudan yap.
  - Doğrudan yapılan işte denetçi yoktur. "Onaylandı" deme; neyi nasıl doğruladığını (test, yeniden okuma) söyle.

## Maliyet basamakları
- T0: hazır betik. T1: Haiku. T2: Sonnet. T3: Opus medium (planlama burada). T4: Opus xhigh.
- Bir işe izin veren en düşük basamakla başla.
- Yükseltmeyi denetçi reddi tetikler.
- Kart başına ajan tavanı vardır (varsayılan 8; workflow `args.kart_ajan_tavani`). Tavan dolan kart `tavan` sonucuyla durur; ana ajan nedeni okuyup kartı `beklemede` yapar, yeniden koşturmaz.
- Kart kilidi: teslim/onaylı/iptal kart ve başka ajanda işlenen kart yeniden işlenmez (`kart durum isleniyor` çıkış 6). Aynı kartı iki koşuya verme.

## Denetim
- Her işçi çıktısını ayrı bir denetçi (`orkestra:denetci`) incelesin. Kimse kendi işini onaylamaz.
- Denetçi işçiyle aynı modelde koşsun (T2 işi, Sonnet denetçi).
- Opus denetçi yalnız T3-T4 işlerinde ve kartta ikinci retten sonra kullan.
- Test ve T0 ön kontrol (`on_kontrol.py`: yeni test hatası, CRLF/BOM, kapsam dışı yazma, eksik token) ajan değildir: işçinin `kart durum is-bitti` çağrısında CLI koşar. Geçmezse is-bitti kaydedilmez ve işçi aynı oturumda düzeltir; denetçi çağrılmaz.
- Denetçi testi yeniden koşmaz; CLI kaydına ve diff'e bakar.
- Kart başına testler `test_alani` dosyalarıyla sınırlıdır (geniş komut otomatik daralır); tam paket iş sonunda bir kez koşar, kart başına değil.
- Test-önce (test yazarı + kırmızı kapı) yalnız riskli kod kartında (`tdd: true`): davranış değişikliği olan çok dosyalı ya da kanonik mantık. Diğer kod kartında işçi kodu ve testi birlikte yazar.
- Yeniden denetim yalnız önceki retteki karşılanmayan kriterlere ve gerilemeye baksın.

## Dağıtım
- Bağımsız işleri paralel koştur.
- Paralel işlerin yazma alanları kesişmesin.
  - Yazma alanı kesişen (aynı dosyayı değiştiren) işlere zincir kurma; tek kartta birleştir, kriterler ayrı satır olsun.
  - Birleşik kart 8 kriterden fazlaysa en çok 2 kartlık zincire böl.
  - Mantıksal bağımlılık (çıktısını okuma) ile dosya çakışmasını ayrı değerlendir; yalnız çıktısını bekleyen iş bağımlılık olur.
- Kart dağıtımını varsayılan olarak `Workflow` aracıyla `orkestra:calistir` üzerinden yap.
- Workflow kullanılamazsa kartları elle dağıt.
- Workflow izni yalnız orkestra kartı dağıtımı içindir; başka iş türlerine genişlemez.

## Defterler
- Ortak defter `.claude/orkestra/ortak_defter.md`: herkes ne yaptığını yazar (hook otomatik düşer).
- Defteri elle düzenleme. Tamamını okuma; ihtiyacın olanı `orkestra defter baglam <id>` ile oku.
- Token ve maliyet defteri `.claude/orkestra/maliyet.jsonl` (ajan x süreç x model). Rapor için `/orkestra:maliyet`.
- Paralel oturumlar ortak dosyaya yazmadan önce dosyayı yeniden okusun ve yalnız sona eklesin.

## Kapsam ve ayarlar
- Ayarlar bilgisayara değil çalışma alanına özgüdür: yeni ayarı genel dosyaya değil `<proje>/.claude/settings.json` içine yaz.
- Eklentileri proje kapsamında (`--scope project`) kur. Genel ayar dosyasını boş tut.
- Orkestrasyon projeden bağımsızdır. Eklenti koduna ve belgelerine projeye özgü bilgi girmez.
- Bir projeye orkestra kurulacaksa yalnız `araclar/projeye_kur.py <proje>` çalıştır; projenin alan işine geçme.
- Orkestra işi istendiğinde görev yalnız çok ajanlı orkestrasyonu kurmaktır; kapsam dışına çıkma.

## Yöntem seçimi
- Birden çok yol varsa en az token harcayan, en verimli yolu öner ve seç.
- Seçenekleri maliyetine göre sırala; en ucuzunu önerilen olarak işaretle.
- Tercih sırası:
  1. Kullanıcının bir kez yaptığı dışa aktarım (CSV) + yerel betik (T0) + yalnız özeti okuma.
  2. API ya da MCP çağrısı; sonucu bağlama almadan önce betikle süz ve topla.
  3. Tarayıcıda sayfa içi JS ile toplanmış sonuç.
  4. Sayfa metni ya da ekran görüntüsü okuma (son çare).
- En ucuz kanıt: soruyu cevaplayan en dar ölçümle başla (ör. "kolon var mı" varlık kontrolü, sayımdan ve tam taramadan önce). Genişletmeyi yalnız kullanıcıya sorarak yap.
- Toplu sınıflamada kuralları ana ajan yazsın, satırları Haiku işlesin.
- Tespit ve düzeltmeyi önce deterministik Python kurallarıyla kur (kod, regex, sayaç, oturum bağlantısı).
- LLM'i yalnız kuralla ayrılamayan belirsiz durumlarda kullan.
- Kuralları mevcut LLM etiketleriyle karşılaştırarak doğrula.

## Odak ve sıradaki adımlar
- Her sohbet ilk işte bir işe bağlanır: mevcut işse `orkestra is devam <id>`, yeni işse `orkestra is ac <başlık> --klasor <görev klasörü>`. Sıradaki adımlar sohbet hafızasında değil işin todo.md'sinde tutulur: ortaya çıkınca `orkestra is todo <id> --ekle "…"`, bitince `orkestra is todo <id> --bitti <n|parça> [--not]`; yeni sohbet listeyi oradan okuyup devam eder.
- Yanıt sonunda "sıradaki adım" yazma.
- Sıradaki adımları `orkestra is todo <id> --ekle` ile işin `todo.md` dosyasına yaz.
- Yalnız kullanıcıdan karar ya da onay gerekiyorsa bunu tek cümleyle söyle.
