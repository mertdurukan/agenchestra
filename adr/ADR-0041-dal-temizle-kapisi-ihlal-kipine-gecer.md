# ADR-0041: dal_temizle kapısı doğrudan ihlal kipine geçer

**Durum:** Kabul edildi

**Tarih:** 2026-10-23

**Bağlam:**

I-201'de eklenen `dal_temizle` kapısı P-028 gereği gölge kipte açıldı (ADR-0035). Kullanıcı gölge ölçümünü beklemeden `ihlal` kipine geçmeyi açıkça istedi.

**Karar:**

`plugins/orkestra/ayarlar/dal_temizle.json` içinde `mod` değeri `ihlal` olur. SessionStart ve `orkestra is kapat`, `main`'e tamamen birleşmiş ve worktree'de açık olmayan dalları önce `git bundle` ile `_arsiv/<proje>/` altına yedekler, sonra `git branch -d` ile siler.

**Seçenekler:**

- Gölgede birkaç oturum ölçmek: elendi, kullanıcı doğrudan geçişi istedi.
- Proje ezmesiyle yalnız DemoRoot'de açmak: elendi, kapı her projede aynı davranmalı (P-022).

**Sonuçlar:**

- Olumlu: artık dallar kendiliğinden temizlenir, tek `main` korunur.
- Olumsuz: yanlış aday seçilirse dal silinir; `branch -d` birleşmemiş dalı reddeder ve bundle yedeği vardır, risk düşüktür.
- Geri alma: ayarda `mod` değerini `golge` yap ya da `ORKESTRA_DAL_TEMIZLE=0`; silinen dal bundle'dan `git fetch <bundle> <dal>` ile döner.

**İlgili:** I-201, P-028, ADR-0035, ADR-0050 (DemoRoot)
