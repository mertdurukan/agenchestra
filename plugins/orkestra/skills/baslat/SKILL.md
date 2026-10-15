---
name: baslat
description: Bu projede orkestrayı aç — .claude/orkestra/ durum klasörünü kurar, .gitignore'a çalışma zamanı dosyalarını ekler ve kısa bir kullanım özeti verir. Orkestra yalnız açılmış projelerde iz tutar ve kapı uygular.
disable-model-invocation: true
---
# /orkestra:baslat

1. `orkestra baslat` çalıştır; çıktıdaki klasör yolunu not et.
2. Proje bir git deposuysa `.gitignore` dosyasına şu satırlar yoksa ekle:
   ```
   .claude/orkestra/*
   !.claude/orkestra/README.md
   .claude/agent-memory-local/
   .claude/settings.local.json
   ```
3. `orkestra kart liste` ve `orkestra maliyet ozet` çalıştır.
4. Kullanıcıya üç satır yaz:
   - Orkestra açıldı.
   - İş başlatmak için `/orkestra:is <istek>`.
   - Panel `/orkestra`, maliyet raporu `/orkestra:maliyet`.
