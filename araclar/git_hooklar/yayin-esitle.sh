#!/bin/sh
# Orkestra yayın klonunu bu deponun çalışma dalıyla eşitler (post-commit ve post-rewrite çağırır).
# Hata commit'i asla bozmaz: her durumda 0 çıkar, mesaj stderr'e gider.
# @YAYIN@ yer tutucusunu araclar/yayin_kur.py yazar.
YAYIN="@YAYIN@"
# git hook ortamı GIT_DIR vb. verir; klon komutlarını bozmasın
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_PREFIX GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES
(
  [ -d "$YAYIN/.git" ] || { echo "orkestra-yayin: klon yok ($YAYIN); araclar/yayin_kur.py çalıştır" >&2; exit 1; }
  DAL=$(git symbolic-ref --short -q HEAD) || { echo "orkestra-yayin: detached HEAD, klon ilerletilmedi" >&2; exit 1; }
  git -C "$YAYIN" fetch -q origin "+refs/heads/$DAL:refs/remotes/origin/$DAL" || { echo "orkestra-yayin: fetch başarısız" >&2; exit 1; }
  git -C "$YAYIN" checkout -q -f -B "$DAL" "refs/remotes/origin/$DAL" || { echo "orkestra-yayin: eşitleme başarısız" >&2; exit 1; }
) || echo "orkestra-yayin: klon güncellenemedi (commit etkilenmedi)" >&2
exit 0
