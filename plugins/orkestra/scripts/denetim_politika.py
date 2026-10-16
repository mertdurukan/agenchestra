#!/usr/bin/env python3
"""Orkestra denetim politikası (L5): geçmiş ilk-denetim ret oranından hangi kartta LLM denetçisi atlanabilir.

  denetim_politika.py tablo [--sd DIR] [--json]
  denetim_politika.py karar <G-xxx> [--sd DIR] [--kaydet]
  denetim_politika.py gecit [--sd DIR]

Modlar: tam (daima denetle) | golge (hesapla, uygulama) | etkin (geçit açıksa uygula). Varsayılan: tam.
Eşik ve listeler ayarlar/denetim_politikasi.json'dan; proje ezmesi <sd>/denetim_politikasi.json (üst düzey alanlar).
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ork_lib as L  # noqa: E402
from kural_aday import sinif_normal  # noqa: E402

AYAR_DOSYASI = os.path.join(L.PLUGIN_ROOT, "ayarlar", "denetim_politikasi.json")
EZME_AD = "denetim_politikasi.json"
# Eklenti ayar dosyası yok/bozuksa son çare (dosyadaki şemanın aynısı; mod=tam => hiçbir şey atlanmaz).
_YEDEK = {"surum": 1, "mod": "tam", "grup_anahtari": ["sinif", "basamak"], "min_ornek": 10,
          "max_ilk_ret_orani": 0.1, "tdd_haric": True, "yuksek_risk_haric": True, "risk_degerleri": ["yuksek"],
          "ornekleme_orani": 0.2, "ornekleme_tuzu": "orkestra-denetim",
          "gecit": {"min_denetim": 50, "min_kanit_kart": 20}}


def _json_sozluk(yol: str):
    try:
        with open(yol, encoding="utf-8") as f:
            v = json.load(f)
        return v if isinstance(v, dict) else None
    except (OSError, ValueError):
        return None


def ayar_yukle(sd: str | None = None) -> dict:
    cfg = _json_sozluk(AYAR_DOSYASI) or copy.deepcopy(_YEDEK)
    if sd:
        ezme = _json_sozluk(os.path.join(sd, EZME_AD))
        if ezme:
            cfg.update(ezme)
    return cfg


def _grup(kart: dict, cfg: dict) -> str:
    parcalar = []
    for a in cfg.get("grup_anahtari") or []:
        v = sinif_normal(kart) if a == "sinif" else kart.get(a)
        parcalar.append("belirsiz" if v in (None, "") else str(v))
    return "|".join(parcalar)


def _ilk_karar(kart: dict):
    den = kart.get("denetimler")
    if isinstance(den, list) and den and isinstance(den[0], dict):
        return den[0].get("karar")
    return None


def grup_tablosu(kartlar, cfg: dict) -> dict:
    t: dict = {}
    for k in kartlar:
        if _ilk_karar(k) is None:
            continue
        g = t.setdefault(_grup(k, cfg), {"n": 0, "ilk_ret": 0, "oran": 0.0})
        g["n"] += 1
        if _ilk_karar(k) == "ret":
            g["ilk_ret"] += 1
    for g in t.values():
        g["oran"] = g["ilk_ret"] / g["n"] if g["n"] else 0.0
    return t


def _ornekleme_degeri(tuz: str, kid: str) -> float:
    return int(hashlib.sha256((tuz + kid).encode("utf-8")).hexdigest()[:8], 16) / 0xFFFFFFFF


def karar(kart: dict, tablo: dict, cfg: dict, gecit_acik: bool = False) -> dict:
    """gecit_acik: uygulanir hesabı için gecit_kontrol sonucu (varsayılan kapalı => uygulanir False)."""
    mod = cfg.get("mod", "tam")
    grup = _grup(kart, cfg)

    def sonuc(k, neden, ornek=False):
        return {"karar": k, "neden": neden, "orneklenmis": ornek, "grup": grup,
                "uygulanir": bool(mod == "etkin" and gecit_acik and k == "atla")}

    if mod == "tam":
        return sonuc("denetle", "politika-tam")
    if cfg.get("tdd_haric") and kart.get("tdd"):
        return sonuc("denetle", "tdd")
    if cfg.get("yuksek_risk_haric") and kart.get("risk") in (cfg.get("risk_degerleri") or []):
        return sonuc("denetle", "yuksek-risk")
    g = tablo.get(grup) or {"n": 0, "oran": 0.0}
    if g["n"] < cfg.get("min_ornek", 10):
        return sonuc("denetle", "yetersiz-veri")
    if g["oran"] > cfg.get("max_ilk_ret_orani", 0.1):
        return sonuc("denetle", "ret-orani-yuksek")
    if _ornekleme_degeri(cfg.get("ornekleme_tuzu", ""), str(kart.get("id", ""))) < cfg.get("ornekleme_orani", 0):
        return sonuc("denetle", "ornekleme", True)
    return sonuc("atla", "dusuk-risk-grup")


def gecit_kontrol(kartlar, cfg: dict) -> dict:
    gc = cfg.get("gecit") or {}
    kartlar = list(kartlar)
    denetim = sum(len(k["denetimler"]) for k in kartlar if isinstance(k.get("denetimler"), list))
    kanit = 0
    for k in kartlar:
        tur = k.get("is_turlari")
        if isinstance(tur, list) and tur and isinstance(tur[-1], dict):
            kapi = tur[-1].get("kapi")
            if isinstance(kapi, dict) and "kanit" in kapi:
                kanit += 1
    eksik = []
    if denetim < gc.get("min_denetim", 50):
        eksik.append(f"denetim {denetim} < {gc.get('min_denetim', 50)}")
    if kanit < gc.get("min_kanit_kart", 20):
        eksik.append(f"kanit_kart {kanit} < {gc.get('min_kanit_kart', 20)}")
    return {"acik": not eksik, "denetim": denetim, "kanit_kart": kanit, "eksik": eksik}


def kaydet(sd, gid, sonuc: dict, mod: str | None = None) -> bool:
    try:
        yol = L.kart_yolu(sd, gid)
        with L.kilit(yol):
            kart = L.kart_oku(sd, gid)
            if not kart:
                return False
            kart.setdefault("politika_kararlari", []).append({
                "zaman": L.simdi(), "karar": sonuc.get("karar"), "neden": sonuc.get("neden"),
                "orneklenmis": bool(sonuc.get("orneklenmis")), "mod": mod or sonuc.get("mod"),
                "uygulanir": bool(sonuc.get("uygulanir")), "grup": sonuc.get("grup")})
            L.kart_yaz(sd, kart)
        return True
    except Exception:
        return False


def _sd(a) -> str:
    sd = a.sd or L.durum_dizini()
    if not sd:
        print(json.dumps({"hata": "durum dizini bulunamadı"}, ensure_ascii=False))
        raise SystemExit(2)
    return sd


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    s = p.add_subparsers(dest="komut", required=True)
    t = s.add_parser("tablo")
    t.add_argument("--sd")
    t.add_argument("--json", action="store_true")
    k = s.add_parser("karar")
    k.add_argument("id")
    k.add_argument("--sd")
    k.add_argument("--kaydet", action="store_true")
    g = s.add_parser("gecit")
    g.add_argument("--sd")
    a = p.parse_args(argv)
    sd = _sd(a)
    cfg = ayar_yukle(sd)
    kartlar = L.kartlar(sd)
    if a.komut == "tablo":
        tablo = grup_tablosu(kartlar, cfg)
        if a.json:
            print(json.dumps(tablo, ensure_ascii=False, indent=2))
        else:
            for ad, v in sorted(tablo.items()):
                print(f"{ad}\tn={v['n']}\tilk_ret={v['ilk_ret']}\toran={v['oran']:.3f}")
        return 0
    if a.komut == "gecit":
        print(json.dumps(gecit_kontrol(kartlar, cfg), ensure_ascii=False))
        return 0
    kart = next((c for c in kartlar if c.get("id") == a.id), None)
    if not kart:
        print(json.dumps({"hata": f"kart yok: {a.id}"}, ensure_ascii=False))
        return 2
    r = karar(kart, grup_tablosu(kartlar, cfg), cfg, gecit_kontrol(kartlar, cfg)["acik"])
    r["mod"] = cfg.get("mod")
    if a.kaydet:
        r["kaydedildi"] = kaydet(sd, a.id, r, cfg.get("mod"))
    print(json.dumps(r, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
