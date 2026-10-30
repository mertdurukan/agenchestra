"""I-271 P4: iş kaydı hijyeni yardımcıları — ölü yol ve terk edilmiş boş iş (salt okuma).

- olu_yollar: durum=acik olup klasörü diskte olmayan iş kayıtları (göreli klasör proje köküne göre çözülür).
- terk_isler: bakim.bos_isler ölçütüne (kartsız, todo'suz, boş planlı) uyan, `terk_is_saat` (is_esleme.json,
  varsayılan 24) saatten eski ve kendisine yazılmış maliyet satırı olmayan açık işler. Kapatma bakim --kapat
  --uygula yolundan yapılır; bu modül hiçbir kaydı değiştirmez.
"""
from __future__ import annotations

import json
import os

import ork_lib as L

ESLEME_AYAR_YOLU = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ayarlar", "is_esleme.json")
TERK_SAAT_VARSAYILAN = 24.0


def esleme_ayari(sd: str) -> dict:
    """Eklenti ayarlar/is_esleme.json, üstüne proje <durum>/is_esleme.json (anahtar bazında; hook._esleme_ayari ile aynı sıra)."""
    ayar: dict = {}
    for yol in (ESLEME_AYAR_YOLU, os.path.join(sd, "is_esleme.json")):
        try:
            with open(yol, encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict):
                ayar.update(d)
        except Exception:
            continue
    return ayar


def terk_saat(sd: str) -> float:
    try:
        v = float(esleme_ayari(sd).get("terk_is_saat", TERK_SAAT_VARSAYILAN))
        return v if v > 0 else TERK_SAAT_VARSAYILAN
    except (TypeError, ValueError):
        return TERK_SAAT_VARSAYILAN


def proje_koku(sd: str) -> str:
    """<proje>/.claude/orkestra → <proje>."""
    return os.path.dirname(os.path.dirname(os.path.abspath(sd)))


def klasor_coz(sd: str, klasor: str) -> str:
    if not klasor:
        return ""
    return os.path.normpath(klasor if os.path.isabs(klasor) else os.path.join(proje_koku(sd), klasor))


def olu_yollar(sd: str) -> list[dict]:
    """Açık olup klasörü diskte bulunmayan (ya da klasör alanı boş) iş kayıtları."""
    import is_kaydi
    out = []
    for g in is_kaydi.is_liste(sd, "acik"):
        yol = klasor_coz(sd, str(g.get("klasor") or ""))
        if not yol or not os.path.isdir(yol):
            out.append({"id": g["id"], "baslik": str(g.get("baslik") or ""), "klasor": str(g.get("klasor") or "")})
    return out


def maliyetli_isler(sd: str) -> set[str]:
    try:
        return {str(r.get("is")) for r in L.maliyet_kayitlari(sd) if r.get("is") not in (None, "", "-")}
    except Exception:
        return set()


def terk_isler(sd: str, bos_isler_fn, saat: float | None = None) -> list[dict]:
    """bos_isler_fn(sd, saat) ölçütüne uyan ve maliyet satırı olmayan işler ('terk')."""
    saat = terk_saat(sd) if saat is None else saat
    haric = maliyetli_isler(sd) | {str(g["id"]) for g in olu_yollar(sd)}  # ölü yol ayrı listelenir, kapatılmaz
    return [dict(g, saat_esigi=saat) for g in bos_isler_fn(sd, saat) if str(g["id"]) not in haric]
