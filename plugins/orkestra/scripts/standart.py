"""Standartlar (ADR-0006): PR, commit, dal, review, Jira yorumu gibi yapı standartlarının kaydı.

Eklenti `standartlar/*.md` varsayılan kalıpları taşır; projede `<durum dizini>/standartlar/<ad>.md` varsa o önceliklidir.
Model çağırmaz; yalnız dosya okur/yazar.
"""
from __future__ import annotations

import os
import re

AD_DESENI = re.compile(r"^[a-z0-9_]{1,40}$")
ESKI_ONEK = "# "


def eklenti_dizini() -> str:
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "standartlar")


def proje_dizini(sd: str | None) -> str | None:
    return os.path.join(sd, "standartlar") if sd else None


def _adlar(d: str | None) -> set:
    if not d or not os.path.isdir(d):
        return set()
    return {f[:-3] for f in os.listdir(d) if f.endswith(".md") and AD_DESENI.match(f[:-3])}


def liste(sd: str | None) -> list:
    """[(ad, kaynak, yol)] — kaynak 'proje' ya da 'eklenti'; proje dosyası eklentiyi ezer."""
    e, p = eklenti_dizini(), proje_dizini(sd)
    sonuc = []
    for ad in sorted(_adlar(e) | _adlar(p)):
        if ad in _adlar(p):
            sonuc.append((ad, "proje", os.path.join(p, ad + ".md")))
        else:
            sonuc.append((ad, "eklenti", os.path.join(e, ad + ".md")))
    return sonuc


def yol(ad: str, sd: str | None) -> str | None:
    if not AD_DESENI.match(ad or ""):
        return None
    for a, _k, y in liste(sd):
        if a == ad:
            return y
    return None


def oku(ad: str, sd: str | None) -> str | None:
    y = yol(ad, sd)
    if not y:
        return None
    with open(y, encoding="utf-8") as f:
        return f.read()


def ekle(ad: str, sd: str) -> str:
    """Projede boş kalıp açar; var olanı ezmez. Dönen: dosya yolu. Geçersiz ad ya da var olan için ValueError."""
    if not AD_DESENI.match(ad or ""):
        raise ValueError(f"geçersiz ad (küçük harf, rakam, alt çizgi; en çok 40): {ad!r}")
    d = proje_dizini(sd)
    y = os.path.join(d, ad + ".md")
    if os.path.exists(y):
        raise ValueError(f"zaten var: {y}")
    os.makedirs(d, exist_ok=True)
    with open(y, "w", encoding="utf-8", newline="\n") as f:
        f.write(f"# {ad.replace('_', ' ').capitalize()} standardı\n\n**Biçim:**\n\n- \n\n**Kurallar:**\n\n- \n")
    return y
