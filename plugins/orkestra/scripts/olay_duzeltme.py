"""Kullanıcı itirazı tespiti (I-286 P3, ADR-0109): gunluk.jsonl `istek` satırlarından OKUMA ANINDA, kural tabanlı.

Yazıcı yoktur, hook'a dokunulmaz. Kalıplar `ayarlar/olay_kaydi.json` `duzeltme_kaliplari` içindedir; liste boşsa
bu tür üretilmez (geri alma). Çıktı: {zaman, imza, baglam}; imza `duzeltme:<kalıp kimliği>`. Baglam mesajın
maskesiz ilk `kesit_uzunluk` karakteridir (istek satırı zaten 300 karaktere kırpılmıştır).
"""
from __future__ import annotations

import re


def derle(ayar: dict) -> list[tuple[str, "re.Pattern"]]:
    out = []
    for k in ayar.get("duzeltme_kaliplari") or []:
        try:
            out.append((str(k["id"]), re.compile(k["desen"], re.IGNORECASE | re.UNICODE)))
        except (KeyError, re.error, TypeError):
            continue
    return out


def eslesen(metin: str, kaliplar: list) -> str | None:
    """İlk eşleşen kalıbın kimliği; yoksa None."""
    for kid, rx in kaliplar:
        if rx.search(metin or ""):
            return kid
    return None


def bul(gunluk: list[dict], ayar: dict) -> list[dict]:
    kaliplar = derle(ayar)
    if not kaliplar:
        return []
    kesit = int(ayar.get("kesit_uzunluk", 120))
    out = []
    for g in gunluk:
        if g.get("tur") != "istek":
            continue
        metin = str(g.get("metin") or "")
        kid = eslesen(metin, kaliplar)
        if kid:
            out.append({"zaman": g.get("zaman"), "imza": "duzeltme:" + kid, "baglam": " ".join(metin.split())[:kesit]})
    return out
