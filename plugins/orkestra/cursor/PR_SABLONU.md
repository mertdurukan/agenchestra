# Cursor birebir uyum: PR şablonu

`cursor/birebir-uyum` çalışmasındaki (issue #14) her PR gövdesi bu başlıkları taşır.

```markdown
## Ne değişti, hangi G maddesini kapatır
<özet; G1…G16 ve PR numarası>

## Claude etkisi
Yok. Bayt eşitliği CI sonucu: <cursor-koruma çalıştırma bağlantısı>

## Paylaşılan koda dokunuldu mu
Hayır. / Evet: <dosya:satır aralığı, host koşulu (CURSOR_VERSION / CURSOR_PLUGIN_ROOT)>

## Geri alma adımı
<tek revert ile Cursor katmanını çıkaran adım>

## Test sonucu ve doğrulanmayan varsayımlar
<koşulan komut ve çıktı; ölçülmemiş her şey "doğrulanmadı" olarak>
```
