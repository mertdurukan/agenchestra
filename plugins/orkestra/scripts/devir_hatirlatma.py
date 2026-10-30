"""Devir hatırlatması (ADR-0099): ana ajan bir istekte iş belgesi olmayan `esik`inci ayrı dosyaya yazınca, o istekte
alt ajan çalışmadıysa tek bir engellemeyen hatırlatma verir. Oturumların `kontrol_orani` kadarı kontrol grubudur: tetiklenme
kaydedilir, hatırlatma verilmez. Her tetiklenme `devir_olay` olarak gunluk.jsonl'a yazılır (ölçüm: devir_olcum.py).

Eşik, kalıplar, oran ve metin kodda durmaz: `ayarlar/devir_hatirlatma.json`, proje durum dizinindeki aynı adlı dosya
anahtar bazında ezer. `mod`: hatirlat | kapali. `ORKESTRA_DEVIR_HATIRLATMA=0` kapatır. Hata hiçbir zaman aracı bozmaz.
"""
from __future__ import annotations

import hashlib
import json
import os
import re

import ork_lib as L

_KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VARSAYILAN_YOL = os.path.join(_KOK, "ayarlar", "devir_hatirlatma.json")
PROJE_DOSYA = "devir_hatirlatma.json"
DURUM_DOSYA = "devir_durum.json"


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


def kontrol_grubu_mu(oturum: str, oran: float) -> bool:
    """Oturum kimliğinin özetinden sabit atama: aynı oturum her çağrıda aynı gruptadır."""
    if not oturum or oran <= 0:
        return False
    h = int(hashlib.sha256(str(oturum).encode("utf-8")).hexdigest()[:8], 16)
    return (h % 10000) / 10000 < oran


def muaf_mi(yol: str, kaliplar) -> bool:
    y = (yol or "").replace("\\", "/")
    for k in kaliplar or []:
        try:
            if re.search(k, y, re.I):
                return True
        except re.error:
            continue
    return False


def izle(arac: str, girdi: dict, sd: str, oturum: str, agent_id=None, cwd=None) -> str:
    """PreToolUse çağrısını sayar; hatırlatma gerekiyorsa metni, yoksa '' döner. Alt ajan çağrıları (agent_id) sayılmaz."""
    try:
        if agent_id or not sd or not oturum or os.environ.get("ORKESTRA_DEVIR_HATIRLATMA") == "0":
            return ""
        ayar = ayar_oku(sd)
        if ayar.get("mod", "kapali") not in ("hatirlat",):
            return ""
        istek = L.istek_id_oku(sd, oturum)
        if not istek:
            return ""
        yol = os.path.join(sd, DURUM_DOSYA)
        with L.kilit(yol):
            tum = _json_oku(yol) or {}
            d = tum.get(oturum) or {}
            if d.get("istek_id") != istek:
                d = {"istek_id": istek, "dosyalar": [], "devir": False, "tetik": False}
            if any(arac.endswith(a) for a in ayar.get("devir_araclari") or []):
                d["devir"] = True
            elif arac in (ayar.get("yazan_araclar") or []):
                yaz = girdi.get("file_path") or girdi.get("notebook_path") or ""
                if yaz:
                    tam = os.path.abspath(os.path.join(cwd or os.getcwd(), yaz)).replace("\\", "/")
                    if not muaf_mi(tam, ayar.get("muaf_yollar")) and tam not in d["dosyalar"]:
                        d["dosyalar"].append(tam)
            esik = int(ayar.get("esik") or 3)
            tetik = (not d["tetik"]) and (not d["devir"]) and len(d["dosyalar"]) >= esik
            if tetik:
                d["tetik"] = True
            tum[oturum] = d
            # eski oturum kayıtları dosyayı şişirmesin
            if len(tum) > 50:
                tum = dict(list(tum.items())[-50:])
            L.atomik_yaz(yol, json.dumps(tum, ensure_ascii=False))
        if not tetik:
            return ""
        kontrol = kontrol_grubu_mu(oturum, float(ayar.get("kontrol_orani") or 0))
        L.jsonl_ekle(os.path.join(sd, "gunluk.jsonl"), {
            "zaman": L.simdi(), "tur": "devir_olay", "istek_id": istek, "oturum": str(oturum)[:8],
            "grup": "kontrol" if kontrol else "hatirlatma", "dosya_sayisi": len(d["dosyalar"]), "esik": esik})
        return "" if kontrol else str(ayar.get("hatirlatma") or "")
    except Exception:
        return ""
