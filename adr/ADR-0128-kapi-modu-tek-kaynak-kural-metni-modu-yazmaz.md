# ADR-0128: Kapı modu tek kaynaktan okunur; kural metni modu yazmaz

**Durum:** Kabul edildi

**Tarih:** 2026-11-01

**Bağlam:** Kural metinleri kapı modunu elle yazıyordu ("gölgededir", "mod ihlal"). Mod ayarda değişince metin eskiyordu ve kullanıcıya yanlış mod söyleniyordu (I-300). Kod yorumlarında ve P-028'de bu karar ADR-0125 diye anıldı, ama ADR dosyası hiç yazılmadı; ADR-0125 numarasını sonra oturum konum kaydı aldı.

**Karar:**

- **Tek kaynak:** Kapı modu yalnız `ayarlar/<kapı>.json` `mod` alanından (proje ezmesi dahil) okunur.
- **Yer tutucu:** Kural metni modu `{{mod:<ayar>}}` yer tutucusuyla yazar; `kapi_mod.mod_coz` onu ayardan çözer (kural dosyası, KURALLAR.md bloğu, kural görünümü).
- **Okuma komutu:** `orkestra kapi durum [--json]` her kapının varsayılan, ezme ve etkin modunu basar.
- **Zorlama:** `tests/test_kural_mod.py` elle yazılmış mod ifadelerini reddeder.

**Seçenekler:**

- Metni her mod değişiminde elle güncellemek: elendi, tam bu kusurun kaynağı.
- Kural metninden modu hiç söylememek: elendi, kullanıcı geçerli modu bilmek ister.
- KURALLAR.md'yi mod değişince yeniden üretmek ama metni elle yazılı bırakmak: elendi, kaynak ikiye bölünür.

**Sonuçlar:** Olumlu: metin ile ayar ayrışamaz. Olumsuz: kural metni tek başına okununca mod görünmez, `orkestra kapi durum` gerekir. Geri alma: yer tutucuları metne geri yazıp `mod_coz` çağrısını kaldırmak.

**İlgili iş ya da kural kimliği:** I-300, P-028; önceki yanlış atıf ADR-0125 (oturum konum kaydı) bu ADR'ye düzeltildi (I-306).
