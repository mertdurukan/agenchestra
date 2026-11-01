"""Pahalı tur devir ipucu (I-271).

Ana ajanın tek turunda (bir Stop'tan sonrakine) önbellek okuması `esik_onbellek_okuma` token'ı aşarsa, sonraki kullanıcı
mesajında (UserPromptSubmit) tek satırlık engellemeyen bir ipucu bağlama girer: oturumu `/orkestra:devir` ile yeni sohbete
taşımayı düşün. Ölçüm (DemoRoot): 5 M üstü tur ana ajan turlarının %4,7'si (239/5136), harcamanın %19,8'i.

soguk_onbellek.devir_uyarisi'nden farkı: o, tek çağrının BAĞLAM boyutuna bakar ve oturumda bir kez uyarır; bu, turun
TOPLAM önbellek okumasına bakar (çok çağrılı uzun turlar) ve `tekrar_aralik_tur` turda bir yeniden uyarabilir.

Ayar: `ayarlar/devir_esigi.json`; proje durum dizinindeki aynı adlı dosya anahtar bazında ezer. Bozuk/eksik değer
varsayılana düşer. `mod`: ipucu | kapali. `ORKESTRA_DEVIR_ESIGI=0` kapatır. Hata hiçbir zaman kancayı düşürmez.
"""
from __future__ import annotations

import json
import os

import ork_lib as L

_KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VARSAYILAN_YOL = os.path.join(_KOK, "ayarlar", "devir_esigi.json")
PROJE_DOSYA = "devir_esigi.json"
VARSAYILAN = {"mod": "ipucu", "esik_onbellek_okuma": 5_000_000, "tekrar_aralik_tur": 20}


def _json_oku(yol: str):
    try:
        with open(yol, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except Exception:
        return None


def _pozitif_int(v, varsayilan: int) -> int:
    if isinstance(v, bool):
        return varsayilan
    try:
        n = int(v)
    except (TypeError, ValueError):
        return varsayilan
    return n if n > 0 else varsayilan


def ayar_oku(sd=None) -> dict:
    """Eklenti ayarı + proje ezmesi; her anahtar ayrı doğrulanır, geçersiz olan varsayılana düşer."""
    ham = dict(_json_oku(VARSAYILAN_YOL) or {})
    if sd:
        ham.update(_json_oku(os.path.join(sd, PROJE_DOSYA)) or {})
    mod = ham.get("mod")
    return {"mod": mod if mod in ("ipucu", "kapali") else VARSAYILAN["mod"],
            "esik_onbellek_okuma": _pozitif_int(ham.get("esik_onbellek_okuma"), VARSAYILAN["esik_onbellek_okuma"]),
            "tekrar_aralik_tur": _pozitif_int(ham.get("tekrar_aralik_tur"), VARSAYILAN["tekrar_aralik_tur"])}


def _durum_yolu(sd: str, oid: str) -> str:
    return os.path.join(sd, "oturumlar", f"{oid}.devir_esigi.json")


def _kapali(sd, oid) -> bool:
    return not sd or not oid or oid == "-" or os.environ.get("ORKESTRA_DEVIR_ESIGI") == "0"


def tur_kaydet(sd: str, oid: str, onbellek_okuma) -> bool:
    """Stop: ana ajan turunu sayar; eşik üstü ve aralık dolmuşsa bekleyen ipucu yazar. İpucu kuruldu mu döner."""
    try:
        if _kapali(sd, oid):
            return False
        ayar = ayar_oku(sd)
        if ayar["mod"] != "ipucu":
            return False
        okuma = int(onbellek_okuma or 0)
        yol = _durum_yolu(sd, oid)
        os.makedirs(os.path.dirname(yol), exist_ok=True)
        with L.kilit(yol):
            d = _json_oku(yol) or {}
            tur = _pozitif_int(d.get("tur"), 0) + 1
            d["tur"] = tur
            son = d.get("son_uyari_tur")
            aralik_doldu = not isinstance(son, int) or tur - son >= ayar["tekrar_aralik_tur"]
            kur = okuma > ayar["esik_onbellek_okuma"] and aralik_doldu
            if kur:
                d["son_uyari_tur"] = tur
                d["bekleyen"] = {"okuma": okuma, "esik": ayar["esik_onbellek_okuma"], "tur": tur}
            L.atomik_yaz(yol, json.dumps(d))
        if kur:
            L.jsonl_ekle(os.path.join(sd, "gunluk.jsonl"), {"zaman": L.simdi(), "tur": "devir_esigi_olay",
                                                             "oturum": str(oid)[:8], "onbellek_okuma": okuma,
                                                             "esik": ayar["esik_onbellek_okuma"], "oturum_tur": tur})
        return kur
    except Exception:
        return False


def ipucu_al(sd: str, oid: str) -> str:
    """UserPromptSubmit: bekleyen ipucunu bir kez döner ve siler; yoksa ''."""
    try:
        if _kapali(sd, oid):
            return ""
        yol = _durum_yolu(sd, oid)
        if not os.path.exists(yol):
            return ""
        with L.kilit(yol):
            d = _json_oku(yol) or {}
            b = d.pop("bekleyen", None)
            if not isinstance(b, dict):
                return ""
            L.atomik_yaz(yol, json.dumps(d))
        if ayar_oku(sd)["mod"] != "ipucu":
            return ""
        okuma_m = int(b.get("okuma") or 0) / 1e6
        esik_m = int(b.get("esik") or 0) / 1e6
        return (f"Orkestra (pahalı tur): önceki tur {okuma_m:.1f} M token önbellek okudu (eşik {esik_m:g} M). "
                "Oturumu `/orkestra:devir` ile yeni sohbete taşımayı düşün; sürdürmek de mümkün, bu ipucu engellemez.")
    except Exception:
        return ""
