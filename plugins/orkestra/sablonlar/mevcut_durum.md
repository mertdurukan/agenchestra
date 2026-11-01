# {baslik}: mevcut durum ve bulgular

<!-- Bu belge değişiklikten ÖNCEKİ durumu anlatır: dal, commit edilmemiş iş ya da yapılmış değişiklik burada yer almaz (onaydan önce yazılır, P-016). Yazım kuralları (tüm belge):
1. Her ayrı ifade ayrı bir satırdır (madde işareti ya da numara ile); bir satırda en çok bir cümle, ~200 karakter.
2. Başlık hiyerarşisi: `##` ana başlık, `###` alt başlık (`### 1.1 Ad`); kalın etiket başlık yerine kullanılmaz, yalnız alan adı olarak kullanılır.
3. Kanıt (dosya:satır, komut, sayı) satırın sonunda parantez içindedir.
4. Belirsiz sahiplik ("bizim kod", "kendi sunucumuz") yazılmaz; somut ad yazılır (adres, sürüm, yol, tablo, müşteri).
5. Tablo ve kod bloğu yok; etki haritası madde arar (kapı). -->

## Kapsam ve yöntem

**Amaç:**

<!-- doldur: tek satır: hangi değişiklik planlanıyor. Belgenin ne işe yaradığını anlatan cümle yazılmaz. -->

- 

**Ölçüm saati:**

<!-- doldur: her bilgi ayrı satır, bu iki etiketle (dal ve commit yazılmaz):
- Tarih ve saat: GG.AA.YYYY SS:DD (yerel)
- Depo: ad ya da yol -->

- Tarih ve saat: 
- Depo: 

**Harita:**

<!-- doldur: `orkestra harita oku` çıktısından bu işe dokunan kayıt kimlikleri, her biri ayrı satır (sır yeri, süreç, altyapı, modül); haritada yoksa tek satır: "Haritada yok; taranan yer: <yol>". -->

- 

**Yöntem:**

<!-- doldur: her okuma ya da koşu ayrı satır: ne yapıldı, hangi araçla (dosya okuma, komut, sorgu). Veriyle doğrulanabilen her şey burada çalışılır; bakılmayan şey "Yöntem"de yer almaz, §4'e girer. Yöntemi anlatmayan üst-bilgi cümlesi yazılmaz (örn. "satır numaraları şu tarihteki dosyalara aittir"): kanıt satır numaraları Ölçüm saati'ne bağlıdır. -->

- 

**Sınır:**

<!-- doldur: bakılmayan ya da erişilemeyen her yer ayrı satır ve nedeni; yoksa tek satır: "Yok". -->

- 

## 1. İstek ya da veri hangi yoldan geçiyor

<!-- doldur:
- İlk satır `**Sonuç:**` ile başlar: yol kaç adım, hangi adımda risk var (tek cümle).
- Her yol (örn. V1, V2, tek yol) ayrı alt başlıktır: `### 1.1 <yol adı>`, `### 1.2 …`.
- Alt başlığın altında ilk adımdan son adıma numaralı liste; her adım tek satır, sonunda (dosya:satır). -->

## 2. Bugünkü davranış ve çalışan korumalar

<!-- doldur:
- İlk satır `**Sonuç:**`: mevcut koruma yeterli mi (tek cümle).
- `### 2.1 Çalışan korumalar` ve `### 2.2 Eksik ya da çalışmayan korumalar` alt başlıkları.
- Her madde: `- **koruma adı:** ne yapıyor (kanıt)`; 2.2'de durum açık yazılır: "eksik" (hiç yok) ya da "çalışmıyor" (var ama etkisiz).
- Her iddia dosya:satır, komut çıktısı ya da ölçüm saatiyle desteklenir; kanıtsız iddia yazılmaz. -->

## 3. Etki haritası

<!-- doldur:
- İlk satır `**Sonuç:**`: kaç yere dokunulacak, en riskli hangisi (tek cümle).
- Her dokunulan yer ayrı madde, tam bu biçimde: `- **yer** → bugünkü davranış → dokunmanın riski: düşük | orta | yüksek`. -->

## 4. Doğrulanamayanlar

<!-- doldur: yalnız veriyle, kodla ya da komutla doğrulanması denenip DOĞRULANAMAYAN şeyler girer. Bilinmeyen diye bir bölüm yoktur: bakılabilen her şey §1-§3'te kanıtla yazılır.
- İlk satır `**Sonuç:**`: kaç madde var, hangisi plan öncesi kapanmalı (tek cümle); madde yoksa tek satır: "Yok; gereken her şey §1-§3'te kanıtlandı."
- Her madde ayrı alt başlık değil, üç satırlı madde:
  - **Konu:** neyin doğrulanamadığı
  - **Denenen:** hangi yol denendi (komut, dosya, sorgu)
  - **Engel:** neden doğrulanamadı (erişim, yetki, süre) ve kim kapatabilir -->

## 5. Gap analizi

<!-- doldur (gap'li işlerde zorunlu; plan bu bölümden beslenir):
- Önce `**Hedef durum:**` etiketiyle tek cümle.
- Sonra her gap ayrı satır, tam bu biçimde: `- **G1:** hedef → mevcut (MD §n) → fark`.
- Her satır tek fikir; hedef, mevcut ve fark kısa tutulur.
- Gap yoksa bile en az bir satır yaz; "fark yok" gerekçesiyle belirt. -->

## Bulgular

<!-- doldur (ADR-0136: ölçüm ya da tarama yapıldıysa; ayrı bulgu belgesi yazılmaz, bulgu burada yaşar. Ölçüm yoksa tek satır: "Yok; ölçüm gerekmedi.").
- İlk satır `**Sonuç:**`: en önemli bulgu, tek cümle ve ana sayı.
- Her bulgu ayrı alt başlıktır: `### <bulgu adı>`.
- Altında önce `**Durum:**` (kesin | güçlü | hipotez), sonra kanıt; her kanıt ayrı madde (kaynak, sayı, ölçüm saati).
- Sayılar yazılırken kaynağından yeniden hesaplanır (K-002).
- Bakılabilen hiçbir şey §4'e yazılmaz; önce bakılır (P-051). -->
