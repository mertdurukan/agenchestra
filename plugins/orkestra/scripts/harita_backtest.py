"""Proje bilgi grafiği geriye dönük sınama (ADR-0118, I-296; model çağırmaz).

Soru: bir dosyaya dokunan kişiye harita, aynı commit'te değişen diğer dosyaları ne ölçüde öngörür?
Yöntem (walk-forward, sızıntısız): commit'ler eskiden yeniye gezilir; her sınama commit'inde commit'in her dosyası
sırayla tohum olur, öngörü = tohumun komşuları, doğru = commit'in diğer dosyaları. Komşular:
- geçmiş kenar: yalnız o commit'ten ÖNCEKİ commit'lerde en az `ASGARI_BIRLIKTE` kez birlikte değişen dosyalar (sınanan commit görülmez),
- statik kenar: bugünkü importlar ve yol atıfları (`yuksek` güvenli; `**/<ad>` desenli `orta` kenar kalabalık yanlış pozitif
  ürettiğinden öngörüye girmez). Sınır: yapısal olduğundan geçmişe taşınması hafif iyimserdir.
Yalnız bugün diskte var olan dosyalar sayılır. Ölçüt: commit başına (tohum ortalaması) recall ve precision, sonra commit ortalaması;
precision yalnız öngörü üretilen tohumlarda, `kapsama` öngörü üretilen tohumların oranıdır.
Eşik (plan P9): en az 126 sınama commit'i, recall >= 0.80, precision >= 0.50.
Kullanım: `python harita_backtest.py <proje> [--isinma 0.3]`.
"""
from __future__ import annotations

import argparse
import collections
import itertools
import json
import os
import subprocess

import cfg
import harita_kenar as K

MIN_COMMIT = 126
ESIK_RECALL = 0.80
ESIK_PRECISION = 0.50


def commitler(kok: str) -> list[list[str]]:
    """Eskiden yeniye commit başına dosya listesi (en az 2, en çok `MAKS_COMMIT_DOSYA` dosya)."""
    cikti = subprocess.run(["git", "-c", "safe.directory=*", "log", "--reverse", "--name-only", "--pretty=format:@@%h"],
                           cwd=kok, capture_output=True, text=True, encoding="utf-8", timeout=300, **cfg.PENCERESIZ).stdout
    sonuc = []
    for blok in cikti.split("@@"):
        dosyalar = sorted({s.strip() for s in blok.splitlines()[1:] if s.strip()})
        if 2 <= len(dosyalar) <= K.MAKS_COMMIT_DOSYA:
            sonuc.append(dosyalar)
    return sonuc


def statik_komsular(kok: str) -> dict[str, set[str]]:
    kom = collections.defaultdict(set)
    for k in K.statik_kenarlar(kok):
        if k["guven"] == "yuksek" and not k["hedef"].startswith("**/"):
            kom[k["kaynak"]].add(k["hedef"])
            kom[k["hedef"]].add(k["kaynak"])
    return kom


def alan(f: str, derinlik: int = 3) -> str:
    """Dosyanın alanı: dizin yolunun ilk `derinlik` bileşeni (kökteki dosya '.')."""
    return "/".join(f.split("/")[:-1][:derinlik]) or "."


