"""Kilit zaman aşımı ölçümü (salt okur).

Durum dizinindeki `<kaynak>.zaman_asimi.log` dosyalarını (ork_lib kilit yoklaması yazar) kaynak başına sayar;
süreç dağılımı, gün trendi ve ortalama beklemeyi çıkarır.

    python scripts/kilit_olcum.py --sd <durum_dizini> [--json]

Satır biçimi: `<ISO zaman> kilit_zaman_asimi pid=<n> surec=<ad> bekleme_ms=<n>`.
Biçimi tutmayan satır da kayıt sayılır (sayım satır sayısına eşit), `ayrisamayan` alanında ayrıca gösterilir.
"""
import argparse
import glob
import json
import os
import re
import sys
from collections import Counter

SONEK = ".zaman_asimi.log"
_DESEN = re.compile(r"^(\d{4}-\d{2}-\d{2})T\S+\s+\S+(?P<alanlar>.*)$")
_ALAN = re.compile(r"(\w+)=(\S+)")


def _oku(yol: str) -> dict:
    surec, gun = Counter(), Counter()
    kayit = ayrisamayan = bekleme_n = bekleme_top = 0
    en_uzun = 0
    with open(yol, encoding="utf-8", errors="replace") as f:
        for satir in f:
            satir = satir.strip()
            if not satir:
                continue
            kayit += 1
            m = _DESEN.match(satir)
            if not m:
                ayrisamayan += 1
                continue
            gun[m.group(1)] += 1
            alan = dict(_ALAN.findall(m.group("alanlar")))
            surec[alan.get("surec", "-")] += 1
            try:
                ms = int(alan["bekleme_ms"])
            except (KeyError, ValueError):
                continue
            bekleme_n += 1
            bekleme_top += ms
            en_uzun = max(en_uzun, ms)
    return {
        "kayit": kayit,
        "ayrisamayan": ayrisamayan,
        "surec": dict(surec.most_common()),
        "gun": dict(sorted(gun.items())),
        "ort_bekleme_ms": round(bekleme_top / bekleme_n, 1) if bekleme_n else None,
        "en_uzun_bekleme_ms": en_uzun if bekleme_n else None,
    }


def olc(sd: str) -> dict:
    sonuc = {}
    for yol in sorted(glob.glob(os.path.join(sd, "*" + SONEK))):
        kaynak = os.path.basename(yol)[: -len(SONEK)]
        sonuc[kaynak] = _oku(yol)
    return sonuc


def tablo(veri: dict) -> str:
    if not veri:
        return "zaman aşımı günlüğü yok"
    satirlar = [f"{'kaynak':<24}{'kayit':>7}{'ort_ms':>10}{'en_uzun_ms':>12}  surec dagilimi"]
    for kaynak, v in veri.items():
        dag = ", ".join(f"{s}={n}" for s, n in v["surec"].items())
        satirlar.append(f"{kaynak:<24}{v['kayit']:>7}{str(v['ort_bekleme_ms']):>10}"
                        f"{str(v['en_uzun_bekleme_ms']):>12}  {dag}")
    for kaynak, v in veri.items():
        satirlar.append(f"\n{kaynak} gün trendi:")
        satirlar += [f"  {g}  {n}" for g, n in v["gun"].items()]
        if v["ayrisamayan"]:
            satirlar.append(f"  ayrışamayan satır: {v['ayrisamayan']}")
    return "\n".join(satirlar)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sd", required=True, help="durum dizini (*.zaman_asimi.log burada aranır)")
    ap.add_argument("--json", action="store_true", help="JSON çıktı")
    a = ap.parse_args(argv)
    if not os.path.isdir(a.sd):
        print(f"durum dizini yok: {a.sd}", file=sys.stderr)
        return 2
    veri = olc(a.sd)
    print(json.dumps(veri, ensure_ascii=False, indent=2) if a.json else tablo(veri))
    return 0


if __name__ == "__main__":
    sys.exit(main())
