"""Maliyet değişikliğinin önce/sonra ölçümü ve kalite bekçisi (BIC-2).

`karsilastir(sd, kesim, gun)`: [kesim-gun, kesim) ile [kesim, kesim+gun) pencerelerini aynı tanımlarla ölçer.
Maliyet metrikleri azalmalı; kalite metrikleri (doğrulanmış başarı, ret oranı) kötüleşmemeli. Karar:
  kalite-riski   bir kalite metriği eşikten fazla kötüleşti (maliyet düşse bile)
  iyilesme       en az bir maliyet metriği iyi, hiçbiri kötü, kalite sağlam
  kotulesme      bir maliyet metriği kötüleşti
  etkisiz        fark eşik altında
  yetersiz-veri  karar için örnek az
Gidişat kuralı etki.gidisat ile aynıdır (göreli eşik %10). Salt okuma; yalnız sayı döner.
"""
from __future__ import annotations

import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analitik as A  # noqa: E402
import kpi  # noqa: E402
import ork_lib as L  # noqa: E402

MIN_ORNEK = 5
KAPI_SURECLERI = ("test-kapisi", "on-kontrol")
# (metrik, yön, tür) — tür: maliyet | kalite
METRIKLER = (
    ("basari_basina_maliyet", "azalmali", "maliyet"),
    ("basari_basina_token", "azalmali", "token"),
    ("kart_basina_ajan", "azalmali", "maliyet"),
    ("ana_ajan_payi", "azalmali", "maliyet"),
    ("yeniden_deneme_carpani", "azalmali", "maliyet"),
    ("kapi_ajani_kart_basina", "azalmali", "maliyet"),
    ("dogrulanmis_basari", "artmali", "kalite"),
    ("ret_orani", "azalmali", "kalite"),
) + tuple((f"basari_basina_{o}_{a}", "azalmali", o) for o in ("token", "usd") for a in L._TOKEN_ALANLARI)
# tür 'token' ve 'usd': ikili ölçü (I-064). karar() yalnız 'kalite' ve 'maliyet' türüne baktığı için hükmü etkilemez.


def _pencere(sd: str, bas: datetime.datetime, bit: datetime.datetime) -> dict:
    s = kpi.olcum(sd, aralik=(bas, bit))
    g, orn = s["genel"], s.get("ornek") or {}
    kartlar = {k["id"] for k in L.kartlar(sd) if k.get("durum") != "iptal"
               and (z := A._zaman(k.get("olusturma"))) and bas <= z < bit}
    ajan: dict = {}
    kapi = 0
    toplam = ana = 0.0
    satirlar = []
    for r in L.maliyet_kayitlari(sd):
        z = A._zaman(r.get("zaman"))
        if not z or not (bas <= z < bit):
            continue
        usd = float(r.get("maliyet_usd") or 0)
        toplam += usd
        satirlar.append(r)
        gid = r.get("gorev")
        if L.ana_ajan_satiri_mi(r):  # ana ajan payı: tek tanım (ork_lib.ana_ajan_satiri_mi)
            ana += usd
            continue
        if gid in kartlar and r.get("agent_id"):
            ajan.setdefault(gid, set()).add(r["agent_id"])
            if r.get("surec") in KAPI_SURECLERI:
                kapi += 1
    n = len(kartlar)
    kal = g.get("basari_basina_kalem") or {}
    return {
        "deger": {
            "basari_basina_maliyet": g.get("basari_basina_maliyet"),
            "basari_basina_token": g.get("basari_basina_token"),
            **{f"basari_basina_{o}_{a}": (kal.get(o) or {}).get(a) for o in ("token", "usd") for a in L._TOKEN_ALANLARI},
            "kart_basina_ajan": (sum(len(v) for v in ajan.values()) / n) if n else None,
            "ana_ajan_payi": (ana / toplam) if toplam else None,
            "yeniden_deneme_carpani": g.get("yeniden_deneme_carpani"),
            "kapi_ajani_kart_basina": (kapi / n) if n else None,
            "dogrulanmis_basari": g.get("dogrulanmis_basari"),
            "ret_orani": g.get("ret_orani"),
        },
        "ornek": {
            "basari_basina_maliyet": orn.get("basari_basina_maliyet", 0),
            "basari_basina_token": orn.get("basari_basina_token", 0),
            **{f"basari_basina_{o}_{a}": orn.get("basari_basina_token", 0) for o in ("token", "usd") for a in L._TOKEN_ALANLARI},
            "kart_basina_ajan": n, "ana_ajan_payi": n, "yeniden_deneme_carpani": n, "kapi_ajani_kart_basina": n,
            "dogrulanmis_basari": orn.get("dogrulanmis_basari", 0), "ret_orani": orn.get("ret_orani", 0),
        },
        "toplam_usd": round(toplam, 2),
        "kalem": L.kalemler(satirlar),
        "kart": n,
    }


