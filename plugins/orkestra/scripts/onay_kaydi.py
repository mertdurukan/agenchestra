"""Tek onay kaydı (ADR-0036): kullanıcının açıkça istediği eylemler oturum başına bir dosyada tutulur.

Kapılar (P-016 kabuk kapısı, izin politikası) aynı eylemi ikinci kez sormadan önce bu kayda bakar.
Kayıt: <sd>/oturumlar/onay_kaydi_<oturum>.json  {"kayitlar": [{"sinif": "git", "kapsam": "tur"|"oturum"}]}
kapsam=tur: yalnız yazıldığı kullanıcı mesajının turu; sonraki her mesajda silinir.
kapsam=oturum: oturum boyunca kalır.
"""
from __future__ import annotations

import json
import os

TURLAR = ("tur", "oturum")


def _yol(sd: str, oturum) -> str:
    return os.path.join(sd, "oturumlar", f"onay_kaydi_{oturum}.json")


def _oku(sd: str, oturum) -> list[dict]:
    try:
        with open(_yol(sd, oturum), encoding="utf-8") as f:
            return [k for k in (json.load(f).get("kayitlar") or []) if isinstance(k, dict)]
    except (OSError, ValueError, AttributeError):
        return []


def _yaz(sd: str, oturum, kayitlar: list[dict]) -> None:
    yol = _yol(sd, oturum)
    if not kayitlar:
        try:
            os.remove(yol)
        except OSError:
            pass
        return
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    with open(yol, "w", encoding="utf-8") as f:
        json.dump({"kayitlar": kayitlar}, f, ensure_ascii=False)


def ekle(sd: str, oturum, sinif: str, kapsam: str = "tur") -> None:
    if not oturum or kapsam not in TURLAR:
        return
    kayitlar = [k for k in _oku(sd, oturum) if k.get("sinif") != sinif]
    kayitlar.append({"sinif": sinif, "kapsam": kapsam})
    _yaz(sd, oturum, kayitlar)


def tur_temizle(sd: str, oturum) -> None:
    """Her kullanıcı mesajında: tur kapsamlı kayıtlar silinir, oturum kapsamlı olanlar kalır."""
    if oturum:
        _yaz(sd, oturum, [k for k in _oku(sd, oturum) if k.get("kapsam") == "oturum"])


def var(sd: str, oturum, sinif: str) -> bool:
    return bool(oturum) and any(k.get("sinif") == sinif for k in _oku(sd, oturum))
