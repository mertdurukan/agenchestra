# Jira Done yorum standardı

Görev Done'a geçerken Jira'ya şu yapıda tek yorum yazılır (başlıklar ayrı satırda):

- **Sonuç:** yapılan işin tek cümlelik özeti.
- **Değişiklik:** PR bağlantısı ve birleşen commit.
- **Test:** hangi testler koştu, sonuç.
- **Deploy:** hangi ortama, ne zaman çıktı ya da "çıkmadı, neden".
- **Geri alma:** geri alma yolu.
- **Not:** kalan iş ya da bilinen sınır, yoksa "Yok".

**Kaynak (ADR-0091):**

Yorum çalışma özetinin Teslim ve Özet alanlarından `orkestra is jira-yorum <iş kimliği>` ile türetilir, elle yazılmaz. Komut model çağırmaz ve metni değiştirmeden taşır; eksik alan varsa yorum üretmez, eksik alanları adıyla söyler (ör. `eksik: Test, Deploy`), düzeltme çalışma özetinde yapılır.

| Yorum alanı | Çalışma özetindeki kaynak |
| --- | --- |
| Sonuç | `**Durum:**` satırı + `**Ne yapıldı?**` ilk maddesi (etiket [..] dahil) |
| Değişiklik | `**Teslim:**` bloğundaki `- **Değişiklik:**` satırı |
| Test | `**Teslim:**` bloğundaki `- **Test:**` satırı |
| Deploy | `**Teslim:**` bloğundaki `- **Deploy:**` satırı |
| Geri alma | `**Teslim:**` bloğundaki `- **Geri alma:**` satırı |
| Not | `**Açık kalanlar:**` maddeleri; boşsa "Yok" |

`**Durum:**` yoksa yorum üretilmez.

**Kurallar:**

- Okuyan bağlamı bilmez: kısaltma ve belirsiz sahiplik ifadesi yerine somut ad, sürüm ve bağlantı yazılır.
- Sır, müşteri verisi ve çalışan adı yazılmaz.
- Yorum yazılmadan Done'a geçilmez; yorum Jira'ya yazılmadan önce kullanıcıya gösterilir (yazma onaya tabidir).
