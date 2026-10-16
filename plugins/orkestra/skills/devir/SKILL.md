---
name: devir
description: "Bu sohbeti sıfır bağlamlı yeni bir sohbete kayıpsız devreden, yapıştırılmaya hazır bir devir belgesi üretir: güncel hedef, kısıtlar, kesinleşmiş kararlar, elenen seçenekler, mevcut durum, birebir taşınması gereken içerik, dosyalar ve ilk hamle. Şu ifadelerde mutlaka kullan: '/orkestra:devir', '/yeni-sohbet', 'yeni sohbet', 'yeni sohbet aç', 'yeni sohbete geç', 'devret', 'devir', 'devir belgesi', 'yeni sohbete taşı', 'yeni sohbette devam edelim', 'başka sohbete geçelim', 'sohbet çok uzadı', 'context doldu', 'bağlam doldu', 'handoff', 'hand off', '/devir'. Kullanıcı sohbetin yavaşladığından, uzadığından veya Claude'un baştaki şeyleri unuttuğundan yakınıp devam etmek istediğinde de öner. Kullanıcı yalnızca kendisi için durum özeti istiyorsa ('nerede kaldık', 'özet geç') KULLANMA; o iş neredeyiz skill'inindir."
---

## Amaç

Çıktının okuyucusu kullanıcı değil, **bu sohbeti hiç görmemiş yeni bir Claude**'dur. O Claude yalnızca devir belgesini (ve eklenen dosyaları) görür. Belge bu yüzden özet değil, çalışma emridir: yeni sohbet ilk mesajından itibaren, eskisi hiç kesilmemiş gibi devam edebilmeli.

**Yeterlilik testi** (göndermeden önce uygula): Bu belgeyi sıfır bağlamla okuyan yetkin biri, kullanıcıya tek bir soru sormadan "İlk hamle"yi doğru yapabilir mi? Yapamıyorsa eksik olanı ekle.

## Çalışma sırası

1. **Tüm sohbeti tara**, yalnızca son mesajları değil. Uzun sohbetlerde en çok baştaki kısıtlar ve ortadaki karar değişiklikleri kaybolur. Sohbetin başı sıkıştırılmış/özetlenmiş görünüyorsa oturum dökümüne bak (Claude Code: `~/.claude/projects/<proje>/<oturum>.jsonl`; claude.ai ve kod çalıştırma açıksa `/mnt/transcripts`); döküm varsa baştaki kısıtları ve kararları oradan doğrula. Başa erişemiyorsan bunu belgenin "Bilinenler" bölümünde açıkça yaz ("sohbetin ilk kısmı görülemedi; şu maddeler özetten alındı"); eksik görüşü tam görüş gibi sunma.
2. **İşin türünü belirle** ve aşağıdaki "Türe göre ek yük" tablosundan ilgili satırı uygula. Tek şablon her işe yetmez: bir hata ayıklama devrinde ortam bilgisi, bir yazı devrinde ses örneği eksikse devir kâğıt üzerinde tam görünür ama yeni sohbet tökezler.
3. **Son geçerli durumu çıkar.** Bir karar sonradan değiştiyse yalnızca son halini yaz; tarihçeyi taşıma. Hedef kaydıysa güncel hedefi yaz, başlangıç hedefini ancak hâlâ bağlayıcıysa an.
4. **Kanıt durumunu ayır.** Kaynakla doğrulananı, kullanıcının beyanını ve senin varsayımını birbirine karıştırma; yeni sohbet varsayımı gerçek sanarsa hata sessizce büyür.
5. **Dosyaları envanterle.** Claude Code'da bu oturumda değişen ya da üretilen dosyaları yol olarak yaz (yeni oturum aynı klasörü görür; yoldan okur). claude.ai'da ve kod çalıştırma açıksa `/mnt/user-data/outputs` ve `/mnt/user-data/uploads` içeriğini listele; yeni sohbet bunları göremez, kullanıcının yeniden eklemesi gerekenleri adıyla yaz.
   - Oturum bir orkestra işine bağlıysa iş kimliğini, klasörünü ve açık todo maddelerini (`orkestra is devam <id>`) 5. bölüme yaz.
6. **Belgeyi şablona göre yaz**, soğuk okuma yap (aşağıda), teslim et.

Devir için soru sorma; devir anı kullanıcının zaten yorulduğu andır. Sohbette birden fazla bağımsız iş varsa aktif olanı devret, diğerlerini "Kapsam dışı" altında tek satırla an. Kullanıcı `/orkestra:devir <konu>` (ya da `/yeni-sohbet <konu>`) derse o konuyu devret.

## Türe göre ek yük

Temel şablon karar/proje işlerine göre kuruludur. İşin türüne göre şunları ilgili bölüme (çoğunlukla 5, 6 veya 7) ekle; birden fazla tür varsa hepsini uygula.

