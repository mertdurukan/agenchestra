#!/usr/bin/env python3
"""Görev türü kataloğu (ADR-0092): kart sınıfından varsayılan basamak, aday basamak ve kanarya sayacı.

  gorev_turleri.py tablo [--sd DIR]

Katalog `ayarlar/gorev_turleri.json`; kapı modu aynı dosyanın `mod` alanı (kapi_mod, ADR-0035), proje ezmesi
`.claude/orkestra/gorev_turleri.json`. Kapatma: ORKESTRA_GOREV_TURU_KAPISI=0.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ork_lib as L  # noqa: E402

KATALOG = os.path.join(L.PLUGIN_ROOT, "ayarlar", "gorev_turleri.json")
KAPI = "gorev_turleri"
BASAMAKLAR = ("T0", "T1", "T2", "T3", "T4")


def yukle(yol: str | None = None) -> dict:
    with open(yol or KATALOG, encoding="utf-8") as f:
        return json.load(f)


def _sinif_tur(sinif: str | None, kat: dict | None = None):
    sn = (sinif or "").strip().lower()
    for ad, t in ((kat or yukle()).get("turler") or {}).items():
        if sn and sn in (t.get("sinif") or []):
            return ad, t
    return None, None


def tur_var_mi(sinif: str | None) -> bool:
    return _sinif_tur(sinif)[0] is not None


def varsayilan_basamak(sinif: str | None) -> str | None:
    """Kart sınıfının katalog varsayılanı; sınıf katalogda yoksa ya da türün kartı yoksa None."""
    return (_sinif_tur(sinif)[1] or {}).get("varsayilan")


def kapi_eksikleri(sinif: str | None, basamak: str, neden: str | None) -> list[str]:
    """Kart açılışındaki golge uyarıları: katalog dışı sınıf, katalogdan yüksek basamak, gerekçesiz T3/T4."""
    if os.environ.get("ORKESTRA_GOREV_TURU_KAPISI") == "0":
        return []
    eksik = []
    varsayilan = varsayilan_basamak(sinif)
    if not tur_var_mi(sinif):
        eksik.append(f"sinif '{sinif}' görev türü kataloğunda yok")
    elif varsayilan and BASAMAKLAR.index(basamak) > BASAMAKLAR.index(varsayilan):
        eksik.append(f"basamak {basamak} katalog varsayılanından ({varsayilan}) yüksek: sinif '{sinif}'")
    if basamak in ("T3", "T4") and not (neden or "").strip():
        eksik.append(f"{basamak} için basamak_neden yok (Opus yalnız K1-K4 kapısından girer)")
    return eksik


def golge_yaz(sd: str, kart_is: str | None, eksik: list[str], klasor: str | None = None) -> None:
    """Eksikleri gunluk.jsonl'a `kapi_golge` olarak yazar ve stderr'e uyarır; `ihlal` kipi bu sürümde kart reddetmez."""
    if not eksik:
        return
    neden = "; ".join(eksik)
    L.jsonl_ekle(os.path.join(sd, "gunluk.jsonl"),
                 {"zaman": L.simdi(), "tur": "kapi_golge", "kapi": KAPI, "is": kart_is or "-", "neden": neden[:300]})
    print(f"orkestra (gölge, {KAPI}): {neden}", file=sys.stderr)


def tablo(sd: str, kat: dict | None = None) -> list[dict]:
    """Tür başına aday basamakta biriken kart sayısı ve kanarya tetiğine (kanarya.min_n) kalan."""
    kat = kat or yukle()
    kn = kat.get("kanarya")
    if not isinstance(kn, dict) or not kn.get("min_n"):
        raise ValueError("katalogda kanarya bloğu (min_n) yok")
    min_n = int(kn["min_n"])
    kartlar = L.kartlar(sd)
    satirlar = []
    for ad, t in (kat.get("turler") or {}).items():
        aday = t.get("aday_basamak")
        siniflar = t.get("sinif") or []
        n = 0
        if aday:
            n = sum(1 for k in kartlar if (k.get("sinif") or "").strip().lower() in siniflar
                    and (k.get("baslangic_basamak") or k.get("basamak")) == aday)
        satirlar.append({"tur": ad, "varsayilan": t.get("varsayilan"), "aday": aday, "n": n, "min_n": min_n,
                         "kalan": max(0, min_n - n) if aday else None})
    return satirlar


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    s = p.add_subparsers(dest="komut", required=True)
    t = s.add_parser("tablo")
    t.add_argument("--sd")
    a = p.parse_args(argv)
    sd = a.sd or L.durum_dizini()
    if not sd:
        print("orkestra: durum dizini bulunamadı", file=sys.stderr)
        return 2
    try:
        for r in tablo(sd):
            print(f"{r['tur']}\tvarsayilan={r['varsayilan'] or '-'}\taday={r['aday'] or '-'}\t{r['n']}/{r['min_n']}")
    except (OSError, ValueError) as e:
        print(f"orkestra: {e}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
