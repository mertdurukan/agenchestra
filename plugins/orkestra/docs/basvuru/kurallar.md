<!-- Bu dosya scripts/dokuman_uret.py ile üretilir; elle düzenleme. -->

# Kurallar

Kaynak: `kurallar/eklenti_kurallari.json` (her projeye yüklenir). Tam metin kaynakta; burada kimlik ve ilk cümle.

| Kimlik | Kural (ilk cümle) |
|---|---|
| K-003 | Okunmak üzere üretilen belgelerden (mevcut durum, plan, todo, bulgu, rapor, özet) yalnız bu turda yeni oluşan ya da içeriği değişen belge, yanıtın sonunda her belge için bir satırla verilir: '<belge türü>: <bağlantı>' ('mevcut durum', 'plan dosyası', 'to-do d… |
| K-004 | İş bağlama ve yeni iş açma kararları kullanıcıya sorulmaz; orkestra en iyi uygulamayla kendisi karar verir. |
| K-005 | Maksimum okunabilirlik için hem sohbette hem de oluşturulan her belgede (plan, todo, çalışma özeti, bulgu, jira_onerisi, rapor) şu düzen uygulanır: (1) Başlık ve ona bağlı etiketli alanlar (Amaç, Arıza sınıfı, Neden, Kanıt, Durum gibi) ayrı paragraflarda alt … |
| K-006 | Her hata, kusur ya da ret nedeni kök nedene inilerek çözülür; sorun oluştuğu yerde, oluşmadan önlenir. |
| P-001 | Yanıt, sorunun ağırlığı kadardır. |
| P-002 | Bilgi sorusuna ('ne demek', 'nedir', 'neden', 'gerekir mi') en çok 5 cümleyle cevap verilir; iş durumu, tablo, kaynak taraması ve alt ajan eklenmez. |
| P-003 | Her işin tek todo'su işin klasöründeki todo.md dosyasıdır ve orkestra is todo ile yönetilir. |
| P-004 | Her işin planı işin klasöründeki plan.md dosyasıdır; plan başka adlı bir dosyaya yazılmaz. |
| P-005 | Her işin tek plan dosyası işin klasöründeki plan.md, tek todo dosyası todo.md'dir (todo orkestra is todo ile yönetilir); kopya liste ya da başka adlı plan tutulmaz, uzun ek analiz ayrı dosyada durabilir ama plan.md'den bağlanır. |
| P-006 | Commit'ler yerelde değişiklikleri kayda almak içindir (otomatik commit'ler dahil). |
| K-007 | Başlatılan her yan oturum, başladığı anda aynı turda üst oturumdan ayrılarak kullanıcının kenar çubuğunda ayrı sohbet olarak görünür (start_session sonrası detach_session). |
| P-007 | Sohbette ve belgelerde 'kendi sunucumuz', 'bizim kod', 'bizim sürüm' gibi belirsiz sahiplik ifadeleri kullanılmaz; ilk yazımda somut ad yazılır: adres, sürüm, dosya yolu, paket, tablo ya da müşteri adı. |
| P-008 | Kullanıcıya 'senin yapman gerekenler' listesi yazmadan önce her madde sınanır: elimde araç, anahtar, API ya da tarayıcı varsa işi kendim yaparım. |
| P-009 | Bir iş (görev) tamamen kapanıyorsa kapanıştan önce görev bitiş raporu yazılır: işin klasöründe doldurulmuş calisma_ozeti_<YYYYMMDD>.md (orkestra is belge <id> ozet; Ana bulgu boş olamaz, ölçülen sayılar komutla, doğrulanmayanlar ve açık işler dahil). |
| P-010 | Halka açık ve geri alınamaz eylemler kullanıcı açıkça istemedikçe yapılmaz, istenmemişse sorulur (kullanıcı eylemi açıkça istediyse, ör. |
| P-011 | Panelde iki ayrı yerde süren arka plan görevleri gösterilir. |
| P-012 | Sohbet tek aktif sorunla ilerler. |
| P-013 | Dosya temizliğinde tek arşiv vardır: <proje>/_arsiv/<proje adı>/<orijinal göreli yol>. |
| P-014 | Kullanıcıya yazılan yanıtta modelin iç karar ve sınıflandırma cümleleri bulunmaz: 'bilgi sorusu, aynı işin devamı', 'kısa cevap', 'K-004 gereği', 'hook şunu istiyor' gibi süreç anlatımı yazılmaz. |
| P-015 | Orkestra projesinin kendisi ve orkestranın açık olduğu her proje için Architecture Decision Record (ADR) tutulur. |
| P-016 | Bir işe başlanınca (orkestra is ac ya da is devam) kullanıcıdan açık onay gelmeden uygulamaya geçilmez: kod/dosya değişikliği, commit ve bağımlılık ekleme yapılmaz. |
| P-017 | Orkestra'da gap analizi (hedef durum ile mevcut durum arasındaki fark) iki geçişlidir ve plan bunsuz tamam sayılmaz. |
| P-018 | Mevcut durum, plan, todo ve çalışma özeti belgeleri ortak bir kalite çıtasına uyar (best in class). |
| P-019 | Her projede betikle üretilen kalıcı bir sistem haritası vardır (.claude/orkestra/sistem_haritasi/: sır ve yapılandırma yeri, dış bağlantılar, çalışan süreçler, giriş noktaları ve modüller, altyapı, veri modeli, bağımlılıklar, açık iş ve ADR). |
| P-020 | Çalışma modları: kullanıcı bir işe /plan (varsayılan) ya da /auto ile başlar. |
| P-021 | Kullanıcının sorusuna yanıt vermeden önce yanıt mevcut duruma ve kod tabanına göre doğrulanır. |
| P-022 | Her projede geçerli olabilecek davranış (skill, hook, betik, kural, komut) önce orkestra eklentisinin asıl kaynağında genel biçimde yazılır: yollar ve adlar ayardan gelir, projeye özgü ad (müşteri, klasör, tablo) kodda bulunmaz. |
| P-023 | Bir iş için kimlik, anahtar ya da bağlantı dizesi (ör. |
| P-024 | Bir projedeki tüm teknolojilerin envanteri (ui, backend, ai, llm, veri, altyapı, gözlemlenebilirlik, test/araç) orkestra davranışıdır, elle yazılan md değildir. |
| P-025 | Kullanıcı sohbete parola, belirteç ya da bağlantı dizesi yapıştırırsa hook değeri kimlik klasörüne alır; ajan o değeri yanıtta, belgede, hafızada, komut satırında ya da alt ajan kartında yinelemez ve alıntılamaz. |
| P-026 | Düzeltilen bir iddia kaynak kayıtta bir kez yeniden yazılır; düzeltme notu çoğaltılmaz. |
| P-027 | Orkestra paneli her Windows kurulumunda oturumdan bağımsız bir Task Scheduler görevi ('Orkestra Panel') olarak çalışır; elle ya da oturum hook'uyla başlatılan arka plan süreci olarak bırakılmaz. |
| P-028 | Yeni kontrol kapıları (görev sözleşmesi, teslim, izole ortam ve sonrakiler) önce 'golge' modunda açılır: eksik uyarılır ve gunluk.jsonl'a 'kapi_golge' olarak yazılır, iş engellenmez. |
| P-029 | Gerçek karar noktalarında kullanıcıya düz metin yerine seçim ekranı sunulur. |
| P-031 | Kullanıcıdan bir şey istendiğinde ajan sırayla çalışır: (1) kaynakları tarar, (2) kaynaklar arasındaki çelişkileri belirler, (3) sentezler. |
| P-030 | Her türlü iş ve süreçte (Jira story, plan, kod, ölçüm, belge) çözüm best in class düzeyinde olur. |
| P-032 | Kullanıcıya giden bir LLM çıktısının kısıtları (söylenmeyecek şey, zorunlu uyarı, sayı ve kaynak, kapsam dışı konu reddi) kodla zorlanır: giriş sınıflandırması, araç çıktısının daraltılması ve LLM yanıtının gönderilmeden önce deterministik doğrulanması; ihlal… |
| P-033 | Her plan maddesi sorunun doğduğu yeri ve orada önleyici çözümü yazar; doğru yön üretildiği noktada sağlanır, sonradan yakalanmaz (K-006). |
| P-034 | Çalışma özeti başlığı yalnız Jira kodu ya da genel ifade olmaz ('<KOD> çalışma özeti' yazılmaz). |
| P-035 | Sıralı işte bağımsız plan maddeleri paralel koşar; sıralılık gerekçelendirilir (taban ölçüm: kayıp plan ve kart aşamasında). |
| P-036 | "Erişim yok" hatırlatması yalnız cümle kimlik, anahtar ya da bağlantı dizesi sözcüklerinden birini içerdiğinde tetiklenir; bir aracın kurulu olmadığını söyleyen cümle kimlik eksikliği sayılmaz. |
| P-037 | Oturum süresi eşiği yalnız bir önceki pencerenin p95'inden türetilmez; sabit bir alt sınır konur, böylece pencere uzadıkça eşik de kaymaz. |
| P-038 | Tur süresi ölçümünden kullanıcı onayı bekleme ve arka plan görev süreleri çıkarılır; aksi halde bekleme süresi, ajanın gerçek çalışma süresi gibi görünür. |
| P-039 | Ana ajan maliyet payı kart başına değil işe göre izlenir; pay eşiği aşıldığında uzun, tekrarlanabilir ve mekanik adımlar işçi basamağına devredilir. |
| P-040 | ADR, kararın etkilediği depoda yazılır; hedef depo planın **Kök:** satırının git deposudur (Kök yoksa işin projesi). |
| P-042 | Sorun, hata ya da sapma anında önce kök neden bulunur, çözüm ilk denemede kalıcı ve best in class yapılır. |
| P-043 | Kullanıcıya terminalde çalıştırması için verilen her komut, kullanıcının kabuğunun sözdizimiyle yazılır. |
| P-044 | Kullanıcıya görünen sonuç isteyen her iş (yerleşim, hizalama, konum, görünüm; küçük ve sözleşmesiz işler dahil) iki adımla yürür. |
| P-045 | Her çıktı, tabi olduğu denetimin kuralını yazılmadan önce görerek üretilir; sorun üretildiği yerde, önleme merdiveninin en üst uygulanabilir basamağında çözülür, sonradan yakalama yalnız güvenlik ağıdır. |
| P-048 | Kullanıcının sohbet sorusuna yanıt vermeden önce aday yollar sayılır: ilgili skill (yaklasim), SearchSkills/ToolSearch ile MCP aracı, kod ya da canlı kayıt, resmi belge; en ucuz yeterli yol seçilir, yanıt doğrudan kod yazmakla başlamaz. |
| P-046 | Her codebase kendi kilitli ortamında kurulur ve komutlar o ortamdan koşar; ortam proje ve git dışındadır, sır taşımaz. |
| P-047 | Her sohbette konuşulan konular saniyeli zamanla kalıcı kaydedilir ve izlenebilir. |
| P-049 | Aynı depoda eşzamanlı çalışan oturumlar birbirini kendiliğinden görür; bunun için ikinci bir kayıt kurulmaz. |
| P-050 | Belgeler üretilip tamamlandıktan sonra, plan ya da auto modu fark etmeden, şu sırayla kullanıcıya verilir. |
| P-051 | Veritabanı, kod, komut ya da API ile bakılabilen hiçbir şey belgede "Doğrulanamayanlar" bölümüne yazılmaz; belge yazılmadan önce bakılır. |
| P-052 | İşte iki yol varsa (örn. |
| P-053 | Ajanın kullanıcıya sorduğu her soru kalıcı kaydedilir ve yanıtlanana kadar kaybolmaz; karar soruları her zaman düğmeyle sunulur. |
| P-055 | Ajan denetçiyi ya da başka bir süreci beklerken boş durmaz; beklerken başlatılabilecek bağımsız işler mekanik belirlenir. |
| P-056 | Her sohbet yanıtı ve her plan maddesi, etkilediği kararı ve en az bir uygulanabilir rakip yaklaşımı (mevcut skill, hook, kural dahil) çıkarmadan verilmez; mevcut plana ya da belgeye çıpalanılmaz. |
| P-057 | Eklenti deposunda (Desktop\Claude-Orchestration, uzak mertdurukan/agenchestra) iş şu akışla yayınlanır: iş kendi dalında commitlenir; hedefli testler geçince dal origin/main üzerine alınır, yerelde main'e fast-forward birleştirilir ve main push edilir. |
| P-058 | Kullanıcıya verdiğin her sayı, 'var/yok', 'doğrudur/yanlıştır' ve değerlendirme iddiası yazılmadan önce ilgili kaynaktan bu turda komutla doğrulanır; hatırlayarak, konuşma geçmişinden ya da varsayımdan sayı ve değerlendirme yazılmaz. |
| P-059 | Oturumda yapılacak başka iş ve konuşulacak konu kalmadığında kapanış kutusu (wrap_up) tek düğme taşır: uygulamanın Arşivle eylemi (actions=[{"action":"archive"}]); kullanıcı basınca sohbet arşivlenir ve plan listesi 'devam ediyor' diye takılı kalmaz. |
| P-060 | Push öncesi test şartı yalnız repoda GitHub CI/CD (.github/workflows) varsa geçerlidir ve yalnız değişen alanın hedefli testlerini (tek dosya, düğüm, -k) kapsar; tam takım şart değildir, tam takımı CI koşar. |
| P-061 | Kodlama davranışı (Karpathy ilkeleri, MIT, multica-ai/andrej-karpathy-skills): (1) Kodlamadan önce düşün: varsayımı açık yaz, birden çok yorum varsa sessizce seçme, daha basit yol varsa söyle; belirsizse tahmin yerine sor. |
