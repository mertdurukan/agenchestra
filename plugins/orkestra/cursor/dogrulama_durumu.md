# Cursor doğrulama durumu (11.11.2026)

## Doğrulandı / Doğrulanmadı

| Madde | Durum | Kanıt / neden |
|---|---|---|
| Cursor CLI kurulumu (resmi: `irm 'https://cursor.com/install?win32=true' | iex`, kullanıcı dizini) | Doğrulandı | `agent --version` → 2026.11.11-043ef28; `agent status` → "Not logged in" |
| Cursor hook adaptörü birim davranışı (komut yeniden yazma, preToolUse failClosed bildirimi, kurulum, rol) | Doğrulandı (yalnız birim testi) | `tests/test_cursor_*.py`, `test_doktor_cursor.py` |
| `doktor --cursor-sonda` betiği çalışır ve CLI yokken dürüstçe "atlandı" der | Doğrulandı | CLI yokken "atlandı", CLI kuruluyken oturumsuz "belirsiz" der (ajan çıktısı: "Authentication required"); yanlışlıkla "geçti" demez |
| Dinamik sonda: komut yeniden yazıldı mı, komut Shell'de çıktı verdi mi, oturum kimliği hook ile aynı mı | **Doğrulanmadı** | CLI kurulu ama oturum açık değil (`agent login` ya da `CURSOR_API_KEY` gerekir); ajan hiç koşmadı, üç ölçüm "belirsiz" |
| Cursor CLI ile gerçek ajan koşusu | **Doğrulanmadı** | Aynı neden (oturum yok); model çağrısı yapılmadı, kota harcanmadı |
| Cursor IDE (grafik arayüz) sürümü | **Doğrulanmadı, kullanıcı elle deneyecek** | Ajan IDE'yi süremez |
| Denetçi yakalama eval'i (60 vaka) | **Doğrulanmadı** | Gerçek model çağrısı gerekir; Claude kotasını harcayan yol kullanılmadı, Cursor CLI oturumsuz. Vaka üretimi (`uret`) doğrulandı: 60 dosya |
| `model_politikasi.cursor.json` | Eklenmedi | `model_listesi_pr6.md` bağlayıcı karar belgesi olarak kalır; hiçbir kod okumayacak bir veri dosyası bayatlar. PR-6 tüketiciyi bağlarken eklenir |

Sondayı koşmak için (önce kullanıcı `agent login` yapar; CLI `%USERPROFILE%\.local\bin` ya da `%LOCALAPPDATA%\cursor-agent` altında, PATH'e eklenmesi gerekebilir): `python plugins/orkestra/scripts/orkestra.py doktor --cursor-sonda` (~1 dk, model kullanır).

## Denetçi eval'ini koşmak (kota harcamadan yol yok)

1. `python plugins/orkestra/scripts/eval_denetci.py uret <dizin>` (60 vaka, model çağrısı yok).
2. En az 3 vakayı Cursor CLI ile (`agent -p`, Claude kotası harcanmaz) `orkestra:denetci` istemiyle koştur; yanıtlar `NNN|onay|-` ya da `NNN|ret|<kod>` satırları.
3. `python plugins/orkestra/scripts/eval_denetci.py puanla <dosya>`. Eşik için 30+30 vaka gerekir; 3 vaka eşik kanıtı sayılmaz.

## IDE kontrol listesi (elle)

1. Cursor IDE'yi PowerShell/başlat menüsünden aç (Git Bash'ten değil); boş bir deneme klasörü aç.
2. Yerel Cursor kopyasının güncel olduğunu doğrula (`~/.cursor/plugins/local/orkestra`; `cursor_kur.py` yedek alarak eşler, önce betik başlığını oku).
3. Cursor'u yeniden başlat; Ayarlar > Hooks bölümünde Orkestra hook'larının (sessionStart, beforeSubmitPrompt, preToolUse, postToolUse, stop) yüklendiğini gör.
4. Ajan sohbetinde şunu iste: "Shell'de `orkestra standart yol kok_neden` çalıştır." Çıktı gelmeli.
5. Bir dosya yazdır (Write); yazma alanı dışındaki bir yolu yazdırmayı dene, engellendiğini gör.
6. `rm -rf` gibi tehlikeli bir komut iste; engellendiğini gör (`ask` yok, `deny` gelir).
7. Orkestra hook betiğini bozup (ad değiştir) bir Shell komutu iste: failClosed nedeniyle komut çalışmamalı; sonra geri al.
8. Hook çıktı kaydında (`ORKESTRA_CURSOR_DEBUG` dosyası) session_id'nin sohbet kimliğiyle aynı olduğunu bak.
9. `orkestra doktor` çalıştır; Cursor bölümünün kırık göstermediğini doğrula.
10. Sonucu (geçti/kaldı, ekran görüntüsü) buraya ekle.
