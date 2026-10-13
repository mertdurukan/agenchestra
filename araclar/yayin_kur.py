"""Orkestra yayın klonunu kurar ve bu depodaki git hook'larını yazar (tek komut).

Kullanım:
    python araclar/yayin_kur.py [--yayin <klon yolu>] [--kuru]

Yayın klonu: bu deponun temiz git klonu. Marketplace (claude-orchestration) buradan okunur,
böylece plugin önbelleğine yalnız commitlenmiş kod girer. Klon elle düzenlenmez.
Varsayılan yol: ortam değişkeni ORKESTRA_YAYIN ya da C:/Mert/McD/Claude_Orkestrasyon/plugin_yayin.

Yapılanlar:
  1. Klon yoksa `git clone` (origin = bu depo, dal = çalışma dalı); varsa eşitler.
  2. .git/hooks/post-commit, post-rewrite (amend/rebase) ve orkestra-yayin-esitle.sh yazılır;
     her commit sonrası klon hızlı ileri sarılır/eşitlenir, hata commit'i bozmaz.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

DEPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VARSAYILAN_YAYIN = "C:/Mert/McD/Claude_Orkestrasyon/plugin_yayin"
HOOKLAR = os.path.join(DEPO, "araclar", "git_hooklar")


def yayin_yolu(arguman: str | None = None) -> str:
    return (arguman or os.environ.get("ORKESTRA_YAYIN") or VARSAYILAN_YAYIN).replace("\\", "/")


def git(*arg, cwd=None):
    return subprocess.run(["git", *arg], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def klon_kur(yayin: str, kuru: bool) -> None:
    dal = git("symbolic-ref", "--short", "-q", "HEAD", cwd=DEPO).stdout.strip()
    if not dal:
        sys.exit("detached HEAD: önce bir dala geç.")
    if os.path.isdir(os.path.join(yayin, ".git")):
        print(f"  klon var: {yayin}")
        return
    print(f"  git clone --branch {dal} {DEPO} {yayin}")
    if not kuru:
        os.makedirs(os.path.dirname(yayin), exist_ok=True)
        r = git("clone", "--branch", dal, DEPO.replace("\\", "/"), yayin)
        if r.returncode:
            sys.exit(r.stderr.strip())


def hook_yaz(yayin: str, kuru: bool) -> None:
    hedef = os.path.join(DEPO, ".git", "hooks")
    for ad in ("post-commit", "post-rewrite", "yayin-esitle.sh"):
        kaynak = os.path.join(HOOKLAR, ad)
        with open(kaynak, encoding="utf-8", newline="") as f:
            metin = f.read().replace("@YAYIN@", yayin)
        son = "orkestra-yayin-esitle.sh" if ad == "yayin-esitle.sh" else ad
        print(f"  hook → .git/hooks/{son}")
        if not kuru:
            os.makedirs(hedef, exist_ok=True)
            with open(os.path.join(hedef, son), "w", encoding="utf-8", newline="\n") as f:
                f.write(metin)
            try:
                os.chmod(os.path.join(hedef, son), 0o755)
            except OSError:
                pass


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--yayin", help="yayın klonu yolu (varsayılan: ORKESTRA_YAYIN ya da " + VARSAYILAN_YAYIN + ")")
    p.add_argument("--kuru", action="store_true")
    a = p.parse_args()
    yayin = yayin_yolu(a.yayin)
    print(f"Yayın klonu: {yayin}")
    klon_kur(yayin, a.kuru)
    hook_yaz(yayin, a.kuru)
    print("Tamam. Sonraki commit klonu ilerletir.")


if __name__ == "__main__":
    main()
