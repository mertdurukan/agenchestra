# Kabuk profili (P-043, ADR-0102)

Kullanıcıya terminalde çalıştırması için verilen komut, kullanıcının kabuğunun sözdizimiyle yazılır. Hook ilk kullanıcı mesajında ve komut anan mesajlarda ilgili profilin gövdesini bağlama ekler. Profil `ayarlar/kabuk_profili.json` içindeki `profil` anahtarından gelir (auto: Windows'ta powershell5, diğerlerinde bash). Proje, `<durum dizini>/standartlar/kabuk_profili.md` ile bölümleri ezebilir.

## powershell5

Kullanıcı terminali Windows PowerShell 5.1: `&&` ve `||` yok, `export`, satır başı `DEGISKEN=1 komut`, `/dev/null` ve `/c/...` yolu yok. Zincir için `;` ya da `komut1; if ($?) { komut2 }`, ortam değişkeni için `$env:AD = "değer"`, boşa atmak için `2>$null`, yol için `C:\...`. Tek komutta tek satır tercih edilir; ardışık bağımlı adımlar ayrı kod bloklarında verilir.

## powershell7

Kullanıcı terminali PowerShell 7: `&&` ve `||` var. `export`, satır başı `DEGISKEN=1 komut`, `/dev/null` ve `/c/...` yolu yok; ortam değişkeni için `$env:AD = "değer"`, boşa atmak için `2>$null`, yol için `C:\...`.

## bash

Kullanıcı terminali bash ya da zsh: `&&`, `||`, `export`, `/dev/null` kullanılabilir. PowerShell cmdlet'leri (`Get-ChildItem`, `Set-Location`) ve `$env:AD` yok.

## cmd

Kullanıcı terminali cmd.exe: `&&` var; `$env:AD`, `export`, `/dev/null` yok. Ortam değişkeni için `set AD=değer`, boşa atmak için `>nul 2>&1`.
