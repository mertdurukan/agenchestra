"""orkestra komutu: olay (I-286, ADR-0109). Salt okur.

`orkestra olay [ozet] [--json]`   tür ve kategori adedi, sonuç dağılımı, kapı modu, eşik korumalı gidiş yolu önerileri
"""
from __future__ import annotations

import json

from komutlar._ortak import sd_gerekli  # noqa: E402


def ozet_hesapla(sd: str) -> dict:
    import kapi_mod
    import olay_kaydi as O
    import olay_yol as Y
    olaylar = O.oku_sd(sd)
    _, ayar = O.ayar_yukle(sd=sd)
    kategori: dict[str, int] = {}
    sonuc: dict[str, int] = {}
    for o in olaylar:
        k = f"{o['ana_kategori']}>{o['alt_kategori']}"
        kategori[k] = kategori.get(k, 0) + 1
        sonuc[o["sonuc"]] = sonuc.get(o["sonuc"], 0) + 1
    return {"toplam": len(olaylar), "tur": O.tur_adetleri(olaylar), "sonuc": sonuc,
            "kategori": dict(sorted(kategori.items(), key=lambda x: -x[1])[:15]),
            "kapi_modu": kapi_mod.mod("olay_kaydi"), "oneriler": Y.oneriler(olaylar, ayar)}


def cmd_ozet(a):
    o = ozet_hesapla(sd_gerekli())
    if a.json:
        print(json.dumps(o, ensure_ascii=False, indent=1))
        return
    print(f"olay kaydı: {o['toplam']} olay · kapı modu {o['kapi_modu']}")
    print("tür: " + ", ".join(f"{k} {v}" for k, v in sorted(o["tur"].items())))
    print("sonuç: " + ", ".join(f"{k} {v}" for k, v in sorted(o["sonuc"].items())))
    for k, v in o["kategori"].items():
        print(f"  {v:5d}  {k}")
    for r in o["oneriler"]:
        print("öneri: " + r["oneri"])
    if not o["oneriler"]:
        print("öneri yok (eşik: n >= 5 ve Wilson alt sınırı >= 0,5)")


def kaydet(alt):
    p = alt.add_parser("olay", help="olay kaydı: tür, kategori, sonuç ve gidiş yolu önerileri (salt okuma)")
    p.add_argument("alt", nargs="?", default="ozet", choices=("ozet",))
    p.add_argument("--json", action="store_true")
    p.set_defaults(f=cmd_ozet)
