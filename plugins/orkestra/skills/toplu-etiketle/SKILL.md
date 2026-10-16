---
name: toplu-etiketle
description: >-
  Yüzlerce satırı (rakip özelliği, task, story, bulgu) yazılı kurallara göre etiketler ya da bir taksonomiye
  eşler: kuralları ana ajan yazar, veri parçalara bölünür, her parça paralel bir Haiku işçisine gider,
  birleştirme ve sayım betikle denetlenir, örneklemi ayrı denetçi kontrol eder. Kullanıcı "hepsini etiketle",
  "agentic mi yapay zeka mı işaretle", "kavramlara ata", "sınıflandır", "eşle", "her satıra kategori ver"
  dediğinde kullan. Tek tek 20 satırdan azsa gerek yok; doğrudan yap.
when_to_use: >-
  "etiketle", "sınıflandır", "kategorize et", "taksonomiye ata", "kavramlarla eşle", "her task'a
  agentic / yapay zeka / boş yaz", "rakip satırlarını kavramlara dağıt"; satır sayısı ≥ ~50 ve kural yazılabilir.
argument-hint: "<girdi.csv|json|xlsx> <neye göre etiketlenecek> [--id-sutun X] [--sayfa S --baslik-satiri N]"
---
# toplu-etiketle: kural (T3) → parçala (T0) → paralel işçi (T1) → birleştir + sayım (T0) → örneklem denetimi

İstek: $ARGUMENTS

