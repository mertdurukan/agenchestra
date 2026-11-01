"""Devir oranı ölçümü (ADR-0099), salt okuma; model çağırmaz.

  devir_olcum.py --n-hesapla [--p1 0.204 --p2 0.354 --alfa 0.05 --guc 0.8]   grup başına gereken tur (bağımsız)
  devir_olcum.py --taban [--proje-kok ~/.claude/projects --tarih 2026-10-14 --on-ek C--Work-DemoRoot]
        transkriptlerden: iş belgesi dışında >=3 ayrı dosya yazılan ana ajan turları ve içinde alt ajan olanlar
  devir_olcum.py --deney [--klasor DURUM_DIZINI]
        gunluk.jsonl `devir_olay` kayıtları (kontrol / hatırlatma) ile zaman.jsonl `alt` satırlarını birleştirir;
        birincil analiz: birleşik, oturum kümeli iki oran testi (iki yönlü); ρ ve tasarım etkisiyle gereken n.
Sonuç: n yetmiyorsa 'ölçülemedi'. Tetikleniş hatırlatmadan önce alt ajansız olduğundan sonuç = tetikten sonra devir oranı.
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import math
import os
import re
import sys
import time
from statistics import NormalDist

HEDEF_P1, HEDEF_P2 = 0.204, 0.354
YAZAN = ("Edit", "Write", "MultiEdit", "NotebookEdit")
DEVIR = ("Agent", "Task", "Workflow")
# Taban tanımı (mevcut_durum §2): iş belgesi / orkestra bakımı muaf, 3'ten az ayrı dosya muaf
BELGE = r"(/plan\.md|/todo\.md|mevcut_durum|sozlesme_|calisma_ozeti|/adr/|/oturumlar\.md|/is\.json|teknik_detay|/readme\.md)"
BELGE_DAR = r"(/plan\.md|/todo\.md|mevcut_durum|sozlesme_|calisma_ozeti|/adr/)"


def n_hesapla(p1: float, p2: float, alfa: float = 0.05, guc: float = 0.8) -> float:
    """Grup başına gereken örnek (iki oran, iki yönlü, bağımsız gözlem)."""
    nd = NormalDist()
    za, zb = nd.inv_cdf(1 - alfa / 2), nd.inv_cdf(guc)
    pb = (p1 + p2) / 2
    return (za * math.sqrt(2 * pb * (1 - pb)) + zb * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))) ** 2 / (p2 - p1) ** 2


def tur_sinifi(yollar: list[str]) -> str:
    p = [y.replace("\\", "/").lower() for y in yollar]
    if all(re.search(BELGE, x) for x in p):
        return "is_belgesi"
    if all("/.claude/orkestra/" in x or "/memory/" in x for x in p):
        return "orkestra_bakim"
    if len(set(p)) < 3:
        return "ayni_dosya"
    if sum(1 for x in p if re.search(BELGE_DAR, x)) >= len(p) - 1:
        return "is_belgesi+1"
    return "muaf_olmayan"


def taban(proje_kok: str, tarih: tuple, on_ek: str) -> dict:
    esik = time.mktime(tarih)
    dosyalar = [f for f in glob.glob(os.path.join(proje_kok, on_ek + "*", "*.jsonl")) if os.path.getmtime(f) >= esik]
    sayac: collections.Counter = collections.Counter()

    def kapat(tur):
        if tur and len(tur["yol"]) >= 3:
            sayac[(tur_sinifi(tur["yol"]), tur["alt"])] += 1

    for f in dosyalar:
        tur = None
        try:
            for ham in open(f, encoding="utf-8", errors="ignore"):
                try:
                    o = json.loads(ham)
                except ValueError:
                    continue
                if not isinstance(o, dict) or o.get("isSidechain"):
                    continue
                t = o.get("type")
                if t == "user" and not o.get("isMeta"):
                    m = (o.get("message") or {}).get("content")
                    if isinstance(m, list) and any(isinstance(x, dict) and x.get("type") == "tool_result" for x in m):
                        continue
                    kapat(tur)
                    tur = {"yol": [], "alt": False}
                elif t == "assistant" and tur is not None:
                    for x in (o.get("message") or {}).get("content") or []:
                        if isinstance(x, dict) and x.get("type") == "tool_use":
                            ad, gi = x.get("name"), x.get("input") or {}
                            if ad in YAZAN:
                                y = gi.get("file_path") or gi.get("notebook_path")
                                if y:
                                    tur["yol"].append(y)
                            elif ad in DEVIR:
                                tur["alt"] = True
            kapat(tur)
        except OSError:
            continue
    mo = {a: s for (k, a), s in sayac.items() if k == "muaf_olmayan"}
    top = sum(mo.values())
    return {"dosya": len(dosyalar), "muaf_olmayan_tur": top, "alt_ajanli": mo.get(True, 0),
            "alt_ajansiz": mo.get(False, 0), "oran": (mo.get(True, 0) / top) if top else None,
            "siniflar": {f"{k}/{'alt' if a else 'altsiz'}": s for (k, a), s in sorted(sayac.items())}}


def _satirlar(yol: str):
    try:
        with open(yol, encoding="utf-8", errors="ignore") as f:
            for ham in f:
                try:
                    o = json.loads(ham)
                except ValueError:
                    continue
                if isinstance(o, dict):
                    yield o
    except OSError:
        return


def kume_test(gruplar: dict) -> dict:
    """gruplar: {grup: {oturum: [y1, y2, ...]}}. Oturum kümeli oran farkı (oran tahmincisi, küme-gürbüz varyans)."""
    ozet = {}
    for g, oturumlar in gruplar.items():
        k = len(oturumlar)
        n = sum(len(v) for v in oturumlar.values())
        y = sum(sum(v) for v in oturumlar.values())
        p = y / n if n else 0.0
        var = 0.0
        if k > 1 and n:
            var = k / (k - 1) * sum((sum(v) - p * len(v)) ** 2 for v in oturumlar.values()) / n ** 2
        ozet[g] = {"oturum": k, "tur": n, "devir": y, "oran": p, "var": var}
    a, b = ozet.get("kontrol"), ozet.get("hatirlatma")
    sonuc = {"gruplar": ozet}
    if a and b and a["tur"] and b["tur"]:
        se = math.sqrt(a["var"] + b["var"])
        fark = b["oran"] - a["oran"]
        z = fark / se if se else None
        # se=0: gruplar içinde hiç değişim yok; fark varsa kesin ayrım (p=0), yoksa fark yok (p=1)
        p = (2 * (1 - NormalDist().cdf(abs(z)))) if z is not None else (0.0 if fark else 1.0)
        sonuc.update({"fark": fark, "z": z, "p": p})
    return sonuc


def rho_ve_etki(oturumlar: dict) -> tuple:
    """Tek yönlü ANOVA ρ tahmini (ikili sonuç) ve tasarım etkisi 1+(m-1)ρ; m ortalama küme büyüklüğü."""
    k = len(oturumlar)
    ns = [len(v) for v in oturumlar.values()]
    n = sum(ns)
    if k < 2 or n <= k:
        return 0.0, 1.0
    ort = sum(sum(v) for v in oturumlar.values()) / n
    ssb = sum(len(v) * (sum(v) / len(v) - ort) ** 2 for v in oturumlar.values())
    ssw = sum(sum((x - sum(v) / len(v)) ** 2 for x in v) for v in oturumlar.values())
    msb, msw = ssb / (k - 1), ssw / (n - k)
    n0 = (n - sum(x * x for x in ns) / n) / (k - 1)
    payda = msb + (n0 - 1) * msw
    rho = max(0.0, (msb - msw) / payda) if payda > 0 else 0.0
    m = n / k
    return rho, 1 + (m - 1) * rho


def deney(klasor: str, p1: float = HEDEF_P1, p2: float = HEDEF_P2) -> dict:
    olaylar = [o for o in _satirlar(os.path.join(klasor, "gunluk.jsonl")) if o.get("tur") == "devir_olay"]
    devirli = {o.get("istek_id") for o in _satirlar(os.path.join(klasor, "zaman.jsonl"))
               if o.get("tur") == "alt" and o.get("istek_id")}
    gruplar: dict = {"kontrol": {}, "hatirlatma": {}}
    for o in olaylar:
        g = o.get("grup")
        if g in gruplar:
            gruplar[g].setdefault(o.get("oturum") or "?", []).append(1 if o.get("istek_id") in devirli else 0)
    t = kume_test(gruplar)
    tum: dict = {}
    for g in gruplar.values():
        for s, v in g.items():
            tum.setdefault(s, []).extend(v)
    rho, deff = rho_ve_etki(tum)
    gerekli = math.ceil(n_hesapla(p1, p2) * deff)
    en_az = min(t["gruplar"]["kontrol"]["tur"], t["gruplar"]["hatirlatma"]["tur"])
    t.update({"rho": rho, "tasarim_etkisi": deff, "gerekli_grup_basina": gerekli, "gercek_en_az_grup": en_az,
              "karar": "ölçülemedi (n yetmiyor)" if en_az < gerekli else "yeterli n"})
    return t


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n-hesapla", action="store_true")
    ap.add_argument("--taban", action="store_true")
    ap.add_argument("--deney", action="store_true")
    ap.add_argument("--p1", type=float, default=HEDEF_P1)
    ap.add_argument("--p2", type=float, default=HEDEF_P2)
    ap.add_argument("--alfa", type=float, default=0.05)
    ap.add_argument("--guc", type=float, default=0.8)
    ap.add_argument("--proje-kok", default=os.path.expanduser("~/.claude/projects"))
    ap.add_argument("--on-ek", default=re.sub(r"[^A-Za-z0-9]", "-", os.getcwd()))
    ap.add_argument("--tarih", default="2026-10-14")
    ap.add_argument("--klasor", default=None)
    a = ap.parse_args(argv)
    if a.n_hesapla:
        ham = n_hesapla(a.p1, a.p2, a.alfa, a.guc)
        print(json.dumps({"grup_basina": math.ceil(ham), "ham": ham}, ensure_ascii=False))
    elif a.taban:
        y, m, d = (int(x) for x in a.tarih.split("-"))
        print(json.dumps(taban(a.proje_kok, (y, m, d, 0, 0, 0, 0, 0, 0), a.on_ek), ensure_ascii=False))
    elif a.deney:
        klasor = a.klasor
        if not klasor:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import ork_lib as L
            klasor = L.durum_dizini(os.getcwd())
        print(json.dumps(deney(klasor, a.p1, a.p2), ensure_ascii=False, indent=2))
    else:
        ap.print_help()
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
