# Cursor doğrulama durumu (11.11.2026)

Ölçüm: Cursor CLI 2026.11.11-043ef28, `agent login` yapılmış hesap (`agent status` → "Logged in"), Windows, PowerShell. Gerçek model çağrısı yaklaşık 11 (sonda 1, hook denemesi 3, denetçi eval 6, +1 eleme). Geçici klasörler dışında hiçbir yere yazılmadı; kullanıcının `~/.cursor` eklenti kurulumu ve `~/.claude` değişmedi.

## Doğrulandı / Doğrulanmadı / Başarısız

| Madde | Durum | Kanıt / neden |
|---|---|---|
| Cursor CLI kurulumu ve girişi | Doğrulandı | `agent status` → "Logged in" |
| Adaptör birim davranışı (komut yeniden yazma, failClosed bildirimi, kurulum, rol) | Doğrulandı | `tests/test_cursor_*.py`, `test_doktor_cursor.py` (birim testi; gerçek koşu aşağıda) |
| `doktor --cursor-sonda` betiği geçici klasörde koşar, `~/.claude`'a yazmaz | Doğrulandı | Geçici proje + yük kayıtçısı; ajan çıktısı ve hook kaydı okundu |
| Sonda: oturum kimliği eşleşmesi (`CURSOR_CONVERSATION_ID` = hook `session_id`) | Doğrulandı | Sonda "geçti" |
| Sonda: komut yeniden yazma ve Shell'de çalışma, kullanıcının gerçek Cursor kurulumuyla | **Başarısız** | `~/.cursor/plugins/local/orkestra` yok (yerel kopya kurulu değil); `orkestra` Shell'de "tanınmıyor". Kurulum eksiği, adaptör hatası değil; kurulum bu oturumda yapılmadı (kullanıcı dizinine dokunulmaz). Kur: `orkestra doktor --duzelt` |
| Hook olayları gerçek ajanda tetiklenir (sessionStart, preToolUse, postToolUse, sessionEnd) | Doğrulandı | Projeye özgü `.cursor/hooks.json` (BOM'suz), `agent -p`, `ORKESTRA_CURSOR_DEBUG` günlüğü. Not: `beforeSubmitPrompt` ve `stop` günlükte görülmedi (`-p` modunda tetiklenmiyor ya da günlüğe düşmüyor; Doğrulanmadı) |
| Komut yeniden yazma (adaptör bağlıyken) | Doğrulandı | `orkestra standart yol kok_neden` → `python ".../scripts/orkestra.py" standart yol kok_neden ...`; komut gerçekten çıktı verdi |
| `deny` uygulanır | Doğrulandı | `orkestra is kapat --yerel-birlesme` → hook `permission: deny`, ajan komutu çalıştıramadı ve engel mesajını bildirdi |
| `preToolUse` failClosed | Doğrulandı | Hook betiği bozulunca Shell çağrısı "fail closed" iletisiyle engellendi, komut çalışmadı |
| `ask` kararı | Doğrulanmadı | Bu koşuda `ask` üreten bir araç çağrısı denenmedi; adaptör `ask`ı `deny`a çevirir (birim testi) |
| BOM'lu `hooks.json` hook'ları yüklemez | Doğrulanmadı | Bu koşuda BOM'lu dosya denenmedi |
| Cursor IDE (grafik arayüz) sürümü | Doğrulanmadı, kullanıcı elle deneyecek | Ajan IDE'yi süremez |
| Denetçi yakalama eval'i | Kısmen ölçüldü (6/60 vaka) | Aşağıda; eşik için 30+30 gerekir, kanıt sayılmaz |
| `model_politikasi.cursor.json` | Eklenmedi | `model_listesi_pr6.md` bağlayıcı belge; PR-6 tüketiciyi bağlarken eklenir |

## Denetçi eval'i (Cursor CLI, `agent -p --mode ask`, 3 bozuk + 3 doğru)

Vakalar 002, 003, 004 (bozuk), 001, 009, 011 (doğru); her vaka ayrı koşu, `agents/denetci.md` istemde gömülü.
Sonuç: kaçırma 0/3, yanlış ret 0/3, ret nedeni doğru 2/3 (003: gerçek kusur `kanit-yok`, denetçi `kapsam-eksik` dedi). %95 üst sınırlar %63 (n=3): eşik kanıtı değil. Not: model Claude değil Cursor'un varsayılan modeli; sonuç Claude denetçisi için geçerli sayılmaz.

## IDE kontrol listesi (elle)

1. Cursor IDE'yi PowerShell/başlat menüsünden aç (Git Bash'ten değil); boş bir deneme klasörü aç.
2. Yerel Cursor kopyasını kur/güncelle (`~/.cursor/plugins/local/orkestra`; `orkestra doktor --duzelt` ya da `cursor_kur.py`, yedek alır).
3. Cursor'u yeniden başlat; Ayarlar > Hooks bölümünde Orkestra hook'larının yüklendiğini gör.
4. Ajan sohbetinde: "Shell'de `orkestra standart yol kok_neden` çalıştır." Çıktı gelmeli.
5. Bir dosya yazdır (Write); yazma alanı dışındaki bir yolu yazdırmayı dene, engellendiğini gör.
6. Tehlikeli bir komut iste; engellendiğini gör (`ask` yok, `deny` gelir).
7. Hook betiğini bozup (ad değiştir) bir Shell komutu iste: failClosed nedeniyle çalışmamalı; sonra geri al.
8. `ORKESTRA_CURSOR_DEBUG` dosyasında session_id'nin sohbet kimliğiyle aynı olduğunu bak.
9. `orkestra doktor` çalıştır; Cursor bölümü kırık göstermemeli.
10. Sonucu (geçti/kaldı, ekran görüntüsü) buraya ekle.

Sonda: `python plugins/orkestra/scripts/orkestra.py doktor --cursor-sonda` (~1 dk, model kullanır; yerel kopya kurulu olmalı).
