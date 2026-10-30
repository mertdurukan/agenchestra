# ADR-0106: Görünen sonuç isteyen iş, ekranda görülecek sonuç kriteriyle başlar ve tarayıcı ölçümüyle kapanır

**Durum:** Kabul edildi

**Tarih:** 2026-10-30

**Bağlam:**

Araçlar sayfasında Açık/Kapalı düğmesinin her kartta aynı yerde durması istendi. İlk teslim yalnız düğme genişliğini sabitledi (`.anahtar { width:96px }`); satırın `flex-wrap: wrap` kuralı kaldı ve uzun içerikli kartlarda düğme alt satıra düştü. Panel testleri sahte DOM koşturur (tests/panel_duman.js), yerleşim hesaplamaz; teslim kod okumasıyla "yapıldı" sayıldı, tarayıcıda hiç ölçülmedi.

**Karar:**

(1) Kullanıcıya görünen yerleşim, hizalama ya da konum değişikliği olan iş, gerçek tarayıcıda ölçülmeden kapanmaz: öğelerin `getBoundingClientRect` değerleri (ör. tüm düğmelerin sağ kenarı eşit), düzeltme öncesi kırmızı ve sonrası yeşil. (2) Panel için ölçüm, headless Chrome/Edge ile çalışan testtir: tests/test_panel_araclar_yerlesim.py. (3) Kural eklenti katmanında P-044 olarak yazıldı (P-022). (4) İş başında kullanıcının sözü alıntılanır ve başarı kriteri ekranda görülecek sonuç olarak yazılır (kod ifadesi kriter sayılmaz); belirsiz sözcük tek soruyla teyit edilir; küçük ve sözleşmesiz işler de kapsanır. (5) Tek özelliği (genişlik, renk) düzeltmek konum düzeltmesi sayılmaz; önce konumu belirleyen kural bulunur.

**Seçenekler:**

- Yalnız CSS'i düzeltmek: elendi. Sahte DOM'da görünmeyen aynı sınıf hata tekrar eder.
- Her işte elle ekran görüntüsü istemek: elendi. Otomatik regresyon sağlamaz.
- Sahte DOM'a yerleşim motoru eklemek: elendi. Gerçek tarayıcıyı taklit etmek pahalı ve yanıltıcıdır.
- Mekanik kapı (hook): elendi. "Görsel değişiklik" metinden güvenilir ayırt edilemez, yanlış pozitif yüksek olur.

**Sonuçlar:**

Olumlu: konum hataları teslimden önce yakalanır, test kırmızı kalır. Olumsuz: Chrome/Edge olmayan makinede test atlanır (skip mesajı yazar); kural ajan disiplinine dayanır, mekanik kapı yoktur. Geri alma: P-044 ve test silinir, CSS değişmez.

**İlgili iş:** I-278, P-044, K-006, P-022, ADR-0098
