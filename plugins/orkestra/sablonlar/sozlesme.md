# {baslik}: sözleşme ve rapor

<!-- ADR-0136: tek belge iki aşamalıdır. İşin başında yalnız Problem, Başarı kriterleri, Kapsam dışı ve Kısıtlar yazılır (iç kayıt, kullanıcıya verilmez). İşin sonunda Sonuç, Öneriler ve Karar bekleyen konular eklenir ve belge çalışma özetinden sonra verilir. Bu belge işin neyi çözeceğini ve ne zaman bitmiş sayılacağını sabitler; kullanıcı mevcut durum, plan ve todo ile birlikte tek onayla kabul eder. Yazım kuralları (tüm belge):
1. Her ayrı ifade ayrı bir satırdır (madde işareti ya da numara ile); bir satırda en çok bir cümle, ~200 karakter.
2. Başlık hiyerarşisi: `##` ana başlık, `###` alt başlık; kalın etiket başlık yerine kullanılmaz, yalnız alan adı olarak kullanılır.
3. Belirsiz sahiplik ("bizim kod", "kendi sunucumuz") yazılmaz; somut ad yazılır (adres, sürüm, yol, tablo, müşteri).
4. Tablo ve kod bloğu yok. -->

## Problem

<!-- doldur: her ifade ayrı satır.
- İlk satır Sonuç etiketiyle: ne istendi ve ne bitince iş tamam sayılır (tek cümle).
- Sonra: çözülecek sorun ya da istek, kullanıcının sözleriyle.
- Ölçülebilir etkisi (sayı, ölçüm saati, kaynak).
- Sorunun doğduğu yer (dosya, süreç, tablo). -->


## Başarı kriterleri

<!-- doldur: her kriter ayrı satır ve ölçülebilir; tam bu biçimde, S numaraları sabittir (plan Kabul'u buna bağlanır):
- **S1:** kriter (komut çıktısı, sayı ya da dosya:satır ile sınanabilir) -->


## Kapsam dışı

<!-- doldur: bu işte bilerek yapılmayan her şey ayrı satır ve nedeni; yoksa tek satır: "Yok". -->


## Kısıtlar

<!-- doldur: uyulacak kural, sınır, süre ya da bütçe, her biri ayrı satır ve kaynağı (kural kimliği, ADR, kullanıcı mesajı); yoksa tek satır: "Yok". -->


## Sonuç

<!-- doldur (yalnız işin sonunda):
her başarı kriteri ayrı satır, tam bu biçimde: `- **S1:** Karşılandı | Kısmen | Karşılanmadı — kanıt (komut çıktısı, sayı ya da dosya:satır)`.
İlk satır `**Sonuç:**`: işin sonucu, tek cümle ve ana sayı. -->


## Öneriler

<!-- doldur (yalnız işin sonunda): her öneri ayrı alt başlık `### <öneri adı>`.
Altında üç satır:
- **Öneri:** ne yapılacak
- **Neden:** hangi bulguya dayanıyor
- **Etkisi:** yapılırsa ve yapılmazsa ne olur
Öneri yoksa tek satır: "Yok". -->


## Karar bekleyen konular

<!-- doldur (yalnız işin sonunda): yalnız kullanıcının vermesi gereken kararlar; her karar ayrı madde, seçenekleri ayrı alt madde. Yoksa tek satır: "Yok". -->
