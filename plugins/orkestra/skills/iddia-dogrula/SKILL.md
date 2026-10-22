---
name: iddia-dogrula
description: >-
  Bir iddia ya da eksiklik listesini madde madde doğrular. Her madde için kanıt toplar (kod dosya:satır,
  DB sorgusu + saat + ortam, belge), DOĞRULANDI / KISMEN / ÇÜRÜTÜLDÜ / TEYİT / BELİRSİZ kararı verir ve
  gerekirse yeni metin önerir. Rapor ayrı bir denetçiden geçer. Kullanıcı "doğrulamanı ya da çürütmeni
  istiyorum", "bu listeyi doğrula", "eksiklik listesini kontrol et", "bu iddialar doğru mu", "veriyle ve
  kodla teyit et" dediğinde kullan. Tek bir DB ölçümü için db-olcum kullanılır.
when_to_use: >-
  "doğrulamanı ya da çürütmeni istiyorum", "bu listeyi doğrula", "eksiklik listesini kontrol et",
  "bu iddialar doğru mu", "veriyle ve kodla teyit et", "rakip tablosundaki satırları doğrula",
  "müşteri şikayetini veriyle tasdik et".
argument-hint: "<iddia listesi: dosya yolu (csv/md/xlsx sayfası) ya da sohbetteki maddeler>"
---
# iddia-dogrula: iddia listesi → madde başına kanıt → karar → denetimli rapor

**Amaç:** Her iddiaya kanıta dayalı tek bir karar vermek. Gerekiyorsa düzeltilmiş metni önermek. Rapor, kaynak belgeye geri işlenebilir halde olmalı.

## Ayar (önce oku)

Yollar ve projeye özgü kurallar ayardadır; skill metninde proje adı yoktur. Birleşik ayarı şu komut yazar:

```
python -I "${CLAUDE_SKILL_DIR}/scripts/rapor.py" ayar
```

Eklenti varsayılanı `ayarlar/iddia_dogrula.json`, proje ezmesi `.claude/orkestra/iddia_dogrula.json` (ezme anahtarları varsayılanın yerine geçer). Anahtarlar:

