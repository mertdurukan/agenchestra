# Eklenti geliştirme notları

Bu dosya eklentiyi geliştirenler içindir. Kullanım kuralları için `KURALLAR.md` dosyasına bak.

## Yayın akışı
Oturumlar eklentiyi `~/.claude/plugins/cache/claude-orchestration/<plugin>/<sürüm>/` altındaki önbellek kopyasından yükler (göreli yol girdisine rağmen). Sürüm commit SHA'sıdır (12 hane); `version` alanı bilerek yoktur.

1. Eklenti deposunda geliştir.
2. `main` dalına commit at.
3. Post-commit ve post-rewrite hook'u (`araclar/git_hooklar/yayin-esitle.sh`; kurulum `araclar/yayin_kur.py`) yayın klonunu ilerletir. Başka dalda ya da detached HEAD'de hiçbir şey yapmaz.
4. `orkestra guncelle` çalıştır (yayın klonu kirliyse reddeder). Çalıştırmazsan `autoUpdate` ilk mesajdan en çok 10 dk sonra alır.
5. Sonraki oturumda ya da `/reload-plugins` ile yeni sürüm yüklenir.

Notlar:
- Güncelleme commit'i değil, marketplace klasörünün çalışma ağacını kopyalar. Bu yüzden marketplace, geliştirme deposunun temiz git klonudur (yayın klonu). Yayın klonunu elle düzenleme.
- Commitlenmemiş iş yayına girmez.
- SessionStart bayatlık uyarısı önbellek kopyası ile yayın klonu arasındaki farkı bildirir.
- `validate --strict` sürüm alanı olmadığı için hep "No version specified" ile düşer (bilinçli).
- `orkestra` CLI'ı da önbellekten çalışır. HTML paneli geliştirme deposu yolundan `python <depo>/plugins/orkestra/scripts/orkestra.py panel` ile başlat.

## Paylaşılan git indeksi tuzağı
Aynı depoda birden çok oturum aynı indeksi kullanır. Başka oturumun commit'i senin sahnelediğin dosyaları da alır. Bu yüzden commit'i ana indeksle değil, geçici `GIT_INDEX_FILE` ile kur.

Adımlar:
1. Güncel HEAD'i al: `OLD=$(git rev-parse HEAD)`.
2. Geçici indeks tanımla: `export GIT_INDEX_FILE=$(mktemp -u)`.
3. Ağacı oku: `git read-tree $OLD`. `read-tree` ile `commit-tree` arasında HEAD değişmemeli; değiştiyse baştan başla.
4. Yalnız kendi dosyalarını ekle: `git add <dosyalar>` (geçici indekse işler; ana indekse dokunmaz).
5. Ağacı yaz: `TREE=$(git write-tree)`.
6. Commit nesnesini oluştur: `NEW=$(git commit-tree $TREE -p $OLD -m "<mesaj>")`.
7. Dalı ilerlet: `git update-ref refs/heads/main $NEW $OLD`.
8. Geçici indeksi kaldır: `unset GIT_INDEX_FILE`, ardından geçici dosyayı sil.
9. Doğrula: `git diff --stat $OLD $NEW` çıktısında yalnız kendi dosyaların olmalı.
10. Ana indeksi eşitle: `git reset -q HEAD -- <yollar>`. Yapmazsan sonraki commit işini geri alır.

## Test takımı
- Tam paket: `python plugins/orkestra/scripts/test_paralel.py` (paralel koşar; yaklaşık 4 dk).
- Değişiklikten sonra commit'ten önce koş.
- CLI çağrıları süreç içinde koşar: test yardımcıları (`test_cekirdek.kos`, `test_test_kapisi.kos` vb.) `tests/ic_kos.py` üzerinden `orkestra.py`/`hook.py` `main()`'ini aynı argv, cwd, ortam ve stdin ile çağırır. Alt süreç başına ~0,5 sn gidiyordu; en yavaş dosyalar 5-10 kat hızlandı (15.10). Ev dizinini değiştiren testlerde içe aktarımda hesaplanan ev yolları (GENEL_DIZIN türevleri) çağrı süresince yeni eve çevrilir.
- Gerçek alt süreçle uçtan uca doğrulama: `ORKESTRA_IC_KOS=0` ile koş (yayın öncesi ya da süreç içi farkından şüphelenince).
- Yeni testte CLI'yi `subprocess.run` ile değil `ic_kos.kos([CLI, ...], cwd=..., env=...)` ile çağır; uçtan uca kalması gereken (hook betiği, git, node) çağrılar alt süreçte kalır.

## Panel test sunucusu
- Panel sayfaları: `/` Şimdi, `/maliyet`, `/verim` (`/analitik` yönlendirir). Ortak varlıklar `assets/ortak.css` ve `ortak.js`.
- Test sunucusu `_kos <port>` ile açılınca `~/.claude/orkestra-panel/panel.json` dosyasının üzerine yazılır. Testten sonra önceki içeriği geri yaz.
- POST `/ac` gerçek ya da uydurma oturum kimliğiyle denenmez; masaüstü süreci başlatır.
