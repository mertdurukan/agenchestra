#!/usr/bin/env python3
"""Cursor birebir uyum (issue #14, PR-1): Claude koruma denetimi.

Bir dalin (HEAD) taban ile (varsayilan: origin/main ile ortak ata) farkini kurallara gore denetler:

  1. bayt_esit  : Claude'un calisan dosyalari. Eklenen, silinen ya da degisen her dosya ihlaldir.
                  Kanit: taban ve HEAD agaclarindaki dosyalarin sha256 listesi (git nesnelerinden,
                  satir sonu donusumunden bagimsiz).
  2. yazma_izin : PR yalniz bu yollara yazar. Listede olmayan yol ihlaldir.
  3. ortak_kod  : bayt_esit disindaki paylasilan dosyalar. Izinlidir ama PR govdesinde
                  "Paylasilan koda dokunuldu mu" basligi altinda "Evet" yazmiyorsa ihlaldir.

Kurallar (plugins/orkestra/cursor/koruma_kurallari.json) tabandan okunur; boylece PR kendi kuralini
gevsetemez. Tabanda dosya yoksa (cerceveyi ilk ekleyen PR) HEAD surumu kullanilir ve uyari verilir.
Cerceve dosyalarinin degismesi uyari uretir (sahip incelemesi gerekir).

Cikis kodu: 0 temiz, 1 ihlal, 2 kullanim/git hatasi. Yalniz standart kutuphane; Python 3.9+.

Kullanim:
  python araclar/cursor_koruma.py --denetle [--taban origin/main] [--govde-dosya govde.md]
  python araclar/cursor_koruma.py --liste [REF]     # bayt_esit dosyalarinin sha256 listesi (JSON)
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import re
import subprocess
import sys
from typing import Dict, List, Optional, Tuple

KURAL_YOLU = "plugins/orkestra/cursor/koruma_kurallari.json"
GOVDE_ORTAK_KOD = re.compile(r"Payla(?:ş|s)[ıi]lan koda dokunuldu mu\s*\n+\s*Evet", re.IGNORECASE)


class GitHata(Exception):
    pass


def _git(args: List[str], girdi: Optional[bytes] = None, cwd: Optional[str] = None) -> bytes:
    try:
        p = subprocess.run(["git"] + args, input=girdi, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           cwd=cwd, check=False)
    except FileNotFoundError as e:
        raise GitHata("git bulunamadi") from e
    if p.returncode != 0:
        raise GitHata("git %s: %s" % (" ".join(args), p.stderr.decode("utf-8", "replace").strip()))
    return p.stdout


def esles(yol: str, desen: str) -> bool:
    """'dizin/**' ve 'dizin/' onek eslesir; digerleri fnmatch (buyuk/kucuk harf duyarli)."""
    if desen.endswith("/**"):
        return yol.startswith(desen[:-2])
    if desen.endswith("/"):
        return yol.startswith(desen)
    return fnmatch.fnmatchcase(yol, desen)


def eslesir_mi(yol: str, desenler: List[str]) -> bool:
    return any(esles(yol, d) for d in desenler)


def kurallari_oku(taban: str, cwd: Optional[str]) -> Tuple[dict, bool]:
    """(kurallar, tabandan_mi). Tabanda yoksa HEAD surumu."""
    try:
        ham = _git(["show", "%s:%s" % (taban, KURAL_YOLU)], cwd=cwd)
        return json.loads(ham.decode("utf-8")), True
    except GitHata:
        ham = _git(["show", "HEAD:%s" % KURAL_YOLU], cwd=cwd)
        return json.loads(ham.decode("utf-8")), False


def agac_dosyalari(ref: str, cwd: Optional[str]) -> Dict[str, str]:
    """ref agacindaki {yol: blob_sha1}."""
    cikti = _git(["ls-tree", "-r", "-z", ref], cwd=cwd)
    sonuc: Dict[str, str] = {}
    for kayit in cikti.split(b"\0"):
        if not kayit:
            continue
        meta, _, yol = kayit.partition(b"\t")
        parcalar = meta.split()
        if len(parcalar) >= 3 and parcalar[1] == b"blob":
            sonuc[yol.decode("utf-8")] = parcalar[2].decode("ascii")
    return sonuc


def sha256_listesi(ref: str, desenler: List[str], cwd: Optional[str]) -> Dict[str, str]:
    """ref agacindaki desenlere uyan dosyalarin {yol: sha256} listesi (git nesne baytlarindan)."""
    dosyalar = {y: b for y, b in agac_dosyalari(ref, cwd).items() if eslesir_mi(y, desenler)}
    if not dosyalar:
        return {}
    sirali = sorted(dosyalar)
    istek = "".join(dosyalar[y] + "\n" for y in sirali).encode("ascii")
    ham = _git(["cat-file", "--batch"], girdi=istek, cwd=cwd)
    sonuc: Dict[str, str] = {}
    konum = 0
    for yol in sirali:
        son = ham.index(b"\n", konum)
        baslik = ham[konum:son].split()
        if len(baslik) != 3 or baslik[1] != b"blob":
            raise GitHata("beklenmeyen cat-file ciktisi: %r" % ham[konum:son])
        boyut = int(baslik[2])
        icerik = ham[son + 1:son + 1 + boyut]
        sonuc[yol] = hashlib.sha256(icerik).hexdigest()
        konum = son + 1 + boyut + 1
    return sonuc


def taban_coz(taban: str, cwd: Optional[str]) -> str:
    """Taban ref ile HEAD'in ortak atasi; bulunamazsa (sig klon) taban ref'in kendisi."""
    try:
        return _git(["merge-base", taban, "HEAD"], cwd=cwd).decode().strip()
    except GitHata:
        _git(["rev-parse", "--verify", taban], cwd=cwd)
        return taban


def degisenler(taban: str, cwd: Optional[str]) -> List[Tuple[str, str]]:
    """[(durum, yol)] taban -> HEAD; yeniden adlandirma ayrik silme+ekleme sayilir."""
    cikti = _git(["diff", "--name-status", "-z", "--no-renames", taban, "HEAD"], cwd=cwd)
    parca = [p for p in cikti.split(b"\0") if p]
    return [(parca[i].decode(), parca[i + 1].decode("utf-8")) for i in range(0, len(parca) - 1, 2)]


def denetle(taban_ref: str, govde: str, cwd: Optional[str] = None) -> Tuple[List[str], List[str], List[str]]:
    """(ihlaller, uyarilar, notlar)."""
    ihlal: List[str] = []
    uyari: List[str] = []
    notlar: List[str] = []
    taban = taban_coz(taban_ref, cwd)
    kurallar, tabandan = kurallari_oku(taban, cwd)
    if not tabandan:
        uyari.append("kurallar tabanda yok (cerceveyi ilk ekleyen PR); HEAD surumu kullanildi")
    bayt = kurallar["bayt_esit"]
    izin = kurallar["yazma_izin"]
    ortak = kurallar["ortak_kod"]
    cerceve = kurallar.get("cerceve", [])

    # 1. bayt esitligi: sha256 listeleri
    once = sha256_listesi(taban, bayt, cwd)
    sonra = sha256_listesi("HEAD", bayt, cwd)
    for yol in sorted(set(once) | set(sonra)):
        if yol not in sonra:
            ihlal.append("bayt_esit: silinmis: %s" % yol)
        elif yol not in once:
            ihlal.append("bayt_esit: eklenmis: %s" % yol)
        elif once[yol] != sonra[yol]:
            ihlal.append("bayt_esit: degismis: %s (sha256 %s -> %s)" % (yol, once[yol][:12], sonra[yol][:12]))
    notlar.append("bayt_esit: %d dosya karsilastirildi" % len(set(once) | set(sonra)))

    # 2. yazma izin listesi + 3. ortak kod
    ortak_degisen: List[str] = []
    tum = degisenler(taban, cwd)
    for _durum, yol in tum:
        if eslesir_mi(yol, bayt):
            continue  # yukarida raporlandi
        if eslesir_mi(yol, ortak):
            ortak_degisen.append(yol)
        elif not eslesir_mi(yol, izin):
            ihlal.append("yazma_izin: izin listesinde olmayan yol: %s" % yol)
        if yol in cerceve:
            uyari.append("denetim cercevesi degisti, sahip incelemesi gerekir: %s" % yol)
    if ortak_degisen:
        if GOVDE_ORTAK_KOD.search(govde):
            for y in ortak_degisen:
                uyari.append("ortak kod degisti (PR govdesinde isaretli): %s" % y)
        else:
            for y in ortak_degisen:
                ihlal.append("ortak_kod: %s degisti ama PR govdesinde 'Paylasilan koda dokunuldu mu' icin "
                             "'Evet' yok" % y)
    notlar.append("degisen dosya: %d" % len(tum))
    return ihlal, uyari, notlar


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--denetle", action="store_true", help="taban ile HEAD farkini denetle")
    g.add_argument("--liste", nargs="?", const="HEAD", metavar="REF", help="bayt_esit sha256 listesi (JSON)")
    ap.add_argument("--taban", default="origin/main", help="taban ref (varsayilan origin/main)")
    ap.add_argument("--govde-dosya", help="PR govdesi dosyasi (ortak kod isareti icin)")
    ap.add_argument("--kok", help="depo koku (varsayilan: gecerli dizin)")
    a = ap.parse_args(argv)
    govde = ""
    if a.govde_dosya:
        try:
            with open(a.govde_dosya, encoding="utf-8") as f:
                govde = f.read()
        except OSError as e:
            print("cursor_koruma: govde dosyasi okunamadi: %s" % e, file=sys.stderr)
            return 2
    try:
        if a.liste is not None:
            kurallar, _ = kurallari_oku(a.liste, a.kok)
            print(json.dumps(sha256_listesi(a.liste, kurallar["bayt_esit"], a.kok), indent=2, sort_keys=True))
            return 0
        ihlal, uyari, notlar = denetle(a.taban, govde, a.kok)
    except (GitHata, KeyError, ValueError) as e:
        print("cursor_koruma: hata: %s" % e, file=sys.stderr)
        return 2
    for n in notlar:
        print("not: %s" % n)
    for u in uyari:
        print("::warning::%s" % u)
    for i in ihlal:
        print("::error::%s" % i)
    print("cursor_koruma: %s (%d ihlal, %d uyari)" % ("BASARISIZ" if ihlal else "temiz", len(ihlal), len(uyari)))
    return 1 if ihlal else 0


if __name__ == "__main__":
    sys.exit(main())
