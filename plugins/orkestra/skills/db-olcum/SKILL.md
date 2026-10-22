---
name: db-olcum
description: >-
  Projenin veritabanında (kopya ya da prod) salt okuma ölçüm yapar: hipotezden Python sorgu betiği üretir,
  kapı denetimlerinden (VPN, saat penceresi, kimlik dosyasının yeri, SQL güvenliği) geçirip çalıştırır,
  saatli CSV ve bulgu raporu yazar, arşivler. Kullanıcı "DB'de ölç", "veriyle tasdik edelim", "şu tabloya
  bak", "sorgu yaz ve çalıştır", "kaç satır var", "hangi şemalarda var" dediğinde kullan. İddia listesi
  için iddia-dogrula kullanılır.
when_to_use: >-
  "DB'de ölç", "veriyle tasdik edelim", "şu hipotezi veriyle kontrol et", "sorgu yaz ve çalıştır",
  "kopyada bak", "prod'da bak", "kaç satır / hangi şemalarda var", "senkron bitti mi".
argument-hint: "<soru ya da hipotez> [şema ...] [--ortam kopya|prod]"
---
# db-olcum: salt okuma DB ölçümü (hipotez → betik → CSV → saatli bulgu)

**Amaç:** Bir soruyu ya da hipotezi projenin DB'sinde ölçmek. Ölçüm tekrar çalıştırılabilir bir betikle yapılır, ham çıktısı CSV olarak, yorumu kanıt derecesiyle yazılır, hepsi projede arşivlenir.

## Ayar (önce oku)

Sunucu adresleri, yasak saatler ve projeye özgü kurallar ayardadır; skill metninde proje adı yoktur. Birleşik ayarı şu komut yazar:

```
python -I "${CLAUDE_SKILL_DIR}/scripts/kapi.py" --ayar
```

Eklenti varsayılanı `ayarlar/db_olcum.json`, proje ezmesi `.claude/orkestra/db_olcum.json` (üst düzey anahtarlar yerine konur, `ortamlar` ad ad birleşir). Anahtarlar:

