"""Kapı modları (ADR-0035): sözleşme, teslim ve izole ortam kapıları önce `golge`, ölçülünce `ihlal` modunda çalışır.

Mod, eklentinin `ayarlar/<kapi>.json` dosyasından okunur; proje ezmesi durum klasöründeki `<kapi>.json`dır
(`.claude/orkestra/<kapi>.json`). Dosya yoksa ya da bozuksa `golge` kullanılır.
- golge: eksik uyarı olarak stderr'e yazılır ve gunluk.jsonl'a `kapi_golge` olayı düşer; iş engellenmez.
- ihlal: eksik çağırana döner, çağıran işi reddeder.
Ölçüm (`orkestra is rapor`) `kapi_golge` olaylarını sayar.
"""
from __future__ import annotations

import json
import os
import sys

import ork_lib as L

VARSAYILAN = "golge"
MODLAR = ("golge", "ihlal")


def mod(kapi: str, klasor: str | None = None) -> str:
    """`ayarlar/<kapi>.json` `mod` değeri; proje ezmesi (durum klasörü) önceliklidir."""
    kok = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    yollar = [os.path.join(kok, "ayarlar", kapi + ".json")]
    sd = L.durum_dizini(klasor) if klasor else None
    if sd:
        yollar.append(os.path.join(sd, kapi + ".json"))
    sonuc = VARSAYILAN
    for yol in yollar:
        try:
            with open(yol, encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict) and d.get("mod") in MODLAR:
                sonuc = d["mod"]
        except (OSError, ValueError):
            pass
    return sonuc


def _zaten_kayitli(yol: str, is_ad: str, kapi: str, neden: str) -> bool:
    """Günlüğün son 64 KB'ında aynı (iş, kapı, neden) var mı; tekrar tekrar çağrılan kapılar sayıyı şişirmesin."""
    try:
        with open(yol, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - 65536))
            kuyruk = f.read().decode("utf-8", errors="ignore")
    except OSError:
        return False
    for satir in kuyruk.splitlines():
        try:
            o = json.loads(satir)
        except ValueError:
            continue
        if isinstance(o, dict) and o.get("tur") == "kapi_golge" and o.get("kapi") == kapi                 and o.get("is") == is_ad and o.get("neden") == neden[:300]:
            return True
    return False


def kaydet(klasor: str, kapi: str, neden: str) -> bool:
    """Gölge kaydı: gunluk.jsonl'a `kapi_golge` olayı; aynı (iş, kapı, neden) yeniden yazılmaz. Yeni kayıt yazıldıysa True.
    Kapıyı hiçbir koşulda bozmaz."""
    try:
        sd = L.durum_dizini(klasor)
        if not sd:
            return False
        yol = os.path.join(sd, "gunluk.jsonl")
        is_ad = os.path.basename(os.path.normpath(klasor))
        if _zaten_kayitli(yol, is_ad, kapi, neden):
            return False
        L.jsonl_ekle(yol, {"zaman": L.simdi(), "tur": "kapi_golge", "kapi": kapi, "is": is_ad, "neden": neden[:300]})
        return True
    except Exception:
        return False


def ihlal_ver(klasor: str, kapi: str, eksik: list[str]) -> list[str]:
    """İhlal modunda eksikleri döndürür (çağıran reddeder); gölge modunda uyarır, kaydeder ve boş liste döndürür."""
    if not eksik:
        return []
    if mod(kapi, klasor) == "ihlal":
        return eksik
    neden = "; ".join(eksik)
    if kaydet(klasor, kapi, neden):
        print(f"orkestra (gölge, {kapi}): {neden}", file=sys.stderr)
    return []
