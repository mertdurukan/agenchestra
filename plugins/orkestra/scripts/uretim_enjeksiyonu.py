"""Yazım anında tabi olunan denetimin kuralını bağlama ekler (ADR-0111, P-045, K-006; merdiven L4).

PreToolUse'ta Write/Edit hedefinin dosya adı `ayarlar/uretim_enjeksiyonu.json` eşlemesindeki bir belge türüne denkse o
türün kısa kural metni döner; hook bunu engellemeyen bağlam olarak ekler. Model çağırmaz; hata olursa boş metin döner.
Her enjeksiyon `gunluk.jsonl`'a `uretim_enjekte` olarak tür alanıyla yazılır (içerik yazılmaz). Aynı oturumda aynı tür
için en çok `oturum_basina` kez eklenir (sayaç `uretim_sayac.json`). Ayar: `ayarlar/uretim_enjeksiyonu.json` + proje
durum dizininde aynı adlı dosya (anahtar bazında ezer); `ORKESTRA_URETIM_ENJEKSIYON=0` kapatır.
"""
from __future__ import annotations

import fnmatch
import json
import os

import ork_lib as L

_KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VARSAYILAN_YOL = os.path.join(_KOK, "ayarlar", "uretim_enjeksiyonu.json")
PROJE_DOSYA = "uretim_enjeksiyonu.json"
SAYAC_DOSYA = "uretim_sayac.json"
MODLAR = ("etkin", "kapali")
SAYAC_OTURUM_MAX = 50


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
    if os.environ.get("ORKESTRA_URETIM_ENJEKSIYON") == "0":
        return "kapali"
    m = ayar.get("mod", "kapali")
    return m if m in MODLAR else "kapali"


def esleme_bul(ayar: dict, dosya_adi: str):
    """Dosya adına denk gelen ilk eşleme kaydı (dict) ya da None; eşleme ayardan gelir, kodda belge adı yoktur."""
    ad = str(dosya_adi or "").lower()
    for e in ayar.get("eslemeler") or []:
        if not isinstance(e, dict) or not e.get("tur") or not e.get("metin"):
            continue
        for desen in e.get("dosya") or []:
            if isinstance(desen, str) and fnmatch.fnmatchcase(ad, desen.lower()):
                return e
    return None


def _kes(metin: str, sinir: int) -> str:
    if len(metin) <= sinir:
        return metin
    return metin[:sinir - 1].rsplit(" ", 1)[0] + "…"


def _sayac_al_artir(sd, oturum_id, tur: str, en_cok: int) -> bool:
    """Oturum+tür sayacı `en_cok`a ulaşmadıysa artırır ve True döner; sayaç yazılamazsa True (ipucu verilir)."""
    yol = os.path.join(sd, SAYAC_DOSYA)
    veri = _json_oku(yol) or {}
    anahtar = str(oturum_id or "?")
    kayit = veri.pop(anahtar, None)
    kayit = kayit if isinstance(kayit, dict) else {}
    n = int(kayit.get(tur, 0) or 0)
    if n >= en_cok:
        veri[anahtar] = kayit
        return False
    kayit[tur] = n + 1
    veri[anahtar] = kayit  # en son kullanılan sona
    while len(veri) > SAYAC_OTURUM_MAX:
        veri.pop(next(iter(veri)))
    try:
        gecici = yol + ".tmp"
        with open(gecici, "w", encoding="utf-8") as f:
            json.dump(veri, f)
        os.replace(gecici, yol)
    except Exception:
        return True
    return True


def _gunluk(sd, oturum_id, tur: str, ajan=None) -> None:
    try:
        kayit = {"zaman": L.simdi(), "oturum": oturum_id, "tur": "uretim_enjekte", "belge": tur}
        if ajan:
            kayit["ajan"] = ajan
        L.jsonl_ekle(os.path.join(sd, "gunluk.jsonl"), kayit)
    except Exception:
        pass


def metin(dosya_yolu, sd=None, oturum_id=None, ajan=None) -> str:
    """Yazılacak dosya bir belge türüne denkse o türün kural metni (onek + metin), değilse ya da kapalıysa boş."""
    try:
        if not sd or not dosya_yolu:
            return ""
        ayar = ayar_oku(sd)
        if mod(ayar) == "kapali":
            return ""
        e = esleme_bul(ayar, os.path.basename(str(dosya_yolu)))
        if not e:
            return ""
        tur = str(e["tur"])
        en_cok = max(1, int(ayar.get("oturum_basina", 1) or 1))
        if not _sayac_al_artir(sd, oturum_id, tur, en_cok):
            return ""
        sinir = max(60, int(ayar.get("metin_max", 300) or 300))
        _gunluk(sd, oturum_id, tur, ajan)
        return str(ayar.get("onek", "")) + _kes(str(e["metin"]), sinir)
    except Exception:
        return ""
