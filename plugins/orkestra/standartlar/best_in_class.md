# Best in class standardı (P-030)

Her türlü iş ve süreç için geçerlidir: Jira story, plan, kod, ölçüm, belge. `orkestra standart goster best_in_class` ile okunur.
P-018 belge BİÇİMİNİ denetler, bu standart çözümün KALİTESİNİ sorar; ikisi birlikte uygulanır.

## Dört soru

Plan yazılırken yazan kişi, plan bitince plan yazarından AYRI bir `orkestra:denetci` aynı soruları yanıtlar.

- **Kök neden:** çözüm belirtiyi mi kök nedeni mi ortadan kaldırıyor? Hata nerede oluştuysa orada mı önleniyor (K-006)?
- **Alternatifler:** en az iki uygulanabilir yaklaşım karşılaştırıldı mı, seçim gerekçeli mi? Elenen yaklaşım gerçekten seçilebilir olmalı; göstermelik rakip sayılmaz. Mevcut mekanizmalar (skill, standart, hook, kural) rakip olarak tartıldı mı?
- **Kapsam özü:** kapsam daraltılırken çözümün özü (kalıcı ya da yapısal öğe, ör. koruma katmanı, rol kısıtı, bağımsız denetim) çıkarıldı mı? Çıkarıldıysa gerekçesi ve yerine ne konduğu yazılı mı?
- **Ölçüm:** yöntem istatistiksel olarak yeterli ve gerekçeli mi? Eşik (geçme oranı), örnek büyüklüğü ve neden o sayı yazılı mı? Varlık kontrolü (`grep -c`) davranış ölçümü yerine geçmez.

## Beşinci soru (yalnız LLM çıktısı kullanıcıya gidiyorsa, P-032)

Plan `**LLM çıktısı:** kullanıcıya gider — Doğrulama: <yol>[::<test adı>]` beyanı taşıyorsa denetçi beşinci satırı da yanıtlar.

- **Yanıt kısıtı:** kısıtlar (söylenmeyecek şey, zorunlu uyarı, sayı ve kaynak, kapsam dışı konu reddi) kodla doğrulanıyor mu, gösterilen doğrulama ihlal vakasını gerçekten yakalıyor mu? Doğrulama yoksa neden prompt yeterli?

Beyan `yok — <neden>` ise bu satır istenmez. Kapı yol ve test adının varlığını yoklar; kısıtın yakalandığını denetçi ve test kanıtı gösterir.

## Üretim noktası (K-006, ADR-0069)

`uretim: true` taşıyan sıralı işte her plan maddesi sorunun nerede doğduğunu ve orada nasıl önleneceğini yazar. Alan üç türdür:

- `Düzeltme: <yer> — <önleme>`: çözüm sorunun doğduğu kural, şablon, skill, betik, kart, istem, hook, ayar ya da standartta yapılır.
- `Kontrol: <yer> — <ne kontrol edilir>; Kaynakta çözülmedi çünkü: <neden>`: yalnız sonradan yakalayan bir kontrol ekleniyorsa; neden kaynakta çözümün gerçekten olmadığını söyler.
- `Yeni yetenek — <gerekçe>`: düzeltilecek kusur yoksa; hata, ret, kusur ya da tekrar geçen maddede kullanılamaz.

Denetçi bunu beşinci satır olarak yanıtlar: `**Üretim noktası:** ✔|✘ — gerekçe`. Alan gerçek bir yer ve önleme adlandırıyor mu, tür doğru mu, `Kontrol` türünde kaynakta çözülmeme nedeni gerçek mi, tümü `Yeni yetenek` ise bu seçim doğru mu? Kapı biçimi, kopyayı (birebir ya da Jaccard 0,8 ve üzeri) ve denetçi kimliğini betikle sınar; yerin ve çözümün gerçekliğini yalnız denetçi yargılar.

## Ek ilkeler

- İsteği yanlış okumamak için iş başında istek kendi cümlenle yeniden yazılır; belirsizlik varsa kullanıcıya tek soruyla teyit ettirilir.
- Mevcut analize çıpalanılmaz: önce alternatifler çıkarılır, sonra mevcut analiz onlardan biri olarak tartılır.
- LLM davranışı ölçümünde sabit küçük tekrar (örn. 5) yeterli sayılmaz. Hedef geçme oranı ve güven aralığı belirtilir, örnek sayısı buna göre seçilir.
- Çıktıyı üreten ajan kendi çıktısının denetçisi olamaz; denetçi çağrısı kayıtla izlenir (`zaman.jsonl`).

## Plan maddesinde biçim

```
**Alternatifler:**

- Seçilen: <yaklaşım>. Neden: <gerekçe>.
- Elenen: <yaklaşım>. Neden elendi: <gerekçe>.
```

Plan sonunda `## Best in class denetimi` bloğu bulunur: dört satır `**Kök neden:** ✔|✘ — gerekçe`, `**Alternatifler:**`, `**Kapsam özü:**`, `**Ölçüm:**` ve `**Denetçi:** orkestra:denetci <agent_id>`. Denetçi ✘ verirse düzeltme yapılır, denetçi yeniden çağrılır.

## Zorlama

`uretim_noktasi` kapısı (`ayarlar/uretim_noktasi.json`) ilk günden `ihlal` modundadır (ADR-0069, kullanıcı kararı); her ret `kapi_ret` olarak yazılır. Kapatma: `ORKESTRA_URETIM_KAPISI=0`.

Üretim anı enjeksiyonu (ADR-0068): yukarıdaki `## Üretim anı` bölümü `scripts/yontem_enjeksiyonu.py` ile iş mesajlarında ana ajana, kartlı işçilerde SubagentStart'ta bağlama eklenir; kapatma `ORKESTRA_YONTEM_ENJEKSIYONU=0`.

Gölge kapı `best_in_class` (`ayarlar/best_in_class.json`): eksik uyarılır ve `kapi_golge` olarak yazılır, iş engellenmez. `ihlal` geçişi `orkestra is rapor` kapı sayıları ölçüldükten sonra ayrı kararla yapılır (P-028).

## Üretim anı

Bu işe başlarken best in class: (1) İsteği kendi cümlenle yeniden yaz, mevcut analize çıpalanma. (2) Sorunun doğduğu yeri bul ve orada önle; belirtiyi yamama (K-006). (3) En az iki uygulanabilir yaklaşım çıkar, mevcut skill/standart/hook/kuralı da rakip say, seçimi gerekçele. (4) Kapsam daraltırken çözümün yapısal öğesini (koruma, bağımsız denetim) çıkarma. (5) Ölçüm varsa eşik, örnek büyüklüğü ve nedenini yaz; varlık kontrolü davranış ölçümü değildir.