def _gidisat(once, sonra, ornek, yon) -> str:
    import etki
    if once == 0 and sonra is not None and ornek >= MIN_ORNEK:  # taban 0: yalnız artış anlamlıdır
        if sonra > 0:   # taban 0: artış "azalmalı" metrikte kötü, "artmalı" metrikte iyidir
            return "kotu" if yon == "azalmali" else "iyi"
        return "etkisiz"
    return etki.gidisat(once, sonra, ornek, yon, {"min_ornek": MIN_ORNEK})


def karar(satirlar: list[dict]) -> str:
    kalite = [s["gidisat"] for s in satirlar if s["tur"] == "kalite"]
    maliyet = [s["gidisat"] for s in satirlar if s["tur"] == "maliyet"]
    if "kotu" in kalite:
        return "kalite-riski"
    if all(g == "yetersiz-veri" for g in maliyet):
        return "yetersiz-veri"
    if "kotu" in maliyet:
        return "kotulesme"
    if "iyi" in maliyet:
        return "iyilesme"
    return "etkisiz"


def karsilastir(sd: str, kesim: datetime.datetime, gun: float = 7) -> dict:
    d = datetime.timedelta(days=gun)
    o = _pencere(sd, kesim - d, kesim)
    s = _pencere(sd, kesim, kesim + d)
    satirlar = []
    for ad, yon, tur in METRIKLER:
        a, b = o["deger"][ad], s["deger"][ad]
        orn = min(o["ornek"][ad] or 0, s["ornek"][ad] or 0)
        satirlar.append({"metrik": ad, "tur": tur, "yon": yon, "once": a, "sonra": b, "ornek": orn,
                         "gidisat": _gidisat(a, b, orn, yon)})
    return {"kesim": kesim.isoformat(), "gun": gun,
            "once": {"kart": o["kart"], "toplam_usd": o["toplam_usd"], "toplam_token": o["kalem"]["token"]["toplam"], "kalem": o["kalem"]},
            "sonra": {"kart": s["kart"], "toplam_usd": s["toplam_usd"], "toplam_token": s["kalem"]["token"]["toplam"], "kalem": s["kalem"]}, "metrikler": satirlar,
            "karar": karar(satirlar)}


def _f(v) -> str:
    return "-" if v is None else f"{v:.3f}" if isinstance(v, float) else str(v)


def metin(r: dict) -> str:
    out = [f"Kesim {r['kesim']} · pencere ±{r['gun']:g} gün · önce {r['once']['kart']} kart "
           f"{r['once']['toplam_usd']} $ / {r['once']['toplam_token']} token · sonra {r['sonra']['kart']} kart "
           f"{r['sonra']['toplam_usd']} $ / {r['sonra']['toplam_token']} token",
           "| metrik | tür | yön | önce | sonra | örnek | gidişat |", "|---|---|---|---|---|---|---|"]
    for s in r["metrikler"]:
        out.append(f"| {s['metrik']} | {s['tur']} | {s['yon']} | {_f(s['once'])} | {_f(s['sonra'])} | "
                   f"{s['ornek']} | {s['gidisat']} |")
    out.append(f"KARAR: {r['karar']}")
    return "\n".join(out)
