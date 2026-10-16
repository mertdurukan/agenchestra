#!/bin/sh
# Orkestra yayın klonunu bu deponun çalışma dalıyla eşitler (post-commit ve post-rewrite çağırır).
# Yalnız klonun izlediği dalda (varsayılan main) atılan commit yayına çıkar; başka dalda hiçbir şey yapmadan 0 çıkar.
# Klonda origin'de olmayan iş (commit ya da değişiklik) varsa `checkout -f` ile ezilmeden önce koruma/klon-<dal>-<damga>
# dalına alınır ve origin'e itilir; hiçbir iş sessizce silinmez (klon yine de elle düzenlenmez).
# Hata commit'i asla bozmaz: her durumda 0 çıkar, mesaj stderr'e gider.
# @YAYIN@ yer tutucusunu araclar/yayin_kur.py yazar.
YAYIN="@YAYIN@"
# git hook ortamı GIT_DIR vb. verir; klon komutlarını bozmasın
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_PREFIX GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES
(
  [ -d "$YAYIN/.git" ] || { echo "orkestra-yayin: klon yok ($YAYIN); araclar/yayin_kur.py çalıştır" >&2; exit 1; }
  DAL=$(git symbolic-ref --short -q HEAD) || exit 0   # detached HEAD: yayına çıkmaz
  KLON_DAL=$(git -C "$YAYIN" symbolic-ref --short -q HEAD) || { echo "orkestra-yayin: klon dalı okunamadı" >&2; exit 1; }
  [ "$DAL" = "$KLON_DAL" ] || exit 0                  # başka dal: yayına çıkmaz
  git -C "$YAYIN" fetch -q origin "+refs/heads/$DAL:refs/remotes/origin/$DAL" || { echo "orkestra-yayin: fetch başarısız" >&2; exit 1; }
  SAYI=$(git -C "$YAYIN" rev-list --count "refs/remotes/origin/$DAL..HEAD" 2>/dev/null || echo 0)
  KIRLI=$(git -C "$YAYIN" status --porcelain 2>/dev/null)
  if [ "$SAYI" != "0" ] || [ -n "$KIRLI" ]; then
    KORUMA="koruma/klon-$DAL-$(date +%Y%m%d-%H%M%S)"
    git -C "$YAYIN" checkout -q -B "$KORUMA" && git -C "$YAYIN" add -A       && { git -C "$YAYIN" -c user.name=orkestra -c user.email=orkestra@localhost commit -q --no-verify              -m "Klon eşitlenmeden önce korunan değişiklik" 2>/dev/null || true; }       || { echo "orkestra-yayin: klondaki iş korunamadı; eşitleme yapılmadı" >&2; exit 1; }
    git -C "$YAYIN" push -q origin "$KORUMA" 2>/dev/null || true
    echo "orkestra-yayin: klonda yayına girmemiş iş '$KORUMA' dalına alındı ($SAYI commit); değişikliği kaynak depoda yap" >&2
  fi
  git -C "$YAYIN" checkout -q -f -B "$DAL" "refs/remotes/origin/$DAL" || { echo "orkestra-yayin: eşitleme başarısız" >&2; exit 1; }
) || echo "orkestra-yayin: klon güncellenemedi (commit etkilenmedi)" >&2
exit 0
