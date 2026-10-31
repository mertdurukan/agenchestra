"""Oturum farkındalığı ölçümü (ADR-0125): gölge günlük tespitleri, elle sınıflama, yanlış pozitif oranı, hook gecikmesi.

Günlük: gunluk.jsonl `tur=kapi_golge|kapi_ihlal, kapi=oturum_farkindalik` (tespit) ve `tur=oturum_farkindalik_sinif` (elle sınıf).
İhlal moduna geçiş ölçütü (ADR-0125): ≥60 sınıflı tespitte yanlış pozitif ≤ %10 ve kullanıcı kararı; bu modül karar vermez.
"""
from __future__ import annotations

import datetime
import json
import os
import statistics
import time

import ork_lib as L
import oturum_farkindalik as F


def _satirlar(sd: str):
    yol = os.path.join(sd, "gunluk.jsonl")
    try:
        with open(yol, encoding="utf-8", errors="replace") as f:
            for s in f:
                try:
                    d = json.loads(s)
                except ValueError:
                    continue
                if isinstance(d, dict):
                    yield d
    except OSError:
        return


def sinifla(sd: str, zaman: str, sonuc: str) -> None:
    """Bir tespiti elle 'dogru' ya da 'yanlis' (yanlış pozitif) işaretler."""
    L.jsonl_ekle(os.path.join(sd, "gunluk.jsonl"),
                 {"zaman": L.simdi(), "tur": "oturum_farkindalik_sinif", "ref": zaman, "sonuc": sonuc})


def rapor(sd: str, gun: int = 7, gecikme_n: int = 0, cwd: str | None = None) -> dict:
    sinir = (datetime.datetime.now().astimezone() - datetime.timedelta(days=gun)).isoformat()
    tespit, sinif = [], {}
    for d in _satirlar(sd):
        if d.get("tur") in ("kapi_golge", "kapi_ihlal") and d.get("kapi") == F.KAPI and str(d.get("zaman", "")) >= sinir:
            tespit.append(d)
        elif d.get("tur") == "oturum_farkindalik_sinif":
            sinif[d.get("ref")] = d.get("sonuc")
    neden = {}
    for d in tespit:
        neden[d.get("neden")] = neden.get(d.get("neden"), 0) + 1
    sinifli = [(d, sinif[d["zaman"]]) for d in tespit if d.get("zaman") in sinif]
    yanlis = sum(1 for _, s in sinifli if s == "yanlis")
    r = {"gun": gun, "tespit": len(tespit), "neden": neden, "sinifli": len(sinifli), "yanlis_pozitif": yanlis,
         "yanlis_pozitif_orani": round(yanlis / len(sinifli), 3) if sinifli else None,
         "ihlal_gecis_olcutu": "≥60 sınıflı tespitte yanlış pozitif ≤ %10 + kullanıcı kararı",
         "ihlal_olcutu_saglandi": bool(len(sinifli) >= 60 and yanlis / len(sinifli) <= 0.10),
         "son_tespitler": [{"zaman": d.get("zaman"), "olay": d.get("olay"), "neden": d.get("neden"),
                            "sinif": sinif.get(d.get("zaman"))} for d in tespit[-30:]]}
    if gecikme_n:
        r["gecikme"] = gecikme(sd, cwd or os.getcwd(), gecikme_n)
    return r


def gecikme(sd: str, cwd: str, n: int = 1000) -> dict:
    """`arac_oncesi` işlevinin (hook'a eklenen iş) n çağrılık süresi, ms: yazma aracı ve okuma aracı ayrı. Yazılan kayıt geçici
    oturum kimliğiyle yapılır; ölçüm sonunda silinir."""
    oturum = f"olcum{os.getpid():06d}-0000"
    yol = L._oturum_json_yol(sd, oturum)
    sure = {"okuma": [], "yazma": [], "yazma_ilk": []}
    try:
        for i in range(n):
            tur = "yazma" if i % 2 else "okuma"
            girdi = {"file_path": os.path.join(cwd, f"o{i % 7}.py")} if tur == "yazma" else {"file_path": "x"}
            arac = "Edit" if tur == "yazma" else "Read"
            t0 = time.perf_counter()
            F.arac_oncesi(sd, oturum, cwd, arac, girdi, False)
            sure[tur].append((time.perf_counter() - t0) * 1000)
        for i in range(min(100, max(10, n // 10))):  # her biri bu oturum için yeni dosya: komşu taraması yolu
            t0 = time.perf_counter()
            F.arac_oncesi(sd, oturum, cwd, "Edit", {"file_path": os.path.join(cwd, f"yeni{i}.py")}, False)
            sure["yazma_ilk"].append((time.perf_counter() - t0) * 1000)
    finally:
        for ek in ("", ".lock", ".gelen.jsonl"):
            try:
                os.remove(yol[:-5] + ".json" + ek if ek != ".gelen.jsonl" else yol[:-5] + ek)
            except OSError:
                pass
    out = {"n": n}
    for tur, v in sure.items():
        if v:
            v.sort()
            out[tur] = {"n": len(v), "ortanca_ms": round(statistics.median(v), 2),
                        "p95_ms": round(v[int(len(v) * 0.95) - 1], 2), "en_buyuk_ms": round(v[-1], 2)}
    return out
