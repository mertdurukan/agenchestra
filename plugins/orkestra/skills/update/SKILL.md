---
name: update
description: Orkestra eklentisini günceller, LLM çağırmadan: yayın klonunu GitHub'dan çeker, kurulu orkestra plugin'lerini kendi kapsamıyla günceller. Kullanıcı "/orkestra:update", "orkestrayı güncelle", "eklentiyi güncelle", "yeni sürümü al" dediğinde kullan.
disable-model-invocation: false
---
# /orkestra:update

Güncelleme tamamen deterministiktir; tek komutu çalıştır ve çıktıyı olduğu gibi göster. Yorum ekleme, başka komut çalıştırma.

1. `orkestra update` çalıştır (tek başına; zincir, boru ya da yönlendirme yok). Yalnız komutları görmek için `orkestra update --kuru`.
2. Çıktının son satırını kullanıcıya ilet:
   - `GÜNCELLENDİ (klon eski → yeni)`: değişiklik yeni oturumda yüklenir; yeni oturum aç ya da `/reload-plugins`.
   - `ZATEN GÜNCEL`: yapılacak bir şey yok.
   - `HATA: neden`: nedeni olduğu gibi ilet (kirli yayın klonu, ağ, claude.exe yok…); kendi başına onarmaya girişme.
