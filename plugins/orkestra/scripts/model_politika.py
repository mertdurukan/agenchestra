#!/usr/bin/env python3
"""Orkestra model politikası: basamak→model/effort tablosu, yasak model ve karar eşikleri tek dosyada.

Dosya: ayarlar/model_politikasi.json. Proje ezmesi: <sd>/model_politikasi.json (üst düzey alanlar; `basamak` iç içe birleşir).
calistir.js aynı dosyayı okur; okunamazsa kendi sabit yedeğini kullanır.
"""
from __future__ import annotations

import copy
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ork_lib as L  # noqa: E402

AYAR_DOSYASI = os.path.join(L.PLUGIN_ROOT, "ayarlar", "model_politikasi.json")
EZME_AD = "model_politikasi.json"
_YEDEK = {
    "surum": 1,
    "ana_ajan": {"varsayilan": "claude-sonnet-5-5"},
    "yasak": ["claude-fable-5-1"],
    "planlayici_yukseltme": {"kosul": ["belirsiz", "cok-modul"], "model": "opus"},
    "basamak": {
        "T1": {"model": "haiku", "effort": "medium"},
        "T2": {"model": "sonnet", "effort": "medium"},
        "T3": {"model": "opus", "effort": "medium"},
        "T4": {"model": "opus", "effort": "xhigh"},
    },
    "karar": {"min_n": 20, "ilk_gecis_fark": 0.05, "usd_fark": 0.10, "dk_fark": 0.10},
    "yukseltme_sirasi": ["effort", "model"],
}


def _json_sozluk(yol: str):
    try:
        with open(yol, encoding="utf-8") as f:
            v = json.load(f)
        return v if isinstance(v, dict) else None
    except (OSError, ValueError):
        return None


def yukle(sd: str | None = None) -> dict:
    cfg = _json_sozluk(AYAR_DOSYASI) or copy.deepcopy(_YEDEK)
    if sd:
        ezme = _json_sozluk(os.path.join(sd, EZME_AD))
        if ezme:
            for k, v in ezme.items():
                if k in ("basamak", "karar", "ana_ajan") and isinstance(v, dict) and isinstance(cfg.get(k), dict):
                    for a, d in v.items():
                        if isinstance(d, dict) and isinstance(cfg[k].get(a), dict):
                            cfg[k][a] = {**cfg[k][a], **d}
                        else:
                            cfg[k][a] = d
                else:
                    cfg[k] = v
    return cfg


def basamak_tablosu(sd: str | None = None) -> dict:
    return yukle(sd).get("basamak") or {}


def yasak_mi(model, sd: str | None = None) -> bool:
    """Yasak listedeki bir ad (alt dize, büyük/küçük harf duyarsız; 'fable' de yasak sayılır) mı?"""
    m = str(model or "").strip().lower()
    if not m:
        return False
    for y in yukle(sd).get("yasak") or []:
        y = str(y).strip().lower()
        if not y:
            continue
        aile = y.replace("claude-", "").split("-")[0]
        if y in m or m in y or (aile and aile in m):
            return True
    return False
