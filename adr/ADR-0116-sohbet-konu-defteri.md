# ADR-0116: Sohbet konu defteri

**Durum:** Kabul edildi

**Tarih:** 2026-10-31

**Bağlam:**

Orkestra'da sohbet başına konu listesi yoktu. `niyet.jsonl` yalnız son niyeti tutar, hesap geneldir ve 3 MB'ta döner. `gunluk.jsonl` karışık olay günlüğüdür; konu sayısı, süre ve konu başına tur ondan türetilemez. Kullanıcı her sohbette konuşulan konuların saniyeli zamanla kaydını ve konu sayısının sonradan izlenmesini istedi (I-298).

**Karar:**

(1) Proje başına `.claude/orkestra/konular.jsonl`, ekleme-only ve kilitli (`ork_lib.jsonl_ekle`). Olaylar `ac`, `tur`, `aday`; sayım yalnız `ac` ile yapılır. (2) Hook sohbetin ilk isteğinde konu açar (`kaynak=hook`), her turu sayar. (3) Konu sınırı deterministik tetiklenir: jeton Jaccard örtüşmesi düşükse (`ortusme`) ya da 60 dk boşlukta (`bosluk`) `aday` yazılır ve ajana tek satır hatırlatılır; yeni konuyu yalnız ajan açar (`orkestra konu ac`). (4) `orkestra konu liste|rapor [--gun] [--tum] [--etiket]` kayıttan yeniden hesaplar. (5) Gölge modda başlar (P-028); başlık ≤120 karakter ve maskelenir; `ORKESTRA_KONU_DEFTERI=0` kapatır. (6) Kural P-047.

**Seçenekler:**

- `niyet.jsonl`'i genişletmek: elendi, hesap geneli, 3 MB'ta döner, kalıcı geçmiş kaybolur.
- `gunluk.jsonl`'dan türetmek: elendi, karışık günlükte konu sınırı yok, taranması pahalı.
- LLM ile konu kümeleme: elendi, önce deterministik tetikleyici; belirsizlik ölçümde görünürse eklenir (ADR-0114 ile aynı ilke).
- Yalnız ajan yazsın: elendi, ajan unutur; hook ilk konuyu ve turları güvenceye alır.

**Sonuçlar:**

Olumlu: konu sayısı, süre ve tur sayısı kalıcı ve sorgulanabilir; tüm projelerde varsayılan. Olumsuz: örtüşme eşiği yanlış alarm üretebilir (ölçümle ayarlanır); hook her istekte küçük bir dosya okur. Geri alma: `ORKESTRA_KONU_DEFTERI=0` ya da `konu_defteri.json` ayarı; dosya silinmez.

**İlgili:** I-298, P-047, P-028, ADR-0112, ADR-0114
