# ADR-0111: Üretim anında önleme: merdiven kurala, tabi olunan denetim yazım anında bağlama

**Durum:** Kabul edildi

**Tarih:** 2026-10-31

**Bağlam:**

Kullanıcı (31.10.2026): kontrolle yakalanan sorunlar reddedilmeden önce, ilk üretimde kök nedende çözülsün. ADR-0042 merdiveni (L0–L6) yalnız karar kaydı; K-006 yalnız kural metni; ADR-0101 yalnız hata sinyalinde bağlam verir. Ajan çıktıyı yazarken tabi olduğu denetimin kuralını görmüyor. 178 hook retinin 170'i üretim noktasında düzeltilebilir sınıfta (iş 129).

**Karar:**

(1) Merdiven eklenti kuralı P-045 olur; metin tek kaynaktan `standartlar/onleme_merdiveni.md`. (2) `scripts/uretim_enjeksiyonu.py`: PreToolUse'ta Write/Edit hedefi `ayarlar/uretim_enjeksiyonu.json` eşlemesindeki bir belge türüne denk gelirse ilgili kapı kuralı ve iskelet bağlama konur (L4); engellemez, `gunluk.jsonl`'a `uretim_enjekte` yazar. Kapatma `ORKESTRA_URETIM_ENJEKSIYON=0`, proje ezmesi `.claude/orkestra/uretim_enjeksiyonu.json`. (3) Etki ölçümü ret oranı (taban 21,53/100 tur) ve K-005 ihlali üzerinden, örnek büyüklüğü I-224 asgarileriyle.

**Seçenekler:**

- Elenen: yeni ret kapısı. ADR-0042: önce L0–L4; sonradan yakalama sorunu üretildiği yerde çözmez.
- Elenen: yalnız kural metni. K-006'nın bugünkü hâli; yazım anında bağlamda yok.
- Elenen: mekanik düzeltici (L3) tek başına. Geçmiş belgelerde biçim ihlallerinin yalnız %2,7'sini giderdi.

**Sonuçlar:**

Olumlu: ajan kuralı yazarken görür, ret azalır. Olumsuz: Write/Edit başına ≤300 karakter bağlam; etki ölçülmeden kesin değil. Eşzamanlı kontrol: ayar `kontrol_orani` (varsayılan 0) > 0 ise oturum kimliğinin sabit özetiyle seçilen oturumlar metin almaz ve `uretim_kontrol` yazar; `ret_olcum` kolları oturum başına karşılaştırır (ön/son tek kollu sınırı kalkar, yalnız oran > 0 iken). Geri alma: ayar `mod: kapali` ya da `ORKESTRA_URETIM_ENJEKSIYON=0`; ADR "Yerine geçildi" olur.

**İlgili iş:** I-293, K-006, P-033, P-042, ADR-0042, ADR-0101.
