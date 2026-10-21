"""CHANGELOG.md üretici (I-139 P5, bce F54): git log başlıklarını türe göre gruplar.

Kullanım (depo kökünden): python araclar/changelog.py [--depo .] [--cikti CHANGELOG.md] [--stdout]

Saf Python, model çağırmaz. "Otomatik commit" başlıkları (oto_commit hook'u) ve birleştirme commit'leri atlanır.
Conventional Commit başlıkları (feat, fix, perf, refactor, docs) türüne göre gruplanır; biçimsiz başlıklar "Diğer"e düşer.
Çıktı deterministiktir (aynı log, aynı dosya): tarih ve saat yazılmaz.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys

TURLER = [("feat", "Özellikler"), ("fix", "Düzeltmeler"), ("perf", "Performans"), ("refactor", "Yeniden yapılandırma"),
          ("docs", "Belgeler")]
DIGER = "Diğer"
_CC = re.compile(r"^(?P<tur>feat|fix|perf|refactor|docs)(?:\((?P<kapsam>[^)]*)\))?!?:\s*(?P<ozet>.+)$", re.I)
ATLA = ("Otomatik commit", "Merge ")
BASLIK = ("# Değişiklik günlüğü\n\nBu dosya `python araclar/changelog.py` ile git geçmişinden üretilir; elle düzenlenmez. "
          "Otomatik commit ve birleştirme satırları yazılmaz.\n")


def git_log(depo: str) -> list[tuple[str, str]]:
    """[(kısa hash, başlık)] en yeniden eskiye."""
    cikti = subprocess.run(["git", "-C", depo, "-c", "safe.directory=*", "log", "--format=%h%x09%s"], capture_output=True,
                           text=True, encoding="utf-8", check=True).stdout
    sonuc = []
    for satir in cikti.splitlines():
        h, _, s = satir.partition("\t")
        if h and s:
            sonuc.append((h, s.strip()))
    return sonuc


def grupla(kayitlar: list[tuple[str, str]]) -> dict[str, list[str]]:
    gruplar: dict[str, list[str]] = {ad: [] for _, ad in TURLER}
    gruplar[DIGER] = []
    ad_of = dict(TURLER)
    for h, s in kayitlar:
        if s.startswith(ATLA):
            continue
        m = _CC.match(s)
        if m:
            kapsam = f"{m.group('kapsam')}: " if m.group("kapsam") else ""
            gruplar[ad_of[m.group("tur").lower()]].append(f"{kapsam}{m.group('ozet').strip()} ({h})")
        else:
            gruplar[DIGER].append(f"{s} ({h})")
    return gruplar


def uret(kayitlar: list[tuple[str, str]]) -> str:
    gruplar = grupla(kayitlar)
    parcalar = [BASLIK]
    for ad in [a for _, a in TURLER] + [DIGER]:
        if gruplar[ad]:
            parcalar.append(f"## {ad}\n\n" + "\n".join(f"- {x}" for x in gruplar[ad]) + "\n")
    return "\n".join(parcalar)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--depo", default=".")
    ap.add_argument("--cikti", default="CHANGELOG.md")
    ap.add_argument("--stdout", action="store_true")
    a = ap.parse_args(argv)
    metin = uret(git_log(a.depo))
    if a.stdout:
        sys.stdout.write(metin)
        return 0
    import os
    yol = a.cikti if os.path.isabs(a.cikti) else os.path.join(a.depo, a.cikti)
    with open(yol, "w", encoding="utf-8", newline="\n") as f:
        f.write(metin)
    print(f"yazıldı: {yol}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
