# Orkestra: insanlar için kılavuz

Bu dosya orkestrayı ilk kez gören biri içindir. Okuyunca ne olduğunu, nasıl kurulduğunu, nasıl kullanıldığını ve takıldığında nereye bakacağını bilirsin. Ayrıntı gereken her konuda ilgili belgeye bağlantı vardır.

## 1. Orkestra nedir

Orkestra, Claude Code içinde çalışan bir iş yönetim ve denetim sistemidir. Çok adımlı bir işi planlar, parçalara böler, ucuz modelle yaptırır ve her çıktıyı ayrı bir denetçiye kontrol ettirir.

Dört fikir üzerine kuruludur:

- **Maliyet merdiveni:** Her iş izin veren en ucuz basamakta başlar. Sıra: betik → Haiku 5.5 → Sonnet 5.5 → Opus 5.5 medium → Opus 5.5 xhigh.
- **Ayrı denetçi:** İşi yapan kendi işini onaylayamaz. Onayı ayrı bir denetçi ajan verir.
- **Kalıcı kayıt:** Her iş kendi klasöründe belge bırakır: mevcut durum, plan, todo, çalışma özeti. Sohbet kapansa da iş kaybolmaz.
- **Kapılar:** Onaysız uygulama, kanıtsız todo, ADR'siz kapanış gibi hatalar kod düzeyinde engellenir.

Orkestra yalnız Claude Code içinde çalışır. Cursor ya da başka editörlerin kendi ajanları eklentiyi yüklemez, ama o editörlerin terminalindeki Claude Code kullanır.

## 2. Kurulum

Gereksinimler:

