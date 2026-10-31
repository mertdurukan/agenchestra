# ADR-0126: Belge şablonları satır başı ifade düzeni; mevcut durum Özet'siz, Doğrulanamayanlar bölümlü

**Durum:** Kabul edildi

**Tarih:** 2026-10-31

**Bağlam:** Kullanıcı şablon örneklerini gözden geçirdi: mevcut durum okunması zor, Özet gereksiz, "Git durumu" mevcut durum ilkesine (değişiklikten önceki hal) aykırı, "Bilinmeyenler" bölümü orkestranın kanıtla çalışma ilkesine aykırı bulundu. Ayrıca her ifadenin yeni satırda başlaması ve başlık hiyerarşisinin düzgün olması istendi.

**Karar:**

- **Satır başı ifade:** tüm belge şablonları (mevcut durum, bulgu, rapor, sözleşme, plan, todo, çalışma özeti, jira_onerisi) her ifadeyi ayrı satırda, en çok bir cümle olarak ister; üstteki yorum bloğu bu kuralları taşır.
- **Hiyerarşi:** `##` ana başlık, `###` alt başlık; kalın etiket yalnız alan adıdır.
- **Mevcut durum:** Özet ve Git durumu yoktur; bölümler Kapsam ve yöntem, §1 yol, §2 davranış, §3 etki, §4 Doğrulanamayanlar, §5 Gap analizidir (eskiden §6 gap). Kapı eski düzeni `md_duzen` ile tanır.
- **Doğrulanamayanlar:** yalnız veriyle doğrulanması denenip doğrulanamayan şeyler girer; her madde Konu, Denenen, Engel satırlarını taşır.
- **Özet yalnız çalışma özetinde:** plan ve sözleşme dahil diğer şablonlar `## Özet` taşımaz; bölüm başında `**Sonuç:**` satırı vardır ve `ozet_eksigi` plan ile sözleşmede çağrılmaz. Çalışma özetindeki `## Özet` Şef Özeti'dir (ADR-0085, ADR-0091; yönetici anlatısı ile Jira Done yorumunun tek kaynağı), kapanış kapısı onu ister.
- **Terim ayrımı:** çalışma özeti ve plan `Doğrulanmayanlar` adını korur (`is_kaydi` ve `is_anlati` kapıları bu etiketi okur); mevcut durum `Doğrulanamayanlar` der.

**Seçenekler:**

- Özet'i çalışma özetinden de kaldırmak: elendi, Jira Done yorumu ve yönetici anlatısı o alanlardan türer.
- Yalnız yazım kuralı eklemek, şablonu değiştirmemek: elendi, K-006; kural doldurulan iskelette görünmezse uygulanmaz.
- Eski mevcut durum düzenini bırakmak: elendi, kullanıcı isteğine aykırı.

**Sonuçlar:**

- Olumlu: belgeler satır satır taranabilir; mevcut durum yalnız önceki hali anlatır; doğrulanamayan şey açıkça ayrılır.
- Olumsuz: açık plan ve sözleşmelerde eski `## Özet` bölümü zararsız kalır ama artık denetlenmez; iki terim (Doğrulanamayanlar, Doğrulanmayanlar) birlikte yaşar.
- Geri alma: şablon dosyalarını ve `is_sirasi.md_duzen` ile `plan_alan.py` değişikliğini commit'ten geri al.

**İlgili iş ya da kural kimliği:** P-018, P-016, P-017, K-005, K-006, ADR-0085, ADR-0091