- `ortamlar.<ad>`: `host`, `port`, `yasak_saatler` (`[["17:15","23:15"]]` gibi aralıklar; gece yarısını aşan aralık desteklenir), prod için `mesai`.
- `senkron_kullanici`: doluysa üretilen betik bu hesabın aktif sorgusunu uyarı olarak denetler.
- `kimlik_dosyasi`: bağlantı yardımcısının adı (varsayılan `db.py`; `connect(timeout_s=…)` ve `qc(bağlantı, sql, params)` sunar). Dosya **proje dışında** tutulur.
- `yasak_komut_kalibi` ve `yasak_kolon_kaliplari`: SQL denetiminin kalıpları (yazma/DDL; kişisel veri ve sır kolonları). Proje kendi kolonlarını ezmede ekler.
- `okunmayacak_alanlar`: okunması yasak kolon ve alanların açıklaması (ajan sorguya yazmaz).
- `calisma_dizini`: ölçüm klasörlerinin kökü (`<konu>_<YYYYMMDD>\`).

Kimlik (şifre, bağlantı dizesi) için `orkestra kimlik liste` ile kimlik klasörüne bakılır; değer okunmaz, yazılmaz.

## Kapılar (biri kalırsa DUR, kullanıcıya söyle)
- **Kapı betiği (T0):** `python -I "${CLAUDE_SKILL_DIR}/scripts/kapi.py" --ortam kopya|prod --db-py <kimlik dosyası klasörü>`. Çıkış 1 ise devam etme. Betik şunları denetler:
  - **Saat:** Ortamın `yasak_saatler` aralıklarında sorgu çalışmaz. Prod'da `--seviye agir` ile mesai içinde uyarı verir.
  - **Ağ/VPN:** DNS sistem çözümleyicisiyle çözülür (Resolve-DnsName ile aynı yol), ardından ayardaki porta TCP denenir. `nslookup` kullanma, yanıltıcı. Kalırsa kullanıcıdan VPN'i bağlamasını iste. Host ayarda yoksa denetim UYARI ile atlanır.
  - **Kimlik dosyası:** Proje dışında mı, projede aynı adlı dosya kalmış mı?
- **Kimlik dosyası:**
  - Önceki oturumların scratchpad'inde ya da kimlik klasöründe durur. Bu oturumun scratchpad'ine kopyala.
  - İçeriğini **okuma, yazdırma, projeye kopyalama.**
  - Bulamazsan kullanıcıya sor. Şifreyi Claude girmez.
- **Senkron kontrolü:** Kopyada yasak aralığın sınırındaysan önce senkron hesabının aktif sorgusu olup olmadığına bak; varsa bekle.
- **İzin:** Prod sorgusu ilk kez çalışacaksa kullanıcının o oturumdaki onayını al. İzin denetimini atlatmaya çalışma.

## Yöntem (basamaklarıyla)
1. **Triyaj (ana oturum, T3):** Soru tek ölçüm mü, çok parçalı mı?
   - 2'den fazla bağımsız hipotez ya da şema grubu varsa `/orkestra:is` ile kartlara böl. Her kartta `basamak`, `girdi`, `kabul_kriterleri` ve kesişmeyen bir `yazma_alani` olur (ör. `<calisma_dizini>/<konu>_<YYYYMMDD>/<vN>*`).
   - Orkestra kapalıysa adımları ana oturumda sırayla yürüt; denetimi yine ayrı bir ajana yaptır (9. adım).
2. **Önceki bulgu taraması (T2, `orkestra:arastirmaci`):**
   - Projenin veritabanı referans belgesi baştan okunmaz, Grep ile aranır.
   - Çalışma klasörü dizini ve daha önceki doğrulama/teyit belgeleri taranır.
   - Aynı ölçüm zaten varsa yeniden yazma, onu yeniden çalıştır.
3. **Hipotez ve sorgu tasarımı (T3, `orkestra:isci-t3` ya da ana oturum):** Şunları yaz:
   - hipotez,
   - doğrulama ve çürütme ölçütü,
   - tablolar ve şemalar,
   - SQL.
   Kurallar:
   - Yalnız SELECT, EXPLAIN ve katalog (`pg_get_functiondef`, `information_schema`, `pg_class`). Fonksiyon, prosedür ya da CALL çalıştırılmaz; gövde okunur.
   - Büyük tabloda sayım `reltuples` ile; tarama `LIMIT` ya da tarih aralığıyla.
   - "Boş" kararı küçük tabloda `count(*)` ile verilir.
   - Ağır sorgudan önce `EXPLAIN`. Tek sorgu en çok 3–10 dk.
   - `okunmayacak_alanlar` listesindeki alanlar (kişi tanımlayıcıları, bağlantı parametreleri, ham yük alanları) okunmaz.
4. **İskelet (T0):** `python -I "${CLAUDE_SKILL_DIR}/scripts/iskelet.py" --klasor <calisma_dizini>\<konu>_<YYYYMMDD> --ad <vN_konu> --soru "..." --hipotez "..." --zaman-asimi 600`.
   - İskelet olduğu gibi çalışır: ortam, saat ve salt okuma doğrulamasını yapar, ayarda senkron hesabı varsa uyarı verir, VPN koparsa durur.
   - Var olan dosyanın üstüne yazmaz.
5. **Doldurma (T1, `orkestra:isci-t1`):** T3'ün SQL'ini `SORGULAR` sözlüğüne birebir yerleştir. Şema yeri `{s}` ile işaretlenir; betik bunu şema adıyla değiştirir (başka süslü parantez kaçırılmaz).
6. **SQL denetimi (T0):** `python -I "${CLAUDE_SKILL_DIR}/scripts/kapi.py" --ag-atla --sql-denetim <betik.py>`. Kalırsa 3. adıma dön.
7. **Çalıştırma (T1):** `python -I <betik.py> <kimlik klasörü> <klasör>\ciktilar [şema ...]`.
   - Her CSV'nin ilk kolonu `sorgu_saati`; koşu günlüğü `<ad>_kosu.txt`.
   - Yasak aralıktaysan kullanıcıya bildir. Gece koşusu gerekiyorsa aralığın bitmesini bekleyen bir betik kullan; foreground `sleep` kullanma.
8. **Yorum (T3):** `<klasör>\RAPOR.md` yaz (biçim aşağıda). Sayılar CSV'den alınır, uydurulmaz.
9. **Denetim (ayrı `orkestra:denetci`, işçinin bir üst basamağı):** Denetçi görev kartını, kabul kriterlerini ve çıktı yolunu alır.
   - Betiği yeniden okur, rapordaki sayıları CSV ile eşler.
   - Ret gelirse düzeltilir (en çok 2 tur), sonra basamak yükseltilir.
   - İşçi kendi işini onaylamaz.
10. **Arşiv ve iz:**
    - T1: `kapi.py --ag-atla --cikti-tara <klasör>` temiz olmalı.
    - Ana oturum, sentez adımında: projenin çalışma klasörü dizinine ve günlüğüne satır ekler. Ortak dosyalara işçi yazmaz; dosya önce yeniden okunur, yalnız sona eklenir.
    - Bulgu bir madde kimliğini değiştiriyorsa `/orkestra:madde-senkron`'a ya da kullanıcıya devredilir; kanonik belgelere bu skill yazmaz.

## Çıktı biçimi ve yeri
- Klasör: `<calisma_dizini>\<konu>_<YYYYMMDD>\`. İçinde betikler (şifresiz), `ciktilar\*.csv`, `*_kosu.txt` ve `RAPOR.md` bulunur.
- `RAPOR.md` her soru için şu sırayla yazılır:
  - **Soru → Yöntem** (betik adları) **→ Bulgular** (tablo; her sayı ortam ve sorgu saatiyle) **→ İş kuralı diliyle yorum → Açık sorular → Kanıt derecesi** (kesin / güçlü / hipotez).
  - Kopyadan gelen her sonuçta "bu kopyaya göre" yazılır. Prod sonuçlarında "üretim, <tarih saat>" yazılır.
  - Sonda iki liste: bulgunun dokunduğu madde kimlikleri ve önerilen düzeltme.
- Kullanıcıya dönüş: 10–20 satır özet ve rapor yolu.

## Kabul kriterleri
- `kapi.py` hem çalıştırmadan önce (pencere, VPN, kimlik dosyası, SQL) hem arşivden önce (çıktı taraması) GEÇTİ verdi.
- Her bulgu sayısının bir CSV karşılığı ve sorgu saati var. Ortam (kopya/prod) yazılı.
- Hipotez açıkça doğrulandı, çürütüldü ya da "ölçülemedi" denip nedeni yazıldı.
- Betik `python -I` ile yeniden çalıştırılabiliyor. Proje içinde kimlik dosyası, şifre, kişi adı ya da e-posta yok.
- Denetçi onayı alındı (orkestra kartı varsa `karar: onay`).

## Yasaklar
- DML, DDL, CALL, REFRESH, VACUUM; fonksiyon ya da prosedür çalıştırmak; `SET default_transaction_read_only = off`.
- Yasak saat aralığında sorgu. `could not translate host name` hatası alırsan dur, o ana kadarki çıktıyı yaz, kullanıcıya VPN'i söyle.
- Kimlik dosyasının içeriğini okumak ya da göstermek, projeye kopyalamak; şifre ya da bağlantı dizesini komut satırına, dosyaya veya hafızaya yazmak.
- Kişi adı ya da DB rol adı yazmak (gerekirse "bir çalışan rolü" denir).
- Sır kolonlarını okumak. Sır yalnız yeriyle anılır (şema.tablo.kolon).
- `python -c` ile çok satırlı SQL çalıştırmak; sorgu betiğe yazılır.
- Kanonik belgeleri doğrudan düzenlemek.
