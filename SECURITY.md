# Güvenlik: orkestra eklentisi

Bu belge eklentinin kullanıcıya ne yaptığını ve neyi yapmadığını tek sayfada toplar. Her madde bir karar kaydına (ADR) ya da ayar dosyasına dayanır; ADR'ler eklentiyi kullanan projenin `adr/` klasöründe tutulur.

## Sır ve kimlik

- **Sır değeri günlüğe, belgeye, hafızaya ve komut satırına yazılmaz.** Günlükler `maskele` ile maskelenir. Kayıt: ADR-0008.
- **Kimlik klasörü kullanıcı düzeyindedir:** `~/.orkestra/credentials/<proje>/<servis>.env`. Proje, depo ve eklenti dizininin dışındadır; klasör yalnız mevcut kullanıcıya açılır. Kök `ORKESTRA_KIMLIK_DIZINI` ile değişir. Kayıt: ADR-0008.
- **Tek okuyucu `orkestra kimlik` komutudur.** `liste` ve `var` yalnız ad gösterir; `calistir` değeri alt sürecin ortam değişkenine koyar, hiçbir yere yazmaz. Ortam değişkeni dosyadan önceliklidir. Kayıt: ADR-0008.
- **Ajan kimlik klasörünü okuyabilir, yazamaz.** `Read`, `Grep`, `Glob` serbesttir; `Write`, `Edit` ve her kabuk komutu reddedilir (`ayarlar/izin_politikasi.json` `kimlik_okuma`). Okunan değerin yanıta yazılmaması teknik olarak zorlanamaz, yalnız kuraldır. Kayıt: ADR-0014.
- **Sohbete yapıştırılan sır kimlik klasörüne alınır.** `UserPromptSubmit` hook'u açık atamayı, parolalı bağlantı dizesini, bilinen belirteç öneklerini ve "parola: değer" satırını yakalar; kalıplar `ayarlar/sir_kaliplari.json` içindedir. Bağlama yalnız kayıt adı gider. `ORKESTRA_SIR_YAKALA=0` kapatır. Kayıt: ADR-0011, ADR-0020.
- **Kimlik gerektiğinde ajan önce klasöre bakar,** "erişim yok" demez (`ayarlar/kimlik_hatirlatma.json`). Kayıt: ADR-0018.

## İzin ve onay

- **İzin politikası kipleri:** `genis` (kapı dışı çağrılar onaysız), `kapi` (yalnız kapılar ve yasaklar), `kapali`. `ORKESTRA_IZIN` kipi ezer. Kapılar: `git push`, GitHub ve Jira yazma sorulur; zorla push reddedilir (`ayarlar/izin_politikasi.json`).
- **Onaysız uygulama yoktur.** Yeni işte kullanıcı onayı gelmeden işin belgeleri ve `adr/` dışına yazma, `git commit/add/merge/rebase/reset` ve bağımlılık kurma ana ve alt ajanda reddedilir. Ajan kendi onayını veremez. Kayıt: ADR-0002, ADR-0009.
- **Yol bazlı push kapısı:** yasak yollara dokunan push `pre-push` kancasında reddedilir (`orkestra push-kapisi kur`). `--no-verify` ile atlanmaz kuralı korunur. Kayıt: ADR-0012.

## Otomatik commit

- **Varsayılan kapalıdır.** `ORKESTRA_OTO_COMMIT=1` ile projede açılır; yalnız düzenlenen dosya commit edilir, push yapılmaz.
- **Commit öncesi sır taraması yoktur** (aşağıda bilinen sınır).

## Bilinen sınırlar

- **Konuşma kaydında sır kalır.** Sohbete yazılan değer hook'tan önce kayda girer; mesaj değiştirilemez. Yakalama değeri başka yerlere taşımayı önler, kaydı silmez. Parolayı yenilemek gerekir. Kayıt: ADR-0020.
- **Ajan okuma yasağı kural düzeyindedir.** Read çıktısı değeri bağlama taşır; ajan değeri yeniden yazmamakla yükümlüdür. Kayıt: ADR-0014.
- **Otomatik commit içerik taramaz.** Düzenlenen dosyadaki sır yerel git geçmişine girebilir; geçmişi temizlemek zordur.
- **Serbest metin yakalama yalnız tanınan biçimleri bulur.** Etiketsiz parola satırı yazılmaz.
- **Plan doğrulama anlam denetlemez.** Kanıtın var olduğunu ve alıntının tuttuğunu sınar; iddiayı destekleyip desteklemediğine ayrı denetçi bakar.
- **Cursor'da kapılar hook yüklenirse işler.** `.cursor/hooks.json` git kökünden okunur; BOM'lu yazılırsa hook'lar sessizce yüklenmez ve izin ile onay kapıları çalışmaz. IDE sürümü sınanmamıştır, yalnız CLI ölçüldü (`GELISTIRME.md`, Cursor uyumu).

## Açık bildirim

Güvenlik açığı bulursanız herkese açık sorun kaydı açmadan önce depo sahibine özel olarak bildirin. Bu belgede sır değeri yoktur; değerler yalnız kimlik klasöründe durur.
