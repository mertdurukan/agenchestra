"""İşçi is-bitti teknik not doğrulaması (saf fonksiyon, G-134).

Sözleşme: {"yaklasim": str 20-400, "neden_bu_yol": str 20-400,
           "alternatifler": [{"secenek": str, "neden_elendi": str}],
           "entegrasyon": ["A → B: neden"], "riskler": [str]}
Son üç anahtar zorunlu, liste boş olabilir.
"""
from __future__ import annotations

MIN_UZ, MAX_UZ = 20, 400


def _metin(nesne: dict, anahtar: str, hatalar: list) -> None:
    if anahtar not in nesne:
        hatalar.append(f"{anahtar}: anahtar eksik")
        return
    d = nesne[anahtar]
    if not isinstance(d, str):
        hatalar.append(f"{anahtar}: metin olmalı")
    elif not (MIN_UZ <= len(d.strip()) <= MAX_UZ):
        hatalar.append(f"{anahtar}: {MIN_UZ}-{MAX_UZ} karakter olmalı (şimdi {len(d.strip())})")


def _liste(nesne: dict, anahtar: str, hatalar: list):
    if anahtar not in nesne:
        hatalar.append(f"{anahtar}: anahtar eksik")
        return None
    if not isinstance(nesne[anahtar], list):
        hatalar.append(f"{anahtar}: liste olmalı")
        return None
    return nesne[anahtar]


def dogrula(nesne) -> tuple[bool, list[str]]:
    """(tamam, hatalar). Hata metinleri eksik/geçersiz alanı adıyla söyler."""
    if not isinstance(nesne, dict):
        return False, ["teknik not bir JSON nesnesi olmalı"]
    hatalar: list[str] = []
    _metin(nesne, "yaklasim", hatalar)
    _metin(nesne, "neden_bu_yol", hatalar)
    alt = _liste(nesne, "alternatifler", hatalar)
    for i, o in enumerate(alt or []):
        if not isinstance(o, dict):
            hatalar.append(f"alternatifler[{i}]: nesne olmalı")
            continue
        for a in ("secenek", "neden_elendi"):
            if not isinstance(o.get(a), str) or not o[a].strip():
                hatalar.append(f"alternatifler[{i}].{a}: dolu metin olmalı")
    for a in ("entegrasyon", "riskler"):
        for i, o in enumerate(_liste(nesne, a, hatalar) or []):
            if not isinstance(o, str):
                hatalar.append(f"{a}[{i}]: metin olmalı")
    return not hatalar, hatalar
