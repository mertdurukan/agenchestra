# Commit mesajı standardı (Conventional Commits)

**Biçim:** `<tür>(<kapsam>): <kısa özet>`

- Kapsam isteğe bağlıdır (modül, klasör ya da Jira kodu).
- Özet emir kipinde, küçük harfle başlar, nokta ile bitmez, en çok 72 karakter.
- Gövde boş satırdan sonra gelir: ne değişti ve neden (nasıl değil).
- Uyumsuz değişiklik başlıkta `!` ile (`feat!:`) ya da gövdede `BREAKING CHANGE:` ile belirtilir.

**Türler:**

- `feat`: yeni özellik.
- `fix`: hata düzeltme.
- `docs`: yalnız belge.
- `style`: davranışı değiştirmeyen biçim değişikliği.
- `refactor`: davranışı değiştirmeyen kod düzenlemesi.
- `perf`: performans iyileştirmesi.
- `test`: test ekleme ya da düzeltme.
- `build`: derleme ve bağımlılık değişikliği.
- `ci`: CI yapılandırması.
- `chore`: bakım işi, kaynak ya da test dosyasını değiştirmeyen.
- `revert`: önceki commit'in geri alınması (gövdede geri alınan hash).

**Muafiyet:** `Otomatik commit: <dosya>` iletileri yereldir (oto_commit hook'u). Push'tan önce tek commit olarak birleştirilir (P-006); birleştirilen commit bu standarda uyar.

**Örnek:** `fix(kasa): iade tutarı yuvarlama hatasını düzelt`