def olc(kok: str, isinma: float = 0.3, asgari: int = K.ASGARI_BIRLIKTE, cm: list[list[str]] | None = None,
        duzey: str = "dosya", olasilik: float = 0.0, parca: tuple[float, float] = (0.0, 1.0)) -> dict:
    cm = cm if cm is not None else commitler(kok)
    var: dict[str, bool] = {}

    def mevcut(f):
        if f not in var:
            var[f] = os.path.exists(os.path.join(kok, f))
        return var[f]

    statik = statik_komsular(kok)
    esik_sira = int(len(cm) * isinma)
    adj: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    adj_alan: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)  # alan↔alan birlikte değişim
    alan_sayi: collections.Counter = collections.Counter()  # alanın değiştiği commit sayısı (koşullu olasılık paydası)
    lo = esik_sira + int((len(cm) - esik_sira) * parca[0])
    hi = esik_sira + int((len(cm) - esik_sira) * parca[1])
    recall_l, precision_l, kapsama_l = [], [], []
    kacan: collections.Counter = collections.Counter()
    for sira, dosyalar in enumerate(cm):
        canli = [f for f in dosyalar if mevcut(f)]
        if lo <= sira < hi and len(canli) >= 2:
            r_t, p_t, kapsanan = [], [], 0
            for tohum in canli:
                dogru = set(canli) - {tohum}
                ongoru = {g for g, n in adj[tohum].items() if n >= asgari and mevcut(g)} | {g for g in statik.get(tohum, ()) if mevcut(g)}
                ongoru.discard(tohum)
                if duzey == "alan":  # alan düzeyi: öngörü ve gerçek, tohumun kendi alanı dışındaki alanlardır
                    kendi = alan(tohum)
                    dogru = {alan(g) for g in dogru} - {kendi}
                    ongoru = {alan(g) for g in ongoru} | {b for b, n in adj_alan[kendi].items() if n >= asgari and n / alan_sayi[kendi] >= olasilik}
                    ongoru -= {kendi}
                    if not dogru:
                        continue
                r_t.append(len(ongoru & dogru) / len(dogru))
                for g in dogru - ongoru:
                    kacan[tuple(sorted((tohum, g)))] += 1
                if ongoru:
                    kapsanan += 1
                    p_t.append(len(ongoru & dogru) / len(ongoru))
            if not r_t:
                continue
            recall_l.append(sum(r_t) / len(r_t))
            kapsama_l.append(kapsanan / len(r_t))
            if p_t:
                precision_l.append(sum(p_t) / len(p_t))
        for a, b in itertools.combinations(sorted(dosyalar), 2):  # sınamadan SONRA öğrenilir: sızıntı yok
            adj[a][b] += 1
            adj[b][a] += 1
        alanlar = sorted({alan(f) for f in dosyalar})
        for a in alanlar:
            alan_sayi[a] += 1
        for a, b in itertools.permutations(alanlar, 2):
            adj_alan[a][b] += 1
    n = len(recall_l)
    ort = lambda l: round(sum(l) / len(l), 4) if l else 0.0  # noqa: E731
    sonuc = {"sinama_commit": n, "precision_olculen_commit": len(precision_l), "recall": ort(recall_l),
             "precision": ort(precision_l), "kapsama": ort(kapsama_l), "isinma": isinma, "asgari_birlikte": asgari, "duzey": duzey, "olasilik": olasilik, "parca": list(parca)}
    sonuc["en_cok_kacan_cift"] = [{"cift": list(c), "kez": k} for c, k in kacan.most_common(15)]
    sonuc["yeterli_ornek"] = n >= MIN_COMMIT
    sonuc["esik_gecti"] = bool(sonuc["yeterli_ornek"] and sonuc["recall"] >= ESIK_RECALL and sonuc["precision"] >= ESIK_PRECISION)
    return sonuc


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("proje")
    ap.add_argument("--isinma", type=float, default=0.3)
    ap.add_argument("--asgari", type=int, default=K.ASGARI_BIRLIKTE)
    ap.add_argument("--duzey", choices=("dosya", "alan"), default="dosya")
    ap.add_argument("--olasilik", type=float, default=0.0)
    ap.add_argument("--parca", default="0,1", help="değerlendirilen dilim, ör. 0,0.5 (ayarlama) ve 0.5,1 (sınama)")
    arg = ap.parse_args()
    lo, hi = (float(x) for x in arg.parca.split(","))
    print(json.dumps(olc(arg.proje, arg.isinma, arg.asgari, duzey=arg.duzey, olasilik=arg.olasilik, parca=(lo, hi)), ensure_ascii=False))
