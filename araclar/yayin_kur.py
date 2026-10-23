"""Orkestra yayın klonunu GitHub'dan kurar (tek komut). Hook yazmaz.

Kullanım:
    python araclar/yayin_kur.py [--yayin <klon yolu>] [--kuru]

Yayın klonu: GitHub deposunun (bu deponun `origin` adresi) temiz klonudur. Marketplace (claude-orchestration)
buradan okunur, böylece plugin önbelleğine yalnız uzak `main`'e push edilmiş kod girer. Klona hiçbir betik
yazmaz ve elle düzenlenmez; klon yalnız `orkestra guncelle` ile ilerler.
Yol önceliği: --yayin > ORKESTRA_YAYIN > <depo>/../Claude_Orkestrasyon/plugin_yayin (projeye_kur.py ile aynı).

Yapılanlar:
  1. Klon yoksa `git clone <origin adresi>`; varsa `origin`'i GitHub adresine çevirir (yerel yol ise).
  2. Hiçbir git hook'u yazılmaz. Yayın = uzak `main`'e push (kullanıcının açık isteğiyle) + `orkestra guncelle`.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

DEPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def varsayilan_yayin() -> str:
    """projeye_kur.VARSAYILAN_YAYIN ile aynı konum: depo konumundan türetilir, sabit kişisel yol içermez."""
    return os.path.join(os.path.dirname(DEPO), "Claude_Orkestrasyon", "plugin_yayin").replace("\\", "/")


def yayin_yolu(arguman: str | None = None) -> str:
    v = arguman or os.environ.get("ORKESTRA_YAYIN") or varsayilan_yayin()
    return v.replace("\\", "/")


def git(*arg, cwd=None):
    return subprocess.run(["git", *arg], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def github_adresi() -> str:
    """Bu deponun `origin` adresi; yoksa ya da yerel bir yolsa hata (klon yalnız GitHub'dan çekilir)."""
    r = git("remote", "get-url", "origin", cwd=DEPO)
    adres = r.stdout.strip()
    if r.returncode or not adres:
        sys.exit("origin yok: önce `git remote add origin <GitHub adresi>`.")
    if os.path.exists(adres):
        sys.exit(f"origin yerel bir yol ({adres}); klon yalnız GitHub'dan çekilir. `git remote set-url origin <GitHub adresi>`.")
    return adres


def klon_kur(yayin: str, kuru: bool) -> None:
    adres = github_adresi()
    if os.path.isdir(os.path.join(yayin, ".git")):
        mevcut = git("remote", "get-url", "origin", cwd=yayin).stdout.strip()
        if mevcut == adres:
            print(f"  klon var, origin GitHub: {yayin}")
            return
        print(f"  git remote set-url origin {adres}  (şimdiki: {mevcut or 'yok'})")
        if not kuru:
            r = git("remote", "set-url", "origin", adres, cwd=yayin)
            if r.returncode:
                sys.exit(r.stderr.strip())
        return
    print(f"  git clone --branch main {adres} {yayin}")
    if not kuru:
        os.makedirs(os.path.dirname(yayin), exist_ok=True)
        r = git("clone", "--branch", "main", adres, yayin)
        if r.returncode:
            sys.exit(r.stderr.strip())


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--yayin", help="yayın klonu yolu (varsayılan: ORKESTRA_YAYIN ya da <depo>/../Claude_Orkestrasyon/plugin_yayin)")
    p.add_argument("--kuru", action="store_true")
    a = p.parse_args()
    yayin = yayin_yolu(a.yayin)
    print(f"Yayın klonu: {yayin}")
    klon_kur(yayin, a.kuru)
    print("Tamam. Yayın: uzak main'e push + `orkestra guncelle`.")


if __name__ == "__main__":
    main()
