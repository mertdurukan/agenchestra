# Claude koruma çerçevesi (issue #14, PR-1)

Cursor birebir uyum PR'ları Claude'un çalışan dosyalarına dokunmaz. Denetim `araclar/cursor_koruma.py` ile yapılır, `.github/workflows/cursor-koruma.yml` her `cursor/*` dalında koşar.

## Ne denetlenir

| Sınıf | Kural | Kaynak |
|-------|-------|--------|
| `bayt_esit` | Taban ile HEAD arasında eklenen, silinen ya da değişen her dosya ihlaldir. Kanıt: git nesne baytlarından sha256 listesi (satır sonu dönüşümünden bağımsız). | `koruma_kurallari.json` |
| `yazma_izin` | Değişen her yol listede olmalı; yoksa ihlal. | aynı |
| `ortak_kod` | Paylaşılan dosya (ör. `doktor.py`) değişebilir ama PR gövdesinde "Paylaşılan koda dokunuldu mu" başlığının altı `Evet` ile başlamalı. | aynı |
| `cerceve` | Bu dosyaların değişmesi uyarı üretir; sahip incelemesi gerekir. | aynı |

Kurallar PR'ın **tabanından** okunur, PR kendi kuralını gevşetemez. Tabanda dosya yoksa (çerçeveyi ilk ekleyen PR) HEAD sürümü kullanılır ve uyarı verilir.

## Yerelde koşma

Değişiklikleri commit'leyin (denetim HEAD ile taban arasındaki farka bakar), sonra:

```powershell
git fetch upstream main
python araclar/cursor_koruma.py --denetle --taban upstream/main --govde-dosya pr_govde.md
python araclar/cursor_koruma.py --liste HEAD   # bayt_esit sha256 listesi
```

Çıkış kodu: 0 temiz, 1 ihlal, 2 git/kullanım hatası.

## Bilinen sınırlar

- Denetim PR'ın kendi checkout'undaki `cursor_koruma.py` ile koşar; çerçeveyi değiştiren PR denetimi zayıflatabilir. Bunun için `cerceve` uyarısı var; kalıcı çözüm `CODEOWNERS` (`.github/` bu programın izin listesinde değil, sahibin kararı).
- Yalnız `cursor/*` dal adlı PR'lar denetlenir; başka dallardaki Claude değişiklikleri kapsam dışıdır.
- "Claude çıktısı altın kayıtlarla bayt eşit" doğrulaması (paylaşılan koda ek yapılınca) henüz yok; ilk paylaşılan kod PR'ında (PR-6/PR-7/PR-8) eklenecek.
- sha256 listesi her koşuda taban ve HEAD'den üretilir ve CI artifact'ı olarak yüklenir; depoda sabit liste tutulmaz (Claude tarafındaki meşru commit'ler sabit listeyi bayatlatırdı).
