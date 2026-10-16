---
name: neredeyiz
description: "Durum özeti çıkarır: bu konuşmada ne yapıyoruz, nereye kadar geldik, sırada ne var. Şu ifadelerde tetiklenir: 'nerede kaldık', 'ne yapıyoruz', 'şu ana kadar ne yaptık', 'durum özeti', 'özet geç', 'kaybettim', 'baştan anlat', 'recap', '/neredeyiz', '/orkestra:neredeyiz'. Uzun veya dağılmış konuşmalarda kullanıcıyı yeniden yönlendirmek için. Tek bir teknik soruya cevap verirken veya kullanıcı bir dosyanın/metnin özetini istediğinde KULLANMA."
---

## Amaç

Kullanıcı yönünü kaybettiğinde konuşmayı yeniden okumadan durumu kavramasını sağlamak. Çıktı bir özet değil, oryantasyondur: nereden başladık, şu an neredeyiz, bir sonraki adım ne.

## Kapsam sınırı

Sadece bu konuşmada olanları görebilirsin. Kullanıcı önceki sohbetlerdeki bir işi kastediyorsa bunu tek cümleyle söyle ve elindekiyle devam et; uydurma.

## Kaynak

- İlk istek ve sonradan değişen hedefler (bkz. Hedef kayması)
- Verilen kararlar ve gerekçesi kısa
- Üretilen çıktılar; Claude Code'da bu oturumda değişen dosyalar (yol olarak), claude.ai'da kod çalıştırma açıksa `/mnt/user-data/outputs` içeriği
- Yarım kalanlar, başarısız denemeler, cevaplanmamış sorular

Emin olmadığını "belirsiz" olarak işaretle.

## Hedef kayması

Özeti yazmadan önce konuşmayı şu sinyaller için tara:
- Açık dönüş ifadeleri: "aslında", "vazgeçtim", "boşver", "onun yerine", "bir de", "şunu da ekleyelim"
- Kullanıcının reddettiği veya cevapsız bıraktığı öneriler
- Sorulup cevaplanmadan geçilmiş konular
- İlk isteğin konusu ile son 3 mesajın konusu farklıysa: sessiz kayma

Kayma varsa **Hedef** başlığını iki satır yaz:
Başlangıç: ... → Şu anki: ...
Sessiz kaymada tek cümle ekle: "Bu geçiş konuşulmadan oldu."
Kayma yoksa konuyu hiç açma.

## Format

1. **Hedef** — 1 cümle.
2. **Adımlar** — numaralı, tek satır, durum işaretli: ✅ bitti · 🔄 devam · ⏸️ karar bekliyor · ❌ denendi olmadı
3. **Şu an** — 1-2 cümle: hangi adımdayız, neden burada durduk.
4. **Sıradaki adım** — en fazla 3 madde, eyleme dönük, fiille başlasın.
5. **Açık sorular** — yoksa bu başlığı hiç yazma.

## Kurallar

- 200 kelimeyi geçme. Kullanıcı "aç" derse sınırsız.
- Kararı ve sonucu yaz, muhakemeyi tekrar etme.
- Konuşma 3 mesajdan kısaysa listeye zorlama, tek paragraf yaz.
- "Daha önce söylemiştim" tonu kurma; suçlayıcı olma.
- Sonda soru sorma; sadece sıradaki adımı öner.