| İş türü | Yoksa devrin kırılacağı şey |
|---|---|
| Kod / hata ayıklama | Ortam (dil, sürüm, işletim sistemi, bağımlılıklar), yeniden üretme adımları, hata mesajının tam metni, elenmiş hipotezler, son çalışan hal, dosya yapısı |
| Yazı / yaratıcı iş | Hedef kitle ve ton, **sesi gösteren 1-2 birebir paragraf**, kullanıcının reddettiği ifadeler/üsluplar, metnin son tam hali, yapı planı |
| Araştırma / analiz | Araştırma sorusu, taranan kaynaklar (URL + tarih + ne söylediği), çözülmemiş çelişkiler, bakılıp boş çıkan yerler (tekrar bakılmasın), henüz bakılmamış yerler |
| Öğrenme | Kullanıcının mevcut seviyesi, oturan kavramlar, takıldığı nokta, **işe yarayan** açıklama biçimi/benzetme, işe yaramayanlar, sıradaki konu |
| Karar / strateji | Karar kriterleri ve ağırlıkları, seçeneklerin son durumu, kararı değiştirecek koşul, bekleyen dış bilgi |
| Veri / tablo | Dosya şeması (sütun adları, birimler), yapılmış temizlik/dönüşümler, kesin ara sonuçlar, hesap yöntemi |
| Uzun süreli kişisel/danışma sohbeti | Kullanıcının kendi ifadesiyle durumu ve hedefi, hassas olduğu noktalar, işe yarayan yaklaşım; yorum ve teşhis ekleme |

Hedef ortam claude.ai'da yeni bir sohbet değilse (Claude Code, başka bir model, bir insan) üstteki talimat kutusunu o okuyucuya göre yeniden yaz ve `/mnt/...` gibi ortama özgü yolları çıkar.

## Ne taşınır, ne taşınmaz

**Taşı:**
- Kararlar + tek satır gerekçe. Gerekçe olmazsa yeni sohbet kararı iyi niyetle yeniden tartışmaya açar.
- Elenen seçenekler + neden elendiği. Olmazsa yeni sohbet aynı önerileri tekrar getirir.
- Denenip başarısız olanlar ve hata belirtisi (teknik işlerde hata mesajının kendisi).
- Bu sohbette ortaya çıkan kullanıcı tercihleri (ton, format, derinlik, sevmediği şeyler).
- Doğrulanmış kritik olgular; kaynak adı/URL ve tarihle. Güncelliği önemli olanlara "şu tarihte doğrulandı" notu düş ki yeni sohbet gerekirse tazelesin.
- **Birebir içerik:** üzerinde çalışılan metnin/kodun/prompt'un son hali, kesin sayılar, isimler, sürümler, URL'ler, komutlar. Bunları asla tarif etme ("bir taslak yazdık" işe yaramaz); aynen koy. Kısa ise belgenin içine kod bloğuyla, uzunsa dosya olarak.

**Taşıma:**
- Kronolojik anlatı ("önce şunu konuştuk, sonra…"). Yeni sohbetin buna ihtiyacı yok.
- Muhakemenin kendisi; yalnızca sonucu ve tek satır gerekçesi.
- Terk edilmiş hedefler, geçersiz kalmış kararlar, nezaket ve ara konuşmalar.
- Proje talimatları ve kullanıcı tercih ayarları: yeni sohbet aynı projede açılırsa bunlar kendiliğinden gelir. Yalnızca farklı projeye/ortama gidilecekse ilgili kısmı ekle.
- Parola, API anahtarı, token gibi sırlar: yerine `<KULLANICI_GİRECEK>` yaz ve "Dosyalar" bölümünde belirt.
- "Yukarıda konuştuğumuz gibi" türü göndermeler; yeni sohbette "yukarısı" yok. Her madde kendi başına anlaşılır olsun.

Sohbette olmayan hiçbir şeyi ekleme. Emin olmadığını "belirsiz" diye işaretle; boşluğu tahminle doldurma.

## Şablon

Başlıkları bu sırayla kullan. İçeriği olmayan başlığı tamamen sil (boş başlık gürültüdür). Belgeyi sohbetin dilinde yaz.

