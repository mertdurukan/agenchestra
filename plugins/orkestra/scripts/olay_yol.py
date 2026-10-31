"""Gidiş yolu önerisi (I-286 P4, ADR-0109): olay-sonuç çiftlerinden eşik korumalı, şablonlu öneri. Yazmaz.

Çift = (ana, alt) kategori. Wilson başarı sayısı `duzeldi` olaylar, payda çözümlenmiş (`acik` olmayan) olaylardır.
Öneri yalnız n >= n_min ve Wilson alt sınırı >= wilson_alt_min ise çıkar; serbest metin üretilmez, yalnız ayardaki şablon.
`kullanici_duzeltme` türü, kalıp kesinliği hedefi tutturana dek (`duzeltme_oneriye_girer`) öneriye girmez.
"""
from __future__ import annotations

from kanit_olcum import wilson


def ciftler(olaylar: list[dict], ayar: dict) -> list[dict]:
    girer = bool(ayar.get("duzeltme_oneriye_girer"))
    sayim: dict[tuple, dict] = {}
    for o in olaylar:
        if o.get("sonuc") == "acik" or (o.get("tur") == "kullanici_duzeltme" and not girer):
            continue
        g = sayim.setdefault((o["ana_kategori"], o["alt_kategori"]), {"ana": o["ana_kategori"], "alt": o["alt_kategori"], "n": 0, "duzeldi": 0})
        g["n"] += 1
        g["duzeldi"] += o["sonuc"] == "duzeldi"
    out = []
    for g in sayim.values():
        g["alt_sinir"] = round(wilson(g["duzeldi"], g["n"])[0], 2)
        out.append(g)
    return sorted(out, key=lambda g: (-g["alt_sinir"], -g["n"], g["alt"]))


def oneriler(olaylar: list[dict], ayar: dict) -> list[dict]:
    esik = ayar.get("oneri_esik") or {}
    n_min, alt_min = int(esik.get("n_min", 5)), float(esik.get("wilson_alt_min", 0.5))
    sablon = str(ayar.get("yol_sablon") or "{alt}: {n} olayın {duzeldi} tanesi düzeldi (Wilson alt sınırı {alt_sinir}).")
    out = []
    for g in ciftler(olaylar, ayar):
        if g["n"] >= n_min and wilson(g["duzeldi"], g["n"])[0] >= alt_min:
            out.append(dict(g, oneri=sablon.format(pencere=ayar.get("pencere_gun", 7), **g)))
    return out
