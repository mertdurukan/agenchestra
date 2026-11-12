# ADR-0180: Kapanış kutusu aracı oturumda yoksa hook isteği düşer

**Durum:**

Kabul edildi (I-455). P-029 ve P-059 kural metinleri bu kararı söyler.

**Tarih:**

12.11.2026

**Bağlam:**

- `wrap_up` bir Claude Code uygulaması aracıdır (`mcp__ccd_turn__wrap_up`), Orkestra'nın değil; bazı oturumlarda yüklü gelmez.
- Hook'lar bunu bilmeden her oturumdan `wrap_up` ister: arşiv düğmesi Stop kapısı block verir (ADR-0170), seçim hatırlatması, tur başı yönergesi ve devir yönergesi `wrap_up` çağırmasını söyler.
- Araç yoksa model çağıramaz; block boşa gider ve kullanıcıya görünür.
- Ölçüm (McD, 12.11.2026): arşiv düğmesi ihlali taşıyan 27 oturumun 23'ünün son araç listesinde `wrap_up` yok; son araç listesi okunan 400 oturumun 46'sında yok.
- Hook girdisi araç listesi taşımaz (19 alan). Liste transkriptte durur: `api-request-shape.shape.tools[].name` (yüklü araçlar) ve `deferred_tools_delta` kayıtları (ertelenmiş araçlar).

**Karar:**

- **Ortak okuyucu:** `scripts/arac_listesi.py` `var_mi(transkript, ad)` True, False ya da None (bilinmiyor) döner.
  - Kaynaklar birleşir: son `api-request-shape` listesi, `deferred_tools_delta` kayıtlarının sırayla oynatılması (`addedNames` ekler, `removedNames` çıkarır, `readdedNames` geri ekler), ana ajanın çağırdığı `tool_use` adları.
  - Yüklü araç listesi (`api-request-shape`) görülmeden ve ad kümede yoksa sonuç None'dır; "yok" yalnız liste görülüp ad bulunmayınca denir.
  - Okunamayan, kayıtsız ya da 64 MB'ı aşan transkript None döner.
- **Yalnız False susturur:** None'da eski davranış korunur (yanlış "yok" gerçek ihlali gizler, K-006).
- **Arşiv düğmesi kapısı:** `stop_karar` aday ihlal varken araç False ise `("", "arac_yok")` döner; hook günlüğe `kural_atlandi / arsiv_dugmesi / arac_yok` yazar, block etmez. `kural_ihlal` yazılmaz.
- **Metinler:** seçim hatırlatması, tur başı yönergesi ve devir yönergesi araç False iken `wrap_up` anmaz ve `AskUserQuestion` ile sunar. Metinler ayarda durur (`hatirlatma_arac_yok`, `tur_basi_yonerge_arac_yok`; devir için `devir_esigi.YONERGE_ARAC_YOK`).
- **Araç adı ayardan gelir:** `arac` anahtarı (`arsiv_dugmesi.json`, `secim_ekrani_hatirlatma.json`, `devir_esigi.json`); modül kodunda araç adı yoktur (P-022).
- **Günlük ayrımı:** seçim ekranı ihlali (düz metin seçtirme) araçsız oturumda da yazılır, çünkü `AskUserQuestion` alternatifi vardır.

**Seçenekler:**

- **Hook girdisinden ya da ortam değişkeninden okumak:** elendi, ikisinde de araç listesi yok.
- **`mod: kapali` ya da `ORKESTRA_ARSIV_DUGMESI=0`:** elendi, araçlı oturumları da susturur ve her projede elle ayar ister.
- **Bilinmiyor durumunda "wrap_up varsa" koşullu metin:** elendi, model yine de çağırmaya çalışır; liste kaydı olmayan 303 transkriptin 205'i `wrap_up` kullanmış, eski metin orada doğrudur.
- **Yeni kural kimliği açmak:** elendi, P-029 ve P-059 metnine cümle eklendi.

**Sonuçlar:**

- Araçsız oturumda arşiv düğmesi block'u gelmez; araçlı oturum eskisi gibi çalışır.
- Liste kaydı olmayan oturumlar (ilk tur, kısa oturum) etkisiz kalır: sonuç bilinmiyor.
- Claude Code transkript biçimini değiştirirse okuyucu None döner ve eski davranış sürer; `tests/test_arac_listesi.py` biçimi sınar.
- Okuma maliyeti: transkript yalnız aday ihlalde ve metin üretiminde bir kez taranır (satır filtresiyle).
- Kapsam dışı: `hooks/arka_plan_seridi.tsx` araçsız oturumda plan şeridini etkileyebilir; ayrı konu.
- Yayın sonrası ölçüm: araçsız oturumlarda `kural_ihlal / arsiv_dugmesi` sayısı 0 olmalıdır (`orkestra is rapor`).

**İlgili:**

- ADR-0170 (arşiv düğmesi), ADR-0107 (seçim ekranı yönergesi), ADR-0157 (devir yönergesi)
- Kurallar: P-029, P-059, P-022, K-006
- İş: I-455