```markdown
# DEVİR: <iş/konu adı> — <GG.AA.YYYY>

> **Yeni sohbete talimat:** Bu belge önceki bir sohbetin devridir. O sohbeti göremezsin; tek kaynağın bu belge ve ekli dosyalar. Kesinleşmiş kararları yeniden tartışmaya açma, elenenleri yeniden önerme (yeni kanıt yoksa). Belgede olmayanı varsayma; kritikse sor. Bu belgeyi bana geri özetleme: tek cümleyle ilk hamleyi teyit et ve işe başla.

## 1. Hedef
<Güncel hedef, 1-2 cümle. Başarı ölçütü: iş ne zaman "bitti" sayılır? Çıktı ne için kullanılacak?>

## 2. Kısıtlar ve tercihler
<Bütçe, süre, araç, platform, kapsam sınırları. Bu sohbette beliren çalışma tercihleri.>

## 3. Kesinleşmiş kararlar
- <Karar> — <tek satır gerekçe>

## 4. Elenenler ve başarısız denemeler
- <Seçenek/deneme> — <neden elendi / nasıl başarısız oldu>

## 5. Mevcut durum
<Ne bitti, ne yarım, tam olarak nerede duruldu ve neden. Adım listesi varsa: ✅ bitti · 🔄 yarım · ⏳ başlanmadı>

## 6. Bilinenler
- **Doğrulanmış:** <olgu> (<kaynak>, <tarih>)
- **Kullanıcı beyanı:** <olgu>
- **Varsayım (doğrulanmadı):** <varsayım>

## 7. Birebir taşınan içerik
<Son taslak / kod / prompt / kesin sayılar; kod bloğu içinde, değiştirilmeden.>

## 8. Dosyalar
- **Yeni sohbete ekle:** <dosya adı> — <ne olduğu, hangi sürüm>
- **Kullanıcının gireceği sırlar:** <varsa>

## 9. Açık sorular
- <Soru> — <kim cevaplayacak: kullanıcı mı, araştırma mı>

## 10. İlk hamle
<Yeni sohbetin yapacağı ilk somut iş, fiille başlayan tek talimat. Ardından sıradaki en fazla 2 adım.>

## Kapsam dışı
<Bu sohbette geçen ama devredilmeyen işler, tek satır.>
```

## Uzunluk

Hedef: birebir içerik hariç 300-700 kelime. Sınır katı değil; ölçüt yeterlilik testidir. Kısa bir sohbet için 150 kelime yeter, haftalık bir proje için 1000 kelime meşrudur. Şişirme de kırpma da aynı hatadır: yeni sohbetin dikkatini gereksiz satıra harcatma, gereken kararı da esirgeme.

## Teslim

- **Varsayılan çıktı tek bir `.md` dosyasıdır.** Belgeyi `devir-<konu-kisa-adi>.md` adıyla yaz ve yolunu ver. Claude Code'da yer: oturum bir işe bağlıysa işin klasörü, değilse projenin `.claude/orkestra/devir/` klasörü (projenin kendi çıktı kuralı varsa o). claude.ai'da `/mnt/user-data/outputs/`. Kısa da olsa dosya üret; kullanıcı bu komutu "yeni sohbete vereceğim dosyayı ver" anlamında kullanır. Belgeyi ayrıca sohbete yazma; aynı içeriği iki kez göstermek gürültüdür.
- Dosya kendi başına yeterli olmalı: kullanıcı yeni sohbete yalnızca bu dosyayı ekleyip hiçbir şey yazmasa bile yeni Claude ne yapacağını bilmeli. Üstteki "Yeni sohbete talimat" kutusu bu yüzden zorunludur.
- Birebir içerik çok uzunsa (yaklaşık 150 satırdan fazla kod/metin) ayrı dosya(lar) olarak yanına koy ve 8. bölümde adlarını yaz.
- **Yalnızca kod çalıştırma/dosya oluşturma kapalıysa:** belgeyi tek bir kod bloğu içinde ver ki tek tıkla kopyalansın.
- Belgenin ardından kullanıcıya yalnızca şunu söyle (en fazla 3 satır): yeni sohbeti (varsa aynı projede) aç, bu `.md` dosyasını ekle (Claude Code'da yolunu yaz) ve gönder; şu dosyaları da ekle: <liste> (yoksa bu kısmı yazma). Son satır olarak şunu ekle: "Yanlış ya da eksik gördüğün madde varsa söyle, taşımadan önce düzelteyim." Devirde hatayı yakalamanın en ucuz anı burasıdır; yeni sohbette aynı hata sessizce temel olur. Başka açıklama, özet tekrarı veya soru ekleme.

## Soğuk okuma (göndermeden önce zorunlu)

Belgeyi yazdıktan sonra bu sohbeti unuttuğunu varsayarak yalnızca belgeyi baştan oku ve üç soruyu yanıtla:
1. İlk hamleyi yapmak için kullanıcıya hangi soruyu sormak zorunda kalırdım? → Cevabı sohbette varsa belgeye ekle; yoksa "Açık sorular"a yaz.
2. Hangi cümle ancak eski sohbeti bilen biri için anlamlı? (kısaltma, takma ad, "o yaklaşım", "B planı") → Açık haliyle yeniden yaz.
3. Hangi kararı, gerekçesi zayıf göründüğü için yeniden tartışmaya açardım? → Gerekçeyi güçlendir.

Bu adım atlanırsa en tipik hata oluşur: yazan için eksiksiz, okuyan için delik deşik bir belge.

## Son kontrol

- Her karar güncel mi; sonradan değiştirilmiş bir karar eski haliyle kalmış mı?
- Sayılar, isimler, sürümler sohbetteki ile harfi harfine aynı mı?
- Varsayım, doğrulanmış gibi yazılmış mı?
- "İlk hamle" tek ve somut mu, yoksa "devam et" gibi boş mu?
- Yeni sohbetin göremeyeceği bir şeye ("yukarıdaki tablo", "o dosya") gönderme kaldı mı?
- Yeterlilik testi geçiyor mu?