- Claude Code, kurulu ve oturum açılmış.
- Python 3 (`python` komutu PATH'te olmalı).
- `git` ve eklenti deposuna okuma erişimi.
- `pytest` (test kapısı için): `python -m pip install pytest`.

Bütün projelere kurmak için eklenti deposunda tek komut yeter:

```bash
python <depo>/araclar/projeye_kur.py --kullanici
```

Tek projeye kurmak için:

```bash
python <depo>/araclar/projeye_kur.py <proje klasörü>
```

Her iki komutta önce `--kuru` ile ne yapılacağını görebilirsin. Kurulumdan sonra o projede yeni bir Claude oturumu aç. Orkestra projede kendiliğinden açılır, `.claude/orkestra/` durum klasörünü kurar.

Kaldırmak için aynı komuta `--kaldir` ekle. Tam kurulum ayrıntısı (özel GitHub deposu, kimlik doğrulama, yayın klonu): [plugin_yayin/README.md](../../README.md).

## 3. İlk işin: başlangıçtan kapanışa

Her sohbet bir işe bağlanır. Yeni iş açmak için:

```bash
orkestra is ac "Kısa iş başlığı" --klasor <görev klasörü>
```

Açık bir işe dönmek için `orkestra is devam <id>` kullan. Büyük işler `/orkestra:is <istek>` ile de başlatılır.

İş şu sırayla ilerler:

- **Mevcut durum:** Ajan önce var olanı okur ve `mevcut_durum_<tarih>.md` dosyasına yazar. Sonuna hedef ile mevcut arasındaki farkları (gap) ekler.
- **Plan:** `plan.md` her maddeye ölçülebilir kabul ölçütü ve geri alma yolu yazar. Plandaki iddialar kanıtla doğrulanır (`orkestra plan dogrula <id> --yaz`).
- **Todo:** `todo.md` plan maddelerinden türer. Bir madde ancak kanıt notuyla bitirilir.
- **Onay:** Sen onaylayana kadar kod, dosya değişikliği, commit ve bağımlılık ekleme yapılmaz.
- **Uygulama:** Parçalar işçilere dağıtılır, her çıktıyı ayrı denetçi inceler.
- **Kapanış:** `orkestra is kapat` çalışma özetini ister. Plandaki her madde ve gap için durum ve kanıt yazılmış olmalıdır.

İki çalışma modu vardır:

- **/plan (varsayılan):** Üç belge hazırlanır, sen onaylayınca iş başlar.
- **/auto:** Mesajın onay yerine geçer, iş sonuna kadar koşar. Kesin sınırlar yine geçerlidir. Sana ait işler (parola, push kararı) çalışma özetinde "Kullanıcıya kalanlar" bölümüne düşer.

## 4. Hangi iş için hangi komut

| Yapmak istediğin | Komut ya da skill |
|---|---|
| Çok adımlı işi yürüt | `/orkestra:is <istek>` |
| Bu projede orkestrayı aç | `/orkestra:baslat` |
| Sohbetin neresinde olduğunu öğren | `/orkestra:neredeyiz` |
| Sohbeti yeni sohbete taşı | `/orkestra:devir` |
| Sohbet bitmeden açık kalanları gör | `/orkestra:close` |
| Maliyet raporu | `/orkestra:maliyet [gün]` |
| Ortak defterin son kayıtları | `/orkestra:defter` |
| Panelde onayladıklarını uygula | `/orkestra:onay` |
| Hafıza bakımı raporu | `/orkestra:perspektif` |
| Tekrar eden işten skill taslağı | `/orkestra:skill-avi` |
| PR, commit, dal, Jira yorumu standardı | `/orkestra:standart` |
| Tabloyu sade Excel'e çevir | `/orkestra:sade-excel` |
| Yüzlerce satırı toplu etiketle | `/orkestra:toplu-etiketle` |
| Eklentiyi güncelle | `/orkestra:update` ya da `orkestra update` |

Terminalden sık kullanılanlar:

- `orkestra is liste` açık işleri listeler.
- `orkestra is baglanti <id>` işin belge bağlantılarını verir.
- `orkestra is todo <id> --bitti <n> --not "kanıt: ..."` madde bitirir.
- `orkestra kart liste` görev kartlarını gösterir.
- `orkestra doktor` kurulumu denetler, `--duzelt` onarır.
- `orkestra harita oku` projenin sistem haritasını (sır yerleri, dış bağlantılar, modüller) basar.
- `orkestra --help` bütün komutları listeler.

## 5. Panel

Panel, tarayıcıda açılan canlı bir izleme ekranıdır. `orkestra panel` komutuyla ya da `/orkestra-web` ile başlar ve `http://127.0.0.1:8765/` adresinde yalnız bu bilgisayardan erişilir.

Sekiz sayfası vardır:

- **Şimdi:** Hangi sohbet ne yapıyor, senden ne bekleniyor.
- **Maliyet:** Ne kadar harcandı, nereye.
- **Verim:** Sistem iyi çalışıyor mu.
- **Onaylar:** Senden karar bekleyenler.
- **Kurallar:** Etkin kurallar, kural önerileri.
- **İşler:** Açık işler ve belgeleri.
- **Etki:** Değişikliklerin etkisi.
- **Yapılacaklar:** Açık işlerin maddeleri ve kendi yapılacakların.

Maliyet tutarları API liste fiyatıyla yapılmış tahmindir. Abonelikte gerçek fatura değil, kota karşılığıdır.

## 6. Kurallar ve kapılar

Orkestra bazı kuralları kendisi zorlar. Bunları bilmek sürprizleri önler:

- **Onaysız uygulama yok:** Onay gelmeden dosya değişikliği, commit ve bağımlılık ekleme reddedilir.
- **Sıra:** Mevcut durum olmadan plan, plan olmadan todo yazılamaz.
- **Kanıt:** Kanıt notu olmayan todo maddesi bitirilemez.
- **ADR:** Mimari ya da kalıcı etkisi olan karar `adr/` klasörüne yazılır. İş, plandaki `**ADR:**` satırı olmadan kapanmaz.
- **Gap:** Mevcut durumdaki her fark ya bir plan maddesine bağlanır ya da gerekçeyle kapsam dışı bırakılır.
- **Push:** Yalnız sen açıkça istersen yapılır. İzin politikası `git push` ve GitHub ya da Jira yazmalarında sorar.
- **Sırlar:** Sır değeri hiçbir belgeye ya da sohbete yazılmaz.

Projeye özgü kural eklemek için `orkestra kural ekle --metin "..."` kullan. Etkin kurallar projede `.claude/rules/orkestra_kurallari.md` dosyasına yazılır. Bu dosyayı elle düzenleme.

Kuralların tamamı ve gerekçeleri: [KURALLAR.md](KURALLAR.md). Bir kapıyı geçici kapatan ortam değişkenleri de orada yazılıdır, ama kapatmak son çaredir.

## 7. Güncelleme ve kaldırma

Güncelleme LLM çağırmaz:

```bash
orkestra update
```

Komut sonucu `GÜNCELLENDİ`, `ZATEN GÜNCEL` ya da `HATA: neden` diye yazar. Ardından yeni oturum aç ya da `/reload-plugins` çalıştır. Elle yapmazsan Claude Code ilk mesajdan sonra en çok 10 dakika içinde kendisi günceller.

Bir projeden kaldırmak için:

```bash
python <depo>/araclar/projeye_kur.py <proje klasörü> --kaldir
```

Bütün projelerden kaldırmak için aynı komuta `--kullanici --kaldir` ver.

## 8. Sorun giderme

- **Komut bulunamadı (`orkestra`):** Eklenti yüklü değildir ya da oturum eskidir. Yeni oturum aç, `/plugin` ile listeyi kontrol et.
- **Yazma reddedildi, "onay bekliyor":** İş henüz onaylanmamıştır. Üç belgeyi gördükten sonra "onaylıyorum" yaz.
- **"Plan doğrulaması yok" uyarısı:** `orkestra plan dogrula <id> --yaz` çalıştır, todo'yu sonra yaz.
- **İş kapanmıyor:** Çalışma özeti eksiktir. Plandaki her P ve gap için durum ve kanıt satırı olmalı.
- **Kurulum şüpheli:** `orkestra doktor` sağlık denetimini yapar.
- **Panel açılmıyor:** `orkestra panel` çıktısındaki adresi kontrol et, 8765 portunu başka program tutuyor olabilir.
- **Test kapısı pytest ister:** `python -m pip install pytest`.

## 9. Daha fazlası

- [plugin_yayin/README.md](../../README.md): kurulum ayrıntısı, panel sayfaları, paralel çalışma, basamak tablosu, bilinen sınırlar.
- [KURALLAR.md](KURALLAR.md): ajanlara verilen kurallar, denetim ve dağıtım ayrıntısı.
- [GELISTIRME.md](GELISTIRME.md): eklentiyi geliştirenler için yayın akışı ve test takımı.
- `standartlar/` klasörü: PR, commit, dal, review ve Jira yorumu standartları.
- `sablonlar/` klasörü: mevcut durum, plan, todo ve çalışma özeti şablonları.
