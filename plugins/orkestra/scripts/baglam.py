r"""Dosya yolundan 'Proje/Süreç/Görev' bağlamı çözümü. Yalnız stdlib; projeye özgü ad içermez.

Eşleme dosyası `<durum dizini>/baglam.json` (çalışma alanına özgü):
  {"surum":1, "projeler":[...], "surec_deseni":"^\d{2}_", "gorev_deseni":"^\d{3}-",
   "haric":[...], "dis_kokler":{"<mutlak yol>":"<bağlam>"}}
Eşleme yoksa ya da bozuksa bağlam hep ''.
"""
from __future__ import annotations

import json
import os
import posixpath
import re

AGIRLIK_YAZILAN = 3
AGIRLIK_OKUNAN = 1


def esleme_oku(sd: str) -> dict | None:
    try:
        with open(os.path.join(sd, "baglam.json"), encoding="utf-8-sig") as f:
            d = json.load(f)
    except Exception:
        return None
    return d if isinstance(d, dict) else None


def _duz(yol: str) -> str:
    return str(yol).replace("\\", "/")


def _mutlak_mi(p: str) -> bool:
    return p.startswith("/") or bool(re.match(r"^[A-Za-z]:/", p))


def _alt_yol(kok: str, yol: str) -> str | None:
    """yol, kok'un altındaysa göreli kısmı ('' = kökün kendisi); değilse None. Büyük/küçük harf gözetmez."""
    kok = kok.rstrip("/")
    if yol.casefold() == kok.casefold():
        return ""
    if yol.casefold().startswith(kok.casefold() + "/"):
        return yol[len(kok) + 1:]
    return None


def _desen_uyar(desen, ad: str) -> bool:
    try:
        return bool(desen) and re.search(desen, ad) is not None
    except re.error:
        return False


def yoldan(esleme: dict | None, proje: str | None, yol: str | None) -> str:
    if not esleme or not yol:
        return ""
    try:
        y = posixpath.normpath(_duz(yol))
        rel = None
        if _mutlak_mi(y):
            if proje:
                rel = _alt_yol(posixpath.normpath(_duz(proje)), y)
            if rel is None:
                for kok, deger in (esleme.get("dis_kokler") or {}).items():
                    if _alt_yol(posixpath.normpath(_duz(kok)), y) is not None:
                        return str(deger)
                return ""
        else:
            rel = y
        parcalar = [p for p in rel.split("/") if p and p != "."]
        if not parcalar or parcalar[0] == "..":
            return ""
        projeler = {str(p).casefold(): str(p) for p in esleme.get("projeler") or []}
        ad = projeler.get(parcalar[0].casefold())
        if not ad:
            return ""
        cikti = [ad]
        i = 1
        if len(parcalar) > 1:
            haric = {str(h).casefold() for h in esleme.get("haric") or []}
            p = parcalar[1]
            if p.casefold() in haric:
                return ad
            if len(parcalar) > 2 and _desen_uyar(esleme.get("surec_deseni"), p):
                cikti.append(p)
                i = 2
        if len(parcalar) > i + 1 and _desen_uyar(esleme.get("gorev_deseni"), parcalar[i]):
            cikti.append(parcalar[i])
        return "/".join(cikti)
    except Exception:
        return ""


def coz(esleme: dict | None, proje: str | None, yazilan: list, okunan: list) -> str:
    if not esleme:
        return ""
    oy: dict[str, list] = {}  # baglam -> [oy, son sıra]
    sira = 0
    for liste, agirlik in ((yazilan or [], AGIRLIK_YAZILAN), (okunan or [], AGIRLIK_OKUNAN)):
        for yol in liste:
            sira += 1
            b = yoldan(esleme, proje, yol)
            if not b:
                continue
            k = oy.setdefault(b, [0, 0])
            k[0] += agirlik
            k[1] = sira
    if not oy:
        return ""
    return max(oy.items(), key=lambda kv: (kv[1][0], kv[0].count("/"), kv[1][1]))[0]
