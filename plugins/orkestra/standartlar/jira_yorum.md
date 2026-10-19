# Jira Done yorum standardı

Görev Done'a geçerken Jira'ya şu yapıda tek yorum yazılır (başlıklar ayrı satırda):

- **Sonuç:** yapılan işin tek cümlelik özeti.
- **Değişiklik:** PR bağlantısı ve birleşen commit.
- **Test:** hangi testler koştu, sonuç.
- **Deploy:** hangi ortama, ne zaman çıktı ya da "çıkmadı, neden".
- **Geri alma:** geri alma yolu.
- **Not:** kalan iş ya da bilinen sınır, yoksa "Yok".

**Kurallar:**

- Okuyan bağlamı bilmez: kısaltma ve belirsiz sahiplik ifadesi yerine somut ad, sürüm ve bağlantı yazılır.
- Sır, müşteri verisi ve çalışan adı yazılmaz.
- Yorum yazılmadan Done'a geçilmez; yorum Jira'ya yazılmadan önce kullanıcıya gösterilir (yazma onaya tabidir).
