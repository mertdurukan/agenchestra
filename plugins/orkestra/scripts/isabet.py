"""Ön bağlam isabet ölçümü (I-139 P8, bce F49/F50): `orkestra isabet`.

Saf Python, model çağırmaz. Kapanmış bir işin mevcut durum ve plan belgelerinde anılan (diskte var olan) dosyalarla,
işin açık kaldığı sürede git commit'lerinde değişen dosyaları karşılaştırır:

- kesinlik = anılan ∩ değişen / anılan
- duyarlılık = anılan ∩ değişen / değişen

`tahmin` verilirse (ör. `--on-baglam`: ön bağlam hook'unun göreve bakıp önereceği yollar) anılan küme yerine o kullanılır.
Değişen kümeden işin kendi klasörü çıkarılır (belgeler plan değil kanıttır). Dizin anmaları sayılmaz; yalnız dosyalar.
"""
from __future__ import annotations

import glob
import os
import subprocess

import yol_denetimi as YD
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cfg  # noqa: E402

BELGELER = ("mevcut_durum_*.md", "plan.md")


def norm(yol: str) -> str:
    return os.path.normcase(os.path.abspath(yol)).replace("\\", "/")


def _git(kok: str, *args: str) -> str:
    try:
        r = subprocess.run(["git", "-c", "safe.directory=*", "-C", kok, *args], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=60, **cfg.PENCERESIZ)
    except (OSError, subprocess.SubprocessError):
        return ""
    return r.stdout if r.returncode == 0 else ""


def git_kokleri(dizinler: list[str]) -> list[str]:
    """Verilen dizinlerin git üst dizinleri (tekrarsız, sıra korunur)."""
    sonuc = []
    for d in dizinler:
        t = _git(d, "rev-parse", "--show-toplevel").strip()
        if t and t not in sonuc:
            sonuc.append(t)
    return sonuc


def kapanis_penceresi(kayit: dict) -> tuple[str, str] | None:
    """(başlangıç, bitiş) ISO; iş kapanmamışsa None. Başlangıç açılış, bitiş son `durum:kapandi` olayıdır."""
    if kayit.get("durum") != "kapandi":
        return None
    bas = kayit.get("olusturma")
    bit = None
    for g in kayit.get("gecmis") or []:
        if g.get("olay") == "durum:kapandi":
            bit = g.get("zaman")
    return (bas, bit) if bas and bit else None


def degisenler(git_koklari: list[str], bas: str, bit: str) -> set[str]:
    """Pencerede commit edilen dosyaların normalleşmiş mutlak yolları."""
    sonuc: set[str] = set()
    for k in git_koklari:
        cikti = _git(k, "log", f"--since={bas}", f"--until={bit}", "--name-only", "--pretty=format:")
        for s in cikti.splitlines():
            s = s.strip().strip('"')
            if s:
                sonuc.add(norm(os.path.join(k, s)))
    return sonuc


def anilanlar(klasor: str, kokler: list[str]) -> set[str]:
    """Mevcut durum ve plan belgelerinde backtick içinde anılan, diskte var olan dosyalar (normalleşmiş mutlak)."""
    sonuc: set[str] = set()
    dosyalar = []
    for desen in BELGELER:
        dosyalar += sorted(glob.glob(os.path.join(klasor, desen)))
    for k in YD.denetle_dosyalar(dosyalar, [klasor] + kokler):
        if not k["var"]:
            continue
        yol = k["yol"]
        adaylar = [yol] if os.path.isabs(yol) else [os.path.join(r, yol) for r in kokler]
        for a in adaylar:
            if os.path.isfile(a):
                sonuc.add(norm(a))
                break
    return sonuc


def _oran(pay: int, payda: int) -> float | None:
    return round(pay / payda, 3) if payda else None


def olc(kayit: dict, git_koklari: list[str], kokler: list[str], tahmin=None) -> dict | None:
    """Tek iş için ölçüm; kapanmamış iş ya da klasörsüz kayıt için None.
    tahmin: kayit -> yol listesi (verilirse anılan küme yerine)."""
    pencere = kapanis_penceresi(kayit)
    klasor = kayit.get("klasor")
    if not pencere or not klasor:
        return None
    kendi = norm(klasor) + "/"
    degisen = {y for y in degisenler(git_koklari, *pencere) if not y.startswith(kendi)}
    if tahmin is None:
        anilan = {y for y in anilanlar(klasor, kokler) if not y.startswith(kendi)}
    else:
        anilan = {norm(y) for y in tahmin(kayit)}
    isabet = anilan & degisen
    return {"is_id": kayit.get("id"), "baslik": kayit.get("baslik"), "anilan": len(anilan), "degisen": len(degisen),
            "isabet": len(isabet), "kesinlik": _oran(len(isabet), len(anilan)), "duyarlilik": _oran(len(isabet), len(degisen)),
            "kacirilan": sorted(degisen - anilan)[:5]}


def toplam(satirlar: list[dict]) -> dict:
    """Mikro ortalama: toplam isabet / toplam anılan, toplam isabet / toplam değişen (anılanı ya da değişeni olmayan iş dahil)."""
    a = sum(s["anilan"] for s in satirlar)
    d = sum(s["degisen"] for s in satirlar)
    i = sum(s["isabet"] for s in satirlar)
    return {"is_sayisi": len(satirlar), "anilan": a, "degisen": d, "isabet": i,
            "kesinlik": _oran(i, a), "duyarlilik": _oran(i, d)}


def _yuzde(x) -> str:
    return "-" if x is None else f"{x * 100:.0f}%"


def biclem(satirlar: list[dict], t: dict) -> str:
    if not satirlar:
        return "ölçülecek kapanmış iş yok"
    ust = [f"{s['is_id']}  anılan {s['anilan']}  değişen {s['degisen']}  isabet {s['isabet']}  "
           f"kesinlik {_yuzde(s['kesinlik'])}  duyarlılık {_yuzde(s['duyarlilik'])}" for s in satirlar]
    alt = (f"TOPLAM {t['is_sayisi']} iş  anılan {t['anilan']}  değişen {t['degisen']}  isabet {t['isabet']}  "
           f"kesinlik {_yuzde(t['kesinlik'])}  duyarlılık {_yuzde(t['duyarlilik'])}")
    return "\n".join(ust + [alt])
