"""Kullanıcının kendi yapılacaklar listesi (panel). İş todo listelerinden bağımsızdır.

Yalnız kullanıcı panelden ekler ve çıkarır; iş todo.md dosyalarına dokunulmaz.
Depo: <orkestra durum klasörü>/kullanici_todo.json  →  {"maddeler": [{"id", "metin", "zaman"}]}
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ork_lib as L  # noqa: E402

DOSYA = "kullanici_todo.json"
METIN_MAKS = 2000
ADET_MAKS = 500


def _duzenle(metin: str) -> str:
    """Satır içi boşlukları teke indirir; satır sonlarını korur, ardışık boş satırları teke indirir."""
    satirlar = [" ".join(s.split()) for s in str(metin).splitlines()]
    cikti: list[str] = []
    for s in satirlar:
        if s or (cikti and cikti[-1]):
            cikti.append(s)
    return "\n".join(cikti).strip("\n")


def _yol(sd: str) -> str:
    return os.path.join(sd, DOSYA)


def _oku(yol: str) -> list[dict]:
    if not os.path.exists(yol):
        return []
    try:
        with open(yol, encoding="utf-8") as f:
            v = json.load(f)
    except (OSError, ValueError):
        return []
    m = v.get("maddeler") if isinstance(v, dict) else None
    return [x for x in (m or []) if isinstance(x, dict) and x.get("id") and x.get("metin")]


def _yaz(yol: str, maddeler: list[dict]) -> None:
    L.atomik_yaz(yol, json.dumps({"maddeler": maddeler}, ensure_ascii=False, indent=2) + "\n")


def liste(sd: str) -> list[dict]:
    return _oku(_yol(sd))


def ekle(sd: str, metin: str) -> dict:
    metin = _duzenle(metin)
    if not metin:
        raise ValueError("Madde metni boş.")
    if len(metin) > METIN_MAKS:
        raise ValueError(f"Madde en çok {METIN_MAKS} karakter olabilir.")
    yol = _yol(sd)
    os.makedirs(sd, exist_ok=True)
    with L.kilit(yol):
        maddeler = _oku(yol)
        if len(maddeler) >= ADET_MAKS:
            raise ValueError(f"En çok {ADET_MAKS} madde tutulur.")
        sayi = max([int(str(x["id"])[1:]) for x in maddeler if str(x["id"])[1:].isdigit()] or [0]) + 1
        kayit = {"id": f"K{sayi}", "metin": metin, "zaman": L.simdi()}
        maddeler.append(kayit)
        _yaz(yol, maddeler)
    return kayit


def sil(sd: str, kimlik: str) -> dict:
    yol = _yol(sd)
    with L.kilit(yol):
        maddeler = _oku(yol)
        kalan = [x for x in maddeler if x["id"] != kimlik]
        if len(kalan) == len(maddeler):
            raise LookupError("Madde bulunamadı.")
        _yaz(yol, kalan)
    return next(x for x in maddeler if x["id"] == kimlik)
