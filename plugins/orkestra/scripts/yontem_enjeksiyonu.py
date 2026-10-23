"""Best in class yöntemini üretim anında bağlama ekler (ADR-0068, P-030, K-006).

Metin tek kaynaktan okunur: `standartlar/best_in_class.md` içindeki `## Üretim anı` bölümü. UserPromptSubmit'te
`soru_sinif.tur == "is"` olan mesajlara (ana ajan) ve SubagentStart'ta kartlı işçilere (denetçi hariç) eklenir.
Model çağırmaz, engellemez; hata olursa boş metin döner. Her enjeksiyon ve kontrol kolu atlaması `gunluk.jsonl`'a
`yontem_enjekte` olarak kol alanıyla yazılır (etki ölçümü: `orkestra is rapor`).

Kol: oturum kimliğinin özetiyle `yontem` ya da `kontrol` (`kontrol_payi`). Kontrol kolu metin almaz.
Ayar: `ayarlar/yontem_enjeksiyonu.json` + proje durum dizininde aynı adlı dosya (anahtar bazında ezer);
`ORKESTRA_YONTEM_ENJEKSIYONU=0` her şeyi kapatır.
"""
from __future__ import annotations

import hashlib
import json
import os
import re

import ork_lib as L
import standart

_KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VARSAYILAN_YOL = os.path.join(_KOK, "ayarlar", "yontem_enjeksiyonu.json")
PROJE_DOSYA = "yontem_enjeksiyonu.json"
MODLAR = ("etkin", "kapali")
ANA_MAX = 700
ISCI_MAX = 600


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
    if os.environ.get("ORKESTRA_YONTEM_ENJEKSIYONU") == "0":
        return "kapali"
    m = ayar.get("mod", "kapali")
    return m if m in MODLAR else "kapali"


def kol(oturum_id, sd=None) -> str:
    """'yontem' ya da 'kontrol': oturum kimliğinin özetiyle sabit atama; oturum başına tek kol."""
    pay = ayar_oku(sd).get("kontrol_payi", 0)
    try:
        pay = float(pay)
    except (TypeError, ValueError):
        pay = 0.0
    if not oturum_id or pay <= 0:
        return "yontem"
    sayi = int(hashlib.sha256(str(oturum_id).encode("utf-8")).hexdigest()[:8], 16) / 2 ** 32
    return "kontrol" if sayi < pay else "yontem"


def _bolum(sd, baslik: str) -> str:
    """Standartta `## <baslik>` bölümünün gövdesi (sonraki `## ` başlığına kadar), tek satıra sıkıştırılmış."""
    metin = standart.oku("best_in_class", sd) or ""
    m = re.search(r"^##\s+" + re.escape(baslik) + r"\s*$(.*?)(?=^##\s|\Z)", metin, re.S | re.M)
    return " ".join(m.group(1).split()) if m else ""


def _kes(metin: str, sinir: int) -> str:
    if len(metin) <= sinir:
        return metin
    return metin[:sinir - 1].rsplit(" ", 1)[0] + "…"


def _gunluk(sd, oturum_id, k: str, nokta: str, ajan=None) -> None:
    try:
        kayit = {"zaman": L.simdi(), "oturum": oturum_id, "tur": "yontem_enjekte", "kol": k, "nokta": nokta}
        if ajan:
            kayit["ajan"] = ajan
        L.jsonl_ekle(os.path.join(sd, "gunluk.jsonl"), kayit)
    except Exception:
        pass


def _metin(sd, oturum_id, sinir: int, nokta: str, ajan=None) -> str:
    try:
        ayar = ayar_oku(sd)
        if mod(ayar) == "kapali":
            return ""
        k = kol(oturum_id, sd)
        if k == "kontrol":
            _gunluk(sd, oturum_id, k, nokta, ajan)
            return ""
        govde = _bolum(sd, ayar.get("baslik", "Üretim anı"))
        if not govde:
            return ""
        _gunluk(sd, oturum_id, k, nokta, ajan)
        return _kes(ayar.get("onek", "") + govde, sinir)
    except Exception:
        return ""


def ana_ajan_metni(metin, sd=None, oturum_id=None) -> str:
    """İş mesajında (soru_sinif.tur == 'is') yöntem metni, değilse boş."""
    try:
        import soru_sinif
        if soru_sinif.tur(metin, sd) != "is":
            return ""
    except Exception:
        return ""
    return _metin(sd, oturum_id, ANA_MAX, "ana")


def isci_metni(agent_type, sd=None, oturum_id=None) -> str:
    """Kartlı işçi için yöntem metni; denetçi için boş (yöntemi zaten kendi tanımından alır). İşçi, üst oturumun kolunu alır."""
    if str(agent_type or "").endswith("denetci"):
        return ""
    return _metin(sd, oturum_id, ISCI_MAX, "isci", agent_type)
