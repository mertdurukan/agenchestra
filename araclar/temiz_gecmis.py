#!/usr/bin/env python3
"""Temiz geçmişli yayın kopyası: izlenen dosyaların mevcut halinden TEK commit'lik yeni bir depo üretir.

Eski geçmiş (ve içindeki sızmış adlar) yeni depoya taşınmaz. Betik yalnız yerel dizine yazar; push ya da
uzak depo işlemi yapmaz, eski depoya dokunmaz. Çıktı dizini boş olmalıdır.

Kullanım:
    python araclar/temiz_gecmis.py --cikti <bos-dizin> [--kaynak <depo>] [--mesaj "Initial commit"]
                                   [--ad <yazar adı>] [--eposta <noreply adresi>] [--desen <pcre>]

Çıkış kodu 0: kopya hazır ve yasak desen 0 satır (desen tanımlı değilse tarama atlanır, uyarı yazılır). 1: yasak desen bulundu (kopya silinmez, rapor yazılır).
"""
import argparse
import json
import os
import shutil
import subprocess
import sys



def git(args, cwd, **kw):
    return subprocess.run(["git", "-c", "safe.directory=*"] + args, cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", **kw)


def kaynak_desenleri(kaynak):
    """Depo dışı (gitignore'lu) yapılandırmadaki Python/PCRE uyumlu yasak içerik desenleri."""
    try:
        with open(os.path.join(kaynak, ".claude", "orkestra", "push_kapisi.json"), encoding="utf-8-sig") as f:
            return [str(x) for x in (json.load(f).get("icerik_desenleri") or [])]
    except (OSError, ValueError):
        return []


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--kaynak", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ap.add_argument("--cikti", required=True)
    ap.add_argument("--mesaj", default="Initial commit")
    ap.add_argument("--ad", default="agenchestra")
    ap.add_argument("--eposta", default="noreply@users.noreply.github.com")
    ap.add_argument("--desen", action="append", default=None,
                    help="git grep -E deseni (harf duyarsız, tekrarlanabilir); verilmezse kaynaktaki .claude/orkestra/push_kapisi.json icerik_desenleri okunur")
    a = ap.parse_args(argv)

    if os.path.exists(a.cikti) and os.listdir(a.cikti):
        print("HATA: çıktı dizini boş değil: " + a.cikti, file=sys.stderr)
        return 2
    liste = git(["ls-files", "-z"], a.kaynak)
    if liste.returncode != 0:
        print("HATA: kaynak git deposu değil: " + liste.stderr.strip(), file=sys.stderr)
        return 2
    os.makedirs(a.cikti, exist_ok=True)
    for yol in [p for p in liste.stdout.split("\0") if p]:
        kaynak, hedef = os.path.join(a.kaynak, yol), os.path.join(a.cikti, yol)
        if not os.path.isfile(kaynak):
            continue
        os.makedirs(os.path.dirname(hedef), exist_ok=True)
        shutil.copy2(kaynak, hedef)

    for komut in (["init", "-q", "-b", "main"], ["add", "-A"]):
        r = git(komut, a.cikti)
        if r.returncode != 0:
            print("HATA git %s: %s" % (komut[0], r.stderr.strip()), file=sys.stderr)
            return 2
    env = dict(os.environ, GIT_AUTHOR_NAME=a.ad, GIT_AUTHOR_EMAIL=a.eposta,
               GIT_COMMITTER_NAME=a.ad, GIT_COMMITTER_EMAIL=a.eposta)
    r = git(["commit", "-q", "-m", a.mesaj], a.cikti, env=env)
    if r.returncode != 0:
        print("HATA git commit: " + r.stderr.strip(), file=sys.stderr)
        return 2

    sayi = git(["rev-list", "--count", "HEAD"], a.cikti).stdout.strip()
    desenler = a.desen or kaynak_desenleri(a.kaynak)
    if not desenler:
        print("UYARI: yasak desen tanımlı değil (--desen ya da push_kapisi.json icerik_desenleri); içerik taraması atlandı")
    satirlar = []
    for d in desenler:
        tara = git(["grep", "-n", "-i", "-P", d], a.cikti)
        satirlar += [s for s in tara.stdout.splitlines() if s]
    print("commit sayısı: " + sayi)
    print("yasak desen eşleşmesi: %d satır" % len(satirlar))
    for s in satirlar[:20]:
        print("  " + s)
    return 0 if (sayi == "1" and not satirlar) else 1


if __name__ == "__main__":
    sys.exit(main())
