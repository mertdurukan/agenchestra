"""Öneri kapısı, yanıt denetimi (ADR-0125, ADR-0111): düzeltme önerisi sonradan yakalayan ya da alışkanlığa bağlayan bir
çözümse (hatırlatma, uyarı, tur sonu denetimi) ve yanıtta önleme merdiveni akıl yürütmesi yoksa (üst basamak, mevcut kapı,
üretim noktası) ölçüm kaydı düşer. Yalnız ölçer: engellemez, kullanıcıya gürültü yapmaz, model çağrılmaz.

Kalıplar, kip ve eşikler kodda durmaz: `ayarlar/onleme_yanit.json` (eklenti varsayılanı) ve proje durum dizinindeki
`onleme_yanit.json` (anahtar bazında ezer). Kip: `golge`, `kapali`. `ORKESTRA_ONLEME_YANIT=0` kapatır.
"""
from __future__ import annotations

import json
import os
import re

_KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VARSAYILAN_YOL = os.path.join(_KOK, "ayarlar", "onleme_yanit.json")
PROJE_DOSYA = "onleme_yanit.json"
KURAL = "onleme_basamagi"
MODLAR = ("golge", "kapali")
_CUMLE_SONU = ".!?\n"


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
    if os.environ.get("ORKESTRA_ONLEME_YANIT") == "0":
        return "kapali"
    m = ayar.get("mod", "kapali")
    return m if m in MODLAR else "kapali"


def normallestir(metin) -> str:
    """Türkçe büyük/küçük harf farkını giderir (İ→i, I→ı); uzunluk korunur."""
    return (metin or "").replace("İ", "i").replace("I", "ı").lower()


def _ilk_eslesme(kaliplar, norm: str):
    for k in kaliplar or []:
        try:
            m = re.search(k, norm)
        except re.error:
            continue
        if m:
            return k, m
    return None


def degerlendir(metin, sd=None) -> dict:
    """Yanıtta sonradan yakalayan/alışkanlık önerisi var ve merdiven akıl yürütmesi yoksa
    {"kalip", "alinti"} (öneri cümlesi); aksi halde boş sözlük. Kip `kapali` ise boş."""
    ayar = ayar_oku(sd)
    if mod(ayar) == "kapali" or not isinstance(metin, str) or not metin.strip():
        return {}
    norm = normallestir(metin)
    if _ilk_eslesme(ayar.get("basamak_kaliplari"), norm):
        return {}
    bulgu = _ilk_eslesme(ayar.get("oneri_kaliplari"), norm)
    if not bulgu:
        return {}
    kalip, m = bulgu
    bas = max(norm.rfind(c, 0, m.start()) for c in _CUMLE_SONU) + 1
    sonlar = [i for i in (norm.find(c, m.end()) for c in _CUMLE_SONU) if i != -1]
    return {"kalip": kalip, "alinti": metin[bas:(min(sonlar) + 1 if sonlar else len(metin))].strip()}
