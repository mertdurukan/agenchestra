"""Geniş tarama gölge uyarısı (P-012 madde 4): `grep -r` / `find` geniş bir köke zaman sınırı (`timeout`) olmadan
giderse ihlal sayılır; sınırsız tarama zaman aşımıyla arka plana düşüp açık görev sızıntısı yaratır. Model çağrılmaz.

Kalıplar, kip ve uyarı metni kodda durmaz: `ayarlar/genis_tarama_hatirlatma.json` (eklenti varsayılanı) ve proje durum
dizinindeki `genis_tarama_hatirlatma.json` (anahtar bazında ezer). Bozuk/eksik dosya kapalı kip sayılır.
`ORKESTRA_GENIS_TARAMA=0` kapıyı kapatır. Kip: `golge` (yalnız günlük + uyarı), `kapali`.
"""
from __future__ import annotations

import json
import os
import re

_KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VARSAYILAN_YOL = os.path.join(_KOK, "ayarlar", "genis_tarama_hatirlatma.json")
PROJE_DOSYA = "genis_tarama_hatirlatma.json"
MODLAR = ("golge", "reddet", "kapali")
_BOLUCU = re.compile(r"&&|\|\||[;|\n]")


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


def mod(ayar: dict) -> str:
    if os.environ.get("ORKESTRA_GENIS_TARAMA") == "0":
        return "kapali"
    m = ayar.get("mod", "kapali")
    return m if m in MODLAR else "kapali"


def _eslesir(kaliplar, metin: str) -> bool:
    for k in kaliplar or []:
        try:
            if re.search(k, metin):
                return True
        except re.error:
            continue
    return False


def ihlal_mi(komut, sd=None) -> bool:
    """Komutun bir parçası (;, |, &&, || ile bölünür) tarama kalıbı taşır, geniş kök içerir ve `timeout` ile başlamaz mı?"""
    ayar = ayar_oku(sd)
    if mod(ayar) == "kapali" or not isinstance(komut, str) or not komut.strip():
        return False
    for parca in _BOLUCU.split(komut.replace("\\", "/").lower()):
        if _eslesir(ayar.get("zaman_siniri_kaliplari"), parca):
            continue
        if _eslesir(ayar.get("komut_kaliplari"), parca) and _eslesir(ayar.get("genis_kok_kaliplari"), parca):
            return True
    return False


def hatirlatma_metni(sd=None) -> str:
    return ayar_oku(sd).get("hatirlatma", "")


def arka_plana_dustu_mu(sonuc_metni, sd=None) -> bool:
    """Araç sonucu metni, komutun zaman aşımıyla arka plana düştüğünü söylüyor mu? (P2: açık görev listesine alınır.)
    Kalıplar ayarda (`arka_plana_dusen_kaliplari`); kip ve ortam değişkeni bunu kapatmaz: izleme uyarı değil kayıttır."""
    return isinstance(sonuc_metni, str) and _eslesir(ayar_oku(sd).get("arka_plana_dusen_kaliplari"), sonuc_metni)