- `rapor_dizini`: raporun yazılacağı klasör (görev klasörü varsa onun içine).
- `calisma_dizini`: ham kanıt ve iddia listesi klasörü (`<konu>_<YYYYMMDD>\` alt klasörleriyle).
- `kod_depolari`: kod kanıtı için bakılacak depolar (yol, gerekirse komut ön ekleri).
- `kapsam_disi`: bu konudaki iddialar "kapsam dışı" notuyla BELİRSİZ işaretlenir, öneri yazılmaz.
- `ornek_raporlar` ve `onceki_turlar`: biçim örneği ve daha önce yapılmış doğrulama turları; yeni rapor bunların yapısını izler.
- `yayma_notlari`: yayma adımında projenin ayrıca işlemesi gereken günlük/dizin satırları.

**Rapor yapısı:** başlık bilgisi, özet tablo `| KID | Karar | Önerilen yeni metin |`, `## Kanıtlar` altında `### KID — konu` bölümleri, `## Açık kalanlar`.

## Kapılar
- **İddia listesi kimlikli olmalı.** Kimlik yoksa kaynak sırasıyla `I01, I02…` verilir. Kaynak belgede kimlik varsa o kullanılır, yenisi uydurulmaz.
- **DB kanıtı** yalnız `db-olcum` skill'i üzerinden toplanır. O skill'in kapıları geçerlidir (ağ/VPN, saat penceresi, kimlik dosyası proje dışında, salt okuma). Araştırmacı ajan DB'ye kendi başına bağlanmaz.
- **Kod kanıtı:** ayardaki `kod_depolari` altından toplanır. Kanıtla birlikte deponun son commit tarihi yazılır.
- **Kapsam dışı konular** ayardaki `kapsam_disi` listesindedir.

## Yöntem (basamaklarıyla)
1. **Listeyi çıkar (T1, `orkestra:isci-t1`):**
   - Kaynak md, xlsx satırları ya da sohbet olabilir. Çıktı: `<calisma_dizini>\<konu>_<YYYYMMDD>\iddialar.csv` (`kid;iddia`).
   - xlsx için openpyxl kullanılır.
   - İddia metni kaynaktaki gibi kalır, özetlenmez.
2. **Plan (T3, ana oturum):**
   - Her iddia için gereken kanıt türü belirlenir: kod, DB (kopya mı prod mu), iş takip kaydı ya da önceki belge.
   - Önce var olan kanıta bakılır (`onceki_turlar`, projenin referans belgeleri; Grep ile aranır, baştan okunmaz).
   - 3–5 iddia, aynı kaynağı paylaşıyorsa bir kanıt kartında gruplanır.
   - 5'ten fazla iddia varsa `/orkestra:is` ile kartlara bölünür. Kanıt kartları birbirinden bağımsızdır, karar kartı hepsine bağlıdır.
3. **İskelet (T0):**
   ```
   python -I "${CLAUDE_SKILL_DIR}/scripts/rapor.py" iskelet <iddialar.csv> --rapor <rapor_dizini>\<konu>_dogrulama_<YYYYMMDD>.md --kanit <calisma_dizini>\<konu>_<YYYYMMDD>\kanit --baslik "<başlık>"
   ```
   Rapor iskeletini ve iddia başına bir kanıt kartı (`kanit\<KID>.md`) üretir. Var olan raporun üstüne yazmaz.
4. **Kanıt toplama (T2, paralel `orkestra:arastirmaci`):**
   - Grup başına bir araştırmacı başlatılır. Hepsi aynı mesajda, `run_in_background: true` ile çağrılır.
   - Her araştırmacının görevi:
     - İddiayı **desteklemeye ve çürütmeye** çalışmak; karşı kanıtı da aramak.
     - Kanıtı dosya:satır, `şema.tablo` + sorgu betiği + saat + ortam ya da CSV yolu olarak vermek.
     - Bulamadığını "bulunamadı" diye yazmak.
     - Kart biçiminde yanıt dönmek. Araştırmacı dosya yazamaz; yanıtı `kanit\<KID>.md` dosyasına T1 ya da ana oturum işler.
   - DB ölçümü gerekiyorsa araştırmacı sorguyu önerir. Sorgu `db-olcum` akışıyla, ayrı kartta çalıştırılır.
5. **Karar (T3, `orkestra:isci-t3` ya da ana oturum):** Kartlar okunur, rapor doldurulur. Karar kuralları:
   - **DOĞRULANDI:** Metin olduğu gibi doğru. Gerekirse "(+) nüans" eklenir.
   - **KISMEN:** Özü doğru ama metin yanlış ya da eksik. Yeni metin zorunlu.
   - **ÇÜRÜTÜLDÜ:** Kanıt iddianın tersini gösteriyor. Yeni metin zorunlu.
   - **TEYİT:** Kopyadaki bulgu üretimde aynı çıktı. Yalnız prod teyidi bağlamında kullanılır.
   - **BELİRSİZ:** Kanıt yetersiz ya da erişim yok. Madde "Açık kalanlar"a girer; kime sorulacağı yazılır.
   - Her bulguya kanıt derecesi verilir: kesin / güçlü / hipotez. Kopyadan gelen sonuçta "bu kopyaya göre" yazılır.
   - Yeni metin kısa, kullanıcının dilinde ve kaynak belgeye yapıştırılabilir olmalı.
6. **Mekanik denetim (T0):**
   ```
   python -I "${CLAUDE_SKILL_DIR}/scripts/rapor.py" denetle <rapor.md> --iddialar <iddialar.csv> --yasakli <scratchpad\yasakli.txt>
   ```
   Denetlenenler: karar etiketi geçerli mi; KISMEN ve ÇÜRÜTÜLDÜ maddelerinde yeni metin var mı; her kimliğin kanıt bölümü ve kanıt izi var mı; eksik madde, yer tutucu, sır ya da e-posta kalıbı, yasaklı kelime var mı.
   - Yasaklı kelime listesi (ör. kişi adları) **proje dışında**, scratchpad'de tutulur; projeye ve rapora girmez.
   - Çıkış 1 ise 5. adıma dönülür.
7. **Denetim (ayrı `orkestra:denetci`, karar veren işçinin bir üst basamağı):** Denetçi görev kartını, kabul kriterlerini, rapor yolunu ve `kanit\` klasörünü alır. Yaptıkları:
   - Her ÇÜRÜTÜLDÜ ve KISMEN maddesinin kanıtını kaynağında açar: dosya:satır gerçekten öyle mi, CSV'deki sayı aynı mı.
   - DOĞRULANDI maddelerinin en az %20'sini örnekler.
   - Karar ile kanıt derecesi tutarsızsa reddeder. Örnek: "kesin" denmiş ama tek kanıt bir hipotez.
   - Ret gelirse en çok 2 düzeltme yapılır, sonra basamak yükseltilir. İşçi kendi raporunu onaylamaz.
8. **Yayma (ana oturum, kullanıcı onayıyla):**
   - Yeni metinlerin kaynak belgeye ya da xlsx'e işlenmesi yeni tarihli dosyayla yapılır, eski sürümün üstüne yazılmaz.
   - Kimlik taşıyan belgeler `/orkestra:madde-senkron`'a devredilir.
   - Ayardaki `yayma_notlari` satırları işlenir.

## Çıktı biçimi ve yeri
- **Rapor:** `<rapor_dizini>\<konu>_dogrulama_<YYYYMMDD>.md`.
  - Başlık bilgisi: tarih ve saat aralığı; kaynaklar (DB ortamı, kod depoları ve son commit, belgeler); kapsam; kararların özeti (çürütülen, metni düzeltilecek, nüans eklenecek maddeler).
  - Sonra özet tablo, kanıtlar ve açık kalanlar.
- **Ham kanıt:** `<calisma_dizini>\<konu>_<YYYYMMDD>\` altında `iddialar.csv`, `kanit\<KID>.md` ve varsa db-olcum betikleri ve CSV'leri.
- **Kullanıcıya dönüş:** karar sayıları, değişen maddeler (KID + bir cümle), açık kalanlar ve rapor yolu.

## Kabul kriterleri
- `rapor.py denetle` GEÇTİ: her iddia raporda, etiketi geçerli; KISMEN ve ÇÜRÜTÜLDÜ maddelerinde yeni metin var; her madde kanıt izli.
- Her karar en az bir doğrulanabilir kanıta dayanıyor: dosya:satır, sorgu + saat + ortam ya da CSV. DB kanıtının ortamı yazılı.
- Kopya kaynaklı sonuçlar etiketli. BELİRSİZ maddelerde neyin eksik olduğu ve kime sorulacağı yazılı.
- Ayrı denetçi onay vermiş.

## Yasaklar
- Kanıtsız karar vermek. "Muhtemelen" diye DOĞRULANDI ya da ÇÜRÜTÜLDÜ yazmak; kanıt yoksa BELİRSİZ.
- İddia metnini sessizce değiştirmek. Değişiklik yalnız "Önerilen yeni metin" sütununda yapılır.
- Kararı veren ajanın kendi raporunu denetlemesi.
- DB'ye db-olcum kapıları dışında bağlanmak; yazma sorgusu; sır kolonu okumak.
- Rapora sır değeri, şifre, kişi adı ya da e-posta yazmak.
- Kaynak belgenin ya da xlsx'in üstüne yazmak. Kanonik belgeleri doğrudan düzenlemek.
