"""Veri kaynağı bağlantı profili (I-249, ADR-0001): ad, tür, salt okunur, kimlik kaydı adı, kapı başvurusu. BAĞLANTI KURMAZ.

Profil sır değeri taşımaz: yalnız `kimlik` (orkestra kimlik kayıt adı) ve `kapi` (kapıyı uygulayan modül yolu) anılır.
Salt okunur olmayan profil ve sır kalıbı içeren değer reddedilir. Kimlik kaydı `kimlik.liste` ile yalnız adıyla sınanır.
"""
from __future__ import annotations

import re

SIR_KALIBI = re.compile(r"(?i)(password|passwd|pwd|secret|token|apikey|api_key)\s*[=:]|://[^/\s:@]+:[^/\s@]+@|[A-Za-z0-9+/]{32,}={0,2}")
ALANLAR = {"tur", "kimlik", "kapi", "salt_okunur", "aciklama"}


class ProfilHata(Exception):
    pass


def profil(ad: str, ham: dict) -> dict:
    fazla = set(ham) - ALANLAR
    if fazla:
        raise ProfilHata(f"{ad}: bilinmeyen alan {sorted(fazla)}")
    if ham.get("salt_okunur", True) is not True:
        raise ProfilHata(f"{ad}: yalnız salt okunur profil kabul edilir")
    for k, v in ham.items():
        if isinstance(v, str) and SIR_KALIBI.search(v):
            raise ProfilHata(f"{ad}: '{k}' alanında sır kalıbı var; yalnız kayıt adı yazılır")
    if not ham.get("tur") or not ham.get("kimlik"):
        raise ProfilHata(f"{ad}: 'tur' ve 'kimlik' (kayıt adı) zorunlu")
    return {"ad": ad, "tur": ham["tur"], "salt_okunur": True, "kimlik": ham["kimlik"],
            "kapi": ham.get("kapi", ""), "aciklama": ham.get("aciklama", "")}


def profiller(ayar: dict) -> dict[str, dict]:
    return {ad: profil(ad, ham) for ad, ham in sorted((ayar.get("veri_kaynaklari") or {}).items())}


def coz(p: dict, proje: str | None = None) -> dict:
    """Kimlik kaydı var mı (yalnız ad sınanır; değer okunmaz, bağlantı kurulmaz)."""
    import kimlik
    try:
        adlar = {servis for _, servis, _ in kimlik.liste(proje)}
    except Exception:
        adlar = set()
    return dict(p, kimlik_durumu="var" if p["kimlik"] in adlar else "çözülemedi")