**Amaç:** Yüzlerce satırı (ör. 923 satırı 174 kavrama eşlemek, 303 task'ı üç etikete ayırmak) ucuz, paralel ve
denetimli biçimde etiketlemek.
Betikler: `${CLAUDE_SKILL_DIR}/scripts/parcala.py`, `${CLAUDE_SKILL_DIR}/scripts/birlestir.py`.

Çalışma klasörü: projenin çalışma/ara çıktı klasörü altında `<konu>_<YYYYMMDD>\etiket\` (kural yoksa işin klasörü ya da `.claude/orkestra/`; kalıcı arşiv, scratchpad değil).

## Basamaklar
| Adım | Basamak | Kim | Çıktı |
|---|---|---|---|
| 1 Kurallar + etiket listesi | T3 | Ana ajan (gerekirse kullanıcıya sorar) | `kurallar.md`, `etiketler.txt` |
| 2 Parçalama + kart planı | T0 | `parcala.py` | `parca_NN.txt`, `manifest.json`, `plan.json` |
| 3 Parça etiketleme | T1 | `orkestra:isci-t1`, parça başına bir kart, paralel | `etiket_NN.csv` |
| 3a Parça denetimi | T2 | `orkestra:denetci` (sonnet; workflow kendisi açar) | kart kararı |
| 4 Birleştir + sayım | T0 | `birlestir.py` (isci-t1 çalıştırır) | `birlesik.csv`, `denetim_sayim.json`, `orneklem.csv` |
| 4a Örneklem denetimi | T2 | Birleştirme kartının ayrı `orkestra:denetci`'si | onay / ret + yanlış satırlar |
| 5 Teslim | T0 | `sade-excel` skill'i ya da kaynak xlsx'e sütun ekleme | teslim klasöründe `...xlsx` |

## Yöntem
1. **Kuralları yaz (T3, sen).** `kurallar.md`: numaralı kurallar (K1, K2 …), her biri "şu sinyal → şu etiket";
   çakışmada öncelik sırası; "birden çok işlev sayan satır → ilk ve baskın işlev"; hiçbir kurala uymayanda
   en yakın etiket + `guven=Düşük`. Örnek kalıp: `ozellik_karsilastirma_20261012\atama_kurallari.md` (10 kural + Ek)
   ve `etiketle.py` başındaki 3 etiketin tanımları. `etiketler.txt`: satır başına `etiket — kısa tanım`.
   Etiket kümesi bir ürün kararıysa (yeni taksonomi) kullanıcıya 3–8 satırla göster, onay al; değilse devam et.
2. **Parçala (T0).**
   ```
   python -X utf8 -I "${CLAUDE_SKILL_DIR}/scripts/parcala.py" --girdi <veri> --id-sutun <ID> \
     --sutunlar "<işçinin göreceği alanlar>" --kurallar <klasör>/kurallar.md --etiketler <klasör>/etiketler.txt \
     --klasor <klasör> [--parca-boyutu 200] [--maks-uzunluk 300] [--orneklem 30] [--esik 5]
   ```
   xlsx için `--sayfa` ve `--baslik-satiri` ver. Yalnız karar için gereken alanları seç (URL, uzun kanıt
   metni gereksiz token). Parça boyutu: kısa satırda 200–250, uzun satırda 80–120; parça sayısı ≤ 8.
   Kimliksiz satır, tekrar eden kimlik ya da < 2 etiket varsa betik durur; veriyi düzeltip yeniden çalıştır.
3. **Kartları kur.** `orkestra kart liste` ile orkestranın açık olduğunu gör (kapalıysa `/orkestra:baslat` öner).
   Sonra `orkestra kart toplu --json-dosya <klasör>/plan.json`. Plan: parça başına bir T1 kartı (yazma alanı
   yalnız kendi `etiket_NN.csv`'si, kabul kriterleri dolu) + tüm parçalara bağımlı tek T0 birleştirme kartı.
   Kullanıcıya planı 3 satırla göster (parça sayısı × satır, basamaklar, örneklem eşiği) ve devam et.
4. **Dağıt** (`/orkestra:is` §2 ile aynı yol). Tercih: Workflow `orkestra:calistir`,
   `args: { gorevler: [orkestra kart goster çıktıları] }`. Parça kartları paralel koşar, her biri ayrı denetçiden
   geçer; birleştirme kartı hepsi onaylanınca başlar ve denetçisi örneklemi kurallara karşı tek tek kontrol eder.
   Workflow yoksa elle: parça başına `Agent(subagent_type: "orkestra:isci-t1", run_in_background: true)`
   AYNI mesajda; istem `#GOREV:<id> #SUREC:is` ile başlar ve kartın `girdi` metnini içerir. Her işçiden sonra
   ayrı `orkestra:denetci` (`model: sonnet`, `#SUREC:denetim`). Sen etiket yazmazsın, onay vermezsin.
5. **Ret olursa.** `denetim_sayim.json` → `yeniden_kosulacak_parcalar`: yalnız o parçalar düzeltme sürecine
   (`#SUREC:duzeltme`) girer; temiz parçalara dokunma. Örneklem reddinde yanlışlar tek kurala yığılıyorsa
   kuralı netleştir (T3, sen), yalnız etkilenen parçaları yeniden koştur. İki retten sonra workflow T2'ye yükseltir.
6. **Teslim.** `birlesik.csv` kaynak sırasında, kaynak sütunları + `etiket, guven, gerekce`. Kullanıcıya:
   - liste lazımsa `sade-excel` skill'i (`--sutunlar` ile kimlik, ad, etiket, güven; ≤ 8 sütun);
   - mevcut bir xlsx'e sütun eklenecekse `etiketle.py` kalıbı (stil kopyalama, filtre genişletme) T2 karta.
   Son mesaj: etiket dağılımı, Düşük güven oranı, örneklem sonucu (n, yanlış), yeniden koşulan parçalar,
   kart başına basamak ve maliyet (`orkestra maliyet rapor --gun 1`).

## İşçi çıktı biçimi (kartın kabul kriterinde de yazılı)
`etiket_NN.csv`, UTF-8, virgül ayraçlı, başlık tam olarak `id,etiket,guven,gerekce`; parçadaki her id tam bir kez;
`etiket` yalnız `etiketler.txt`'ten; `guven` yalnız `Yüksek|Orta|Düşük`; `gerekce` ≤ 15 kelime + kural no.

## Kabul kriterleri (bütün iş)
- `birlestir.py` çıkış kodu 0, `TUTARLI: N/N` (N = kaynak satır sayısı); eksik, fazla, tekrar, izinsiz etiket yok.
- Örneklem denetiminde yanlış oranı ≤ `--esik` (varsayılan %5); denetçi kararı `onay`.
- Düşük güven oranı raporlandı; > %30 ise kural boşluğu olarak kullanıcıya söylendi.
- Kurallar, parçalar, işçi çıktıları, `denetim_sayim.json` ve `orneklem.csv` çalışma klasöründe kalıcı.

## Yasaklar
- Ana ajan parça etiketlemez ve onay yazmaz; işçi kendi parçasını denetlemez; denetçi dosya değiştirmez.
- `birlestir.py` TUTARSIZ derken `birlesik.csv`'yi elle üretme ya da eksik satırları tahminle doldurma.
- Paralel kartların yazma alanları kesişmez; işçiler `kurallar.md`, `parca_NN.txt`, `manifest.json`'u değiştirmez.
- Parçalara sır değeri, şifre, çalışan adı, `customer_id`/e-posta gibi kişisel alan konmaz (`--sutunlar` ile dışla).
- Etiket listesinde olmayan etiket uydurulmaz; fiyat/markdown ve MCP kapsam dışıysa (karar 11.10) listeye bir "kapsam dışı" etiketi konur.
