# Kök neden önce (P-042, ADR-0101)

Sorun, hata ya da sapma anında hook bu standardın iki bölümünü bağlama ekler. Tam protokol: `/orkestra:root-cause-first`. Proje, `<durum dizini>/standartlar/kok_neden.md` ile bölümleri ezebilir.

## Hata anı

Bu mesaj bir sorun ya da hata bildiriyor: düzeltmeden önce kök nedeni bul. (1) Beklenen ile gerçek arasındaki ilk sapmayı kanıtla yerelleştir; belirtiyi yamama. (2) En az iki rakip nedeni say, aralarını ayıran en ucuz kontrolü yap; kanıtlanmamış nedene 'kök neden' deme, 'hipotez' de. (3) Düzeltmeyi sorunun doğduğu sınırda, ilk denemede kalıcı ve best in class yap (K-006); geçici önlem ile kalıcı çözümü ayır. (4) Düzeltmeyi ve gerçek sonucu ayrı doğrula; doğrulama tutmazsa hipotezi yeniden aç. Etki küçükse analiz kısa kalır; planlı değişiklikte kök neden uydurma.

## İşçi görevi anı

Görevde bir hata ya da sapma görürsen: belirtiyi yamama, ilk sapmayı kanıtla yerelleştir, nedeni kanıtla, düzeltmeyi sorunun doğduğu sınırda kalıcı yap ve sonucu ayrıca doğrula. Kanıtlanmamış nedene 'kök neden' deme; görev planlı değişikse kök neden uydurma.

## Araç hatası anı

Araç başarısız oldu: komutu körlemesine yineleme. Hatanın ilk sapmasını oku, nedenini kanıtla, sonra tek hedefli düzeltme yap. Kanıtlanmamış nedene 'kök neden' deme.
