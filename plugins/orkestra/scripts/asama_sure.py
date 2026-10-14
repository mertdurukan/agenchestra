"""asama_sure: ajan x surec bazinda sure/maliyet dagilimi (PAR-0 olcum tabani, G-054).

Kaynak: maliyet.jsonl (ork_lib.maliyet_kayitlari ile tekillestirilmis). Salt okuma.
Bilinen kusur N0: kapi ajanlari defterde cogu zaman ajan=orkestra:isci-t1, surec=is gorunur; bu betik
ayirmaz, o grubu 'isci-t1/is (kapı karışık, N0)' notuyla raporlar.

Kullanim: python asama_sure.py --defter <maliyet.jsonl> [--gun N] [--gorev G-xxx] [--json]
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

N0_NOTU = "isci-t1/is (kapı karışık, N0)"
N0_ANAHTAR = ("orkestra:isci-t1", "is")


def _sayi(v):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v)


def _zaman(s):
    if not isinstance(s, str):
        return None
    try:
        t = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.astimezone()
    return t


def kayitlar(defter: str) -> list[dict]:
    """Tekillestirilmis satirlar; yalniz dict satirlar (bozuk/bos atlanir)."""
    if not os.path.isfile(defter):
        return []
    import ork_lib as L
    with tempfile.TemporaryDirectory() as sd:
        hedef = os.path.join(sd, "maliyet.jsonl")
        with open(defter, encoding="utf-8", errors="replace") as f, \
                open(hedef, "w", encoding="utf-8") as o:
            for satir in f:
                satir = satir.strip()
                if not satir:
                    continue
                try:
                    r = json.loads(satir)
                except ValueError:
                    continue
                if isinstance(r, dict):
                    o.write(json.dumps(r) + "\n")
        try:
            return [r for r in L.maliyet_kayitlari(sd) if isinstance(r, dict)]
        except Exception:
            return []


def yuzdelik(degerler: list[float], p: float) -> float:
    d = sorted(degerler)
    if not d:
        return 0.0
    if len(d) == 1:
        return d[0]
    k = (len(d) - 1) * p
    a = int(k)
    b = min(a + 1, len(d) - 1)
    return d[a] + (d[b] - d[a]) * (k - a)


def hesapla(satirlar: list[dict], gun: float | None = None, gorev: str | None = None) -> list[dict]:
    esik = None
    if gun is not None:
        esik = datetime.datetime.now().astimezone() - datetime.timedelta(days=gun)
    gruplar: dict = {}
    for r in satirlar:
        if gorev is not None and r.get("gorev") != gorev:
            continue
        sure = _sayi(r.get("sure_ms"))
        if sure is None:
            continue
        if esik is not None:
            t = _zaman(r.get("zaman"))
            if t is None or t < esik:
                continue
        anahtar = (str(r.get("ajan") or "?"), str(r.get("surec") or "?"))
        g = gruplar.setdefault(anahtar, {"dk": [], "usd": 0.0})
        g["dk"].append(sure / 60000.0)
        g["usd"] += _sayi(r.get("maliyet_usd")) or 0.0
    genel = sum(sum(g["dk"]) for g in gruplar.values())
    out = []
    for (ajan, surec), g in gruplar.items():
        toplam = sum(g["dk"])
        satir = {
            "ajan": ajan, "surec": surec, "sayi": len(g["dk"]),
            "toplam_dk": round(toplam, 2),
            "medyan_dk": round(yuzdelik(g["dk"], 0.5), 2),
            "p95_dk": round(yuzdelik(g["dk"], 0.95), 2),
            "toplam_usd": round(g["usd"], 6),
            "pay_yuzde": round(toplam / genel * 100, 2) if genel else 0.0,
        }
        if (ajan, surec) == N0_ANAHTAR:
            satir["not"] = N0_NOTU
        out.append(satir)
    out.sort(key=lambda x: x["toplam_dk"], reverse=True)
    return out


def md(gruplar: list[dict]) -> str:
    if not gruplar:
        return "Aşama süre ölçümü: kayıt yok.\n"
    s = ["| ajan | süreç | sayı | toplam dk | medyan dk | p95 dk | toplam USD | pay % | not |",
         "|---|---|---:|---:|---:|---:|---:|---:|---|"]
    for g in gruplar:
        s.append(f"| {g['ajan']} | {g['surec']} | {g['sayi']} | {g['toplam_dk']:.2f} | {g['medyan_dk']:.2f} | "
                 f"{g['p95_dk']:.2f} | {g['toplam_usd']:.4f} | {g['pay_yuzde']:.1f} | {g.get('not', '')} |")
    return "\n".join(s) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="ajan x surec sure dagilimi")
    ap.add_argument("--defter", required=True, help="maliyet.jsonl yolu")
    ap.add_argument("--gun", type=float, default=None)
    ap.add_argument("--gorev", default=None)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    gr = hesapla(kayitlar(a.defter), a.gun, a.gorev)
    if a.json:
        print(json.dumps({"gruplar": gr}, ensure_ascii=False, indent=2))
    else:
        sys.stdout.write(md(gr))
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
