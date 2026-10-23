# Best in class standardı (P-030)

Her türlü iş ve süreç için geçerlidir: Jira story, plan, kod, ölçüm, belge. `orkestra standart goster best_in_class` ile okunur.
P-018 belge BİÇİMİNİ denetler, bu standart çözümün KALİTESİNİ sorar; ikisi birlikte uygulanır.

## Dört soru

Plan yazılırken yazan kişi, plan bitince plan yazarından AYRI bir `orkestra:denetci` aynı soruları yanıtlar.

- **Kök neden:** çözüm belirtiyi mi kök nedeni mi ortadan kaldırıyor? Hata nerede oluştuysa orada mı önleniyor (K-006)?
- **Alternatifler:** en az iki uygulanabilir yaklaşım karşılaştırıldı mı, seçim gerekçeli mi? Elenen yaklaşım gerçekten seçilebilir olmalı; göstermelik rakip sayılmaz. Mevcut mekanizmalar (skill, standart, hook, kural) rakip olarak tartıldı mı?
- **Kapsam özü:** kapsam daraltılırken çözümün özü (kalıcı ya da yapısal öğe, ör. koruma katmanı, rol kısıtı, bağımsız denetim) çıkarıldı mı? Çıkarıldıysa gerekçesi ve yerine ne konduğu yazılı mı?
- **Ölçüm:** yöntem istatistiksel olarak yeterli ve gerekçeli mi? Eşik (geçme oranı), örnek büyüklüğü ve neden o sayı yazılı mı? Varlık kontrolü (`grep -c`) davranış ölçümü yerine geçmez.

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

Gölge kapı `best_in_class` (`ayarlar/best_in_class.json`): eksik uyarılır ve `kapi_golge` olarak yazılır, iş engellenmez. `ihlal` geçişi `orkestra is rapor` kapı sayıları ölçüldükten sonra ayrı kararla yapılır (P-028).
