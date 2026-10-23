#!/bin/sh
# Orkestra yayın klonunu bu deponun çalışma dalıyla eşitler (post-commit ve post-rewrite çağırır).
# Yalnız klonun izlediği dalda (varsayılan main) atılan commit yayına çıkar; başka dalda hiçbir şey yapmadan 0 çıkar.
# Klonda origin'de olmayan iş (commit ya da değişiklik) varsa `checkout -f` ile ezilmeden önce tek kurtarma dalına (koruma/klon, her çakışma ona eklenir)
# alınır ve origin'e itilir; hiçbir iş sessizce silinmez (klon yine de elle düzenlenmez).
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
    KORUMA="koruma/klon"                                # tek kurtarma dalı: her çakışma aynı dala eklenir (I-201)
    git -C "$YAYIN" fetch -q origin "+refs/heads/$KORUMA:refs/remotes/origin/$KORUMA" 2>/dev/null || true
    ESKI=$(git -C "$YAYIN" rev-parse -q --verify "refs/heads/$KORUMA" 2>/dev/null || git -C "$YAYIN" rev-parse -q --verify "refs/remotes/origin/$KORUMA" 2>/dev/null || true)
    KIM="-c user.name=orkestra -c user.email=orkestra@localhost"
    { git -C "$YAYIN" add -A && AGAC=$(git -C "$YAYIN" write-tree)       && C=$(git -C "$YAYIN" $KIM commit-tree "$AGAC" -p HEAD -m "Klon eşitlenmeden önce korunan değişiklik")       && if [ -n "$ESKI" ]; then M=$(git -C "$YAYIN" $KIM commit-tree "$AGAC" -p "$C" -p "$ESKI" -m "Klon eşitlenmeden önce korunan değişiklik (önceki kurtarma dalıyla birleşik)"); else M="$C"; fi       && git -C "$YAYIN" update-ref "refs/heads/$KORUMA" "$M"; }       || { echo "orkestra-yayin: klondaki iş korunamadı; eşitleme yapılmadı" >&2; exit 1; }
    git -C "$YAYIN" push -q origin "$KORUMA" 2>/dev/null || true
    echo "orkestra-yayin: klonda yayına girmemiş iş '$KORUMA' dalına alındı ($SAYI commit); değişikliği kaynak depoda yap" >&2
  fi
  git -C "$YAYIN" checkout -q -f -B "$DAL" "refs/remotes/origin/$DAL" || { echo "orkestra-yayin: eşitleme başarısız" >&2; exit 1; }
) || echo "orkestra-yayin: klon güncellenemedi (commit etkilenmedi)" >&2
exit 0
