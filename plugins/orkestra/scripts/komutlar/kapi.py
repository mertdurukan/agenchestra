"""orkestra komutları: kapi (kapı modları; ADR-0128). Model çağırmaz.

`orkestra kapi durum [--json]`   `ayarlar/*.json` içinde `mod` alanı olan her kapının etkin modunu basar
                                 (eklenti varsayılanı ve bu projenin ezmesi ayrı sütun; `block`, `genis` gibi ham değerler dahil).

Kapı modu yalnız bu komuttan ya da `ayarlar/<kapı>.json` dosyasından okunur; kural ve belge metni modu söylemez.
"""
from __future__ import annotations

import json
import os

from komutlar._ortak import BETIK_DIZINI, sd_gerekli


def kapi_satirlari(sd: str | None) -> list[dict]:
    """[{kapi, varsayilan, ezme, etkin}]: `mod` alanı metin olan her ayar dosyası, ada göre sıralı."""
    import kapi_mod as KM
    ayarlar = os.path.join(os.path.dirname(BETIK_DIZINI), "ayarlar")
    out = []
    for ad in sorted(os.listdir(ayarlar)):
        if not ad.endswith(".json"):
            continue
        kapi = ad[:-5]
        varsayilan = KM.ham_mod(kapi)
        if varsayilan is None:
            continue
        etkin = KM.ham_mod(kapi, sd)
        out.append({"kapi": kapi, "varsayilan": varsayilan, "ezme": etkin if etkin != varsayilan else None, "etkin": etkin})
    return out


def cmd_durum(a):
    sd = sd_gerekli()
    satirlar = kapi_satirlari(sd)
    if a.json:
        print(json.dumps(satirlar, ensure_ascii=False, indent=2))
        return
    for r in satirlar:
        ezme = f"  (bu projede ezildi: varsayılan {r['varsayilan']})" if r["ezme"] else ""
        print(f"{r['kapi']} {r['etkin']}{ezme}")
    print(f"{len(satirlar)} kapı")


def kaydet(alt):
    p = alt.add_parser("kapi", help="kapı modları: etkin modu ayardan oku").add_subparsers(dest="alt", required=True)
    d = p.add_parser("durum", help="her kapının etkin modu (varsayılan ve proje ezmesi)")
    d.add_argument("--json", action="store_true")
    d.set_defaults(f=cmd_durum)
