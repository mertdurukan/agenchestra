# ADR-0122: Eklenti deposunun main kopyası yalnız birleştirme yeridir

**Durum:** Kabul edildi

**Tarih:** 2026-10-31

**Bağlam:** ADR-0050 tek `main` ve geçici oturum dalları ister, ama zorlayan mekanizma yoktu. `C:\Users\PC\Desktop\Claude-Orchestration` kopyasında başka oturumların 35 commit'siz dosyası birikti ve I-297 dalı `git merge --ff-only` ile birleşemedi.

**Karar:** `pre_tool_use`, Write/Edit/MultiEdit/NotebookEdit için korunan deponun birincil `main` kopyasına yazmayı yakalar (`scripts/main_kopya_kapisi.py`). Birincil kopya: `.git` dizin ve HEAD `refs/heads/main`; ayrı çalışma ağacında `.git` dosyadır ve serbesttir. Korunan depolar `ayarlar/main_kopya_kapisi.json` `korunan` listesinden gelir. Kapı gölgede açılır: yazı engellenmez, `kapi_golge/main_kopya_kapisi` kaydı düşer ve ajana uyarı gider. `ihlal` modunda yazı reddedilir ve ret metni `git worktree add` yolunu gösterir. Kapatma: `ORKESTRA_MAIN_KOPYA_KAPISI=0`.

**Seçenekler:**

- `izin_politikasi` ile yol reddi: elendi, yol sınıflaması ve gölge/ihlal ölçümü için yeri yok.
- Git `pre-commit` kancası ya da `core.hooksPath`: elendi, yazmayı değil commit'i yakalar.
- Dosya kilidi: elendi, sahip oturumu bloklar ve işi ayrı ağaca yönlendirmez.
- `kopyada_mi` genişletmesi: elendi, o yayın kopyası ve eşitleme içindir.
- Yalnız uyarı (ADR-0050): elendi, zorlama yok.

**Sonuçlar:** Olumlu: sorun yazma anında görünür, ihlalde engellenir. Olumsuz: Bash ile yazma (`sed -i`, `cp`) kapsam dışıdır ve kalan risktir; orkestrasız oturumlar durum klasörü olmadığından yakalanmaz. İhlale geçiş en az 7 gün ve 30 `kapi_golge` olayı, ilk 30 olayın elle sınıflanması, yanlış pozitif 0 ve bilinen ihlal vakasının görünmesiyle ayrı kararla yapılır (P-028). Geri alma: ayarda `mod: golge` ya da env ile kapatma; kod geri alınırsa davranış ADR-0050'ye döner.

**İlgili:** I-302, ADR-0050, P-028, P-022.
