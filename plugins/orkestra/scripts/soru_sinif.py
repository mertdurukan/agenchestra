"""Soru sınıflayıcı (G-120): kullanıcı mesajı bilgi sorusuysa tek satırlık not üretir; model çağrılmaz.

Kalıplar ve eşikler kodda durmaz: `ayarlar/soru_sinif.json` (eklenti varsayılanı) ve proje durum
dizinindeki `soru_sinif.json` (anahtar bazında ezer) içinden okunur. Bozuk/eksik dosya varsayılana düşer.
"""
from __future__ import annotations

import json
import os
import re

_KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VARSAYILAN_YOL = os.path.join(_KOK, "ayarlar", "soru_sinif.json")
PROJE_DOSYA = "soru_sinif.json"


def _json_oku(yol: str):
    try:
        with open(yol, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except Exception:
        return None


def ayar_oku(sd=None) -> dict:
    ayar = _json_oku(VARSAYILAN_YOL) or {}
    if sd:
        proje = _json_oku(os.path.join(sd, PROJE_DOSYA))
        if proje:
            ayar.update(proje)
    return ayar


def _normallestir(metin: str) -> str:
    return metin.replace("İ", "i").replace("I", "ı").lower()


def _eslesir(kaliplar, metin: str) -> bool:
    for k in kaliplar or []:
        try:
            if re.search(k, metin):
                return True
        except re.error:
            continue
    return False


def bilgi_sorusu_mu(metin, ayar: dict) -> bool:
    m = _normallestir((metin or "").strip())
    if not m:
        return False
    if len(m) > ayar.get("uzun_max_karakter", 0):
        return False
    if _eslesir(ayar.get("eylem_kaliplari"), m):
        return False
    if m.endswith("?") and len(m) <= ayar.get("kisa_max_karakter", 0):
        return True
    if _eslesir(ayar.get("soru_kaliplari"), m):
        return True
    eki = ayar.get("soru_eki_regex")
    return bool(eki) and _eslesir([eki], m)


def not_metni(metin, sd=None) -> str:
    ayar = ayar_oku(sd)
    return ayar.get("not", "") if bilgi_sorusu_mu(metin, ayar) else ""
