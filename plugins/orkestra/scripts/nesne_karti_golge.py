"""Nesne kartı gölge Stop kapısı (ADR-0177): yanıttaki nesne kartını doğrular (`nesne_karti_bulgu`), kart yokken en az
`tanimlayici_en_az` farklı şema.tablo(.kolon) tanımlayıcısı anlatan yanıtı `kartsiz_nesne_anlatimi` olarak işaretler.
Yalnız ölçer: hiçbir kipte engellemez, kullanıcıya mesaj vermez, hatada sessiz geçer.
Ayar `ayarlar/nesne_karti.json`; `ORKESTRA_NESNE_KARTI=0` kapatır.
"""
from __future__ import annotations

import re

import nesne_karti as NK

KAPI_KART = "nesne_karti_bulgu"
KAPI_KARTSIZ = "kartsiz_nesne_anlatimi"
_TANIMLAYICI = re.compile(r"(?<![\w./\:-])[A-Za-z_]\w+\.[A-Za-z_]\w+(?:\.[A-Za-z_]\w+)?(?![\w/\(])")


def tanimlayicilar(yanit: str, ayar: dict) -> list:
    haric = {u.lower() for u in ayar.get("tanimlayici_uzanti_haric") or []}
    govde = re.sub(r"https?://\S+", " ", re.sub(r"```.*?```", " ", yanit or "", flags=re.S))
    bulunan = []
    for m in _TANIMLAYICI.finditer(govde):
        t = m.group(0)
        if t.split(".")[-1].lower() in haric or t in bulunan:
            continue
        bulunan.append(t)
    return bulunan


def degerlendir(yanit, sd=None):
    """None ya da {'kapi', 'bulgu_sayilari', 'ornek'}; hatada None."""
    try:
        ayar = NK.ayar_oku(sd)
        if NK.mod(ayar) == "kapali" or not isinstance(yanit, str) or not yanit.strip():
            return None
        if NK.kart_var(yanit, ayar):
            # Sohbet yanıtında kart dışı sıradan maddeler olur: yalnız bilinmeyen derece bulgusu sayılır.
            b = [x for x in NK.dogrula(yanit, ayar) if not x["ayrinti"].startswith("iddia satırı")]
            if not b:
                return None
            say = {}
            for x in b:
                say[x["tur"]] = say.get(x["tur"], 0) + 1
            return {"kapi": KAPI_KART, "bulgu_sayilari": say,
                    "ornek": b[0]["ayrinti"][: int(ayar.get("alinti_max_karakter", 120) or 120)]}
        t = tanimlayicilar(yanit, ayar)
        if len(t) >= int(ayar.get("tanimlayici_en_az", 3) or 3):
            return {"kapi": KAPI_KARTSIZ, "bulgu_sayilari": {"tanimlayici": len(t)}, "ornek": ", ".join(t[:3])}
    except Exception:
        return None
    return None
