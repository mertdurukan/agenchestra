"""Kimlik klasörüne önce bak hatırlatması (P-023): ajan kimlik yok deyip kullanıcıya bırakmadan önce
`orkestra kimlik liste` ile klasöre bakar. Model çağrılmaz; değer okunmaz.

Kalıplar ve mod kodda durmaz: `ayarlar/kimlik_hatirlatma.json` (eklenti varsayılanı) ve proje durum
dizinindeki `kimlik_hatirlatma.json` (anahtar bazında ezer). Bozuk/eksik dosya varsayılana düşer.
`ORKESTRA_KIMLIK_HATIRLATMA=0` hatırlatmayı kapatır.
"""
from __future__ import annotations

import json
import os
import re

_KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VARSAYILAN_YOL = os.path.join(_KOK, "ayarlar", "kimlik_hatirlatma.json")
PROJE_DOSYA = "kimlik_hatirlatma.json"
MODLAR = ("block", "golge", "kapali")


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
    """'block' (tur başına bir kez hatırlat), 'golge' (yalnız günlük) ya da 'kapali'; ortam değişkeni 0 ise kapalı."""
    if os.environ.get("ORKESTRA_KIMLIK_HATIRLATMA") == "0":
        return "kapali"
    m = ayar.get("mod", "kapali")
    return m if m in MODLAR else "kapali"


def _normallestir(metin: str) -> str:
    return (metin or "").replace("İ", "i").replace("I", "ı").lower()


_KOD = re.compile(r"```.*?```|`[^`\n]*`", re.S)


def tarama_metni(metin: str) -> str:
    """İhlal kalıplarının taradığı metin: normalleştirilir, kod bloğu ve satır içi kod aynı uzunlukta boşlukla örtülür.
    Kod içindeki ad ve değerler ("`max_tokens`") kimlik cümlesi sayılmaz; uzunluk korunduğu için kanıt cümlesi
    özgün metinden kesilebilir (hook.py `_kalip_kaniti`)."""
    return _KOD.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), _normallestir(metin))


def _eslesir(kaliplar, metin: str) -> bool:
    for k in kaliplar or []:
        try:
            if re.search(k, metin):
                return True
        except re.error:
            continue
    return False


def yanit_ihlali(yanit, sd=None) -> bool:
    """Yanıtta kimlik ya da erişim eksikliği kalıbı var ve yanıt klasöre baktığını göstermiyor mu?
    Muaf kalıplar tüm metinde aranır (`orkestra kimlik liste` çoğu kez backtick içindedir); ihlal kalıpları kod dışında."""
    ayar = ayar_oku(sd)
    if mod(ayar) == "kapali":
        return False
    m = _normallestir(yanit)
    if not m or _eslesir(ayar.get("yanit_muaf_kaliplari"), m):
        return False
    return _eslesir(ayar.get("yanit_kaliplari"), tarama_metni(yanit))


def mesaj_ipucu(metin, sd=None) -> str:
    """Kullanıcı mesajı kimlik gerektiren bir servisi anıyorsa tek satırlık ipucu, yoksa boş metin."""
    ayar = ayar_oku(sd)
    if mod(ayar) == "kapali":
        return ""
    return ayar.get("ipucu", "") if _eslesir(ayar.get("servis_kaliplari"), _normallestir(metin)) else ""


def hatirlatma_metni(sd=None) -> str:
    return ayar_oku(sd).get("hatirlatma", "")
