# ADR-0132: /auto modu tam otonom, best in class ve kullanıcıya kalan işlerde karar

**Durum:** Kabul edildi

**Tarih:** 01.11.2026

**Bağlam:**

- `/auto` bugün soru sormuyor ve özete kadar akış tanımlıyor; best in class ve durmadan bitir talimatı skill'de yok (skills/auto/SKILL.md).
- Kullanıcıya ait işler yalnız "Kullanıcıya kalanlar"a listeleniyor; ajan çözmeyi denemiyor.
- Tur sonu durmayı engelleyen auto denetimi yok (scripts/hook.py `stop`).

**Karar:**

- Skill'e "Tam otonomi" bölümü eklenir: P-030 dört soruyla best in class, özete kadar durmama, kullanıcıya kalan işte önce ajanın çözmesi.
- Çözülemeyen işte ajan güvenli varsayılanla ilerler; her karar özette karar, gerekçe, alternatif, geri alma alanlarıyla yazılır.
- Stop hook'una auto devam hatırlatması ve `## Otomatik kararlar` alan denetimi eklenir; ikisi de gölge modda açılır (P-028).
- Sınırlar değişmez: sır değeri, parola girişi, hesap açma, zorla/silme/ayna push, salt okunur veritabanı.

**Seçenekler:**

- Yalnız skill metni: elendi; talimat tek başına yoruma açık, durma davranışını ölçmez.
- Yalnız hook ile zorlama: elendi; hook, modele ne yapacağını söylemeden yalnız durdurur, kalite çıtasını taşımaz.
- Skill artı gölge hook ve alan denetimi: seçildi; talimat ve ölçüm birlikte, ihlale geçiş ölçümden sonra.

**Sonuçlar:**

- Olumlu: kullanıcıya dönüş azalır; kararlar özette izlenebilir.
- Olumsuz: yanlış otomatik karar riski; geri alma alanı bunu sınırlar.
- Geri alma: skill bölümü ve iki ayar dosyası silinir; kapılar gölgede olduğu için iş engellenmemiş olur.

**İlgili iş ya da kural kimliği:** I-317, ADR-0009, ADR-0086, P-020, P-028, P-030
