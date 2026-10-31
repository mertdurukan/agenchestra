"""Proje bilgi grafiği kenar çıkarıcı (ADR-0118, I-296; model çağırmaz).

Kaynaklar (spike kararı: `ast` + yol atfı + git birlikte-değişim; tree-sitter ve SCIP elendi):
- statik `import`: Python `ast` ile import satırı → projedeki modül dosyası; kanıt `dosya:satır`.
- statik `atif`: Python dizgesi projedeki bir dosyanın yoluna ya da (tekil) adına eşitse; ad birden çok dosyada varsa
  hedef `**/<ad>` desenidir (ör. her `SKILL.md`). Kanıt `dosya:satır`.
- geçmiş `birlikte_degisir`: git geçmişinde en az `ASGARI_BIRLIKTE` commit'te birlikte değişen dosya çifti; kanıt `git:<n> commit`.
Her kenar kaynak dosyanın içerik hash'ini taşır (eskime takibi P8). Şema: `harita_sema.py`.
Kullanım: `python harita_kenar.py <proje> [--cikti kenarlar.jsonl]`.
"""
from __future__ import annotations

import argparse
import ast
import collections
import datetime
import hashlib
import itertools
import json
import os
import subprocess

import cfg
import harita_sema as S

HARIC = {".git", "node_modules", "__pycache__", ".venv", "venv", "_arsiv", ".pytest_cache", "worktrees", "site-packages"}
ASGARI_BIRLIKTE = 3
MAKS_COMMIT_DOSYA = 30  # çok dosyalı toplu commit birlikte-değişim sinyali değildir


def _dosyalar(kok: str) -> list[str]:
    sonuc = []
    for d, altlar, adlar in os.walk(kok):
        altlar[:] = [a for a in altlar if a not in HARIC]
        sonuc += [os.path.relpath(os.path.join(d, a), kok).replace(os.sep, "/") for a in adlar]
    return sorted(sonuc)


def _hash(kok: str, rel: str) -> str:
    try:
        with open(os.path.join(kok, rel), "rb") as f:
            return hashlib.sha1(f.read()).hexdigest()[:12]
    except OSError:
        return "yok"


def _kenar(kok, kaynak, iliski, hedef, koken, guven, kanit, simdi):
    return {"kaynak": kaynak, "iliski": iliski, "hedef": hedef, "koken": koken, "guven": guven, "kanit": kanit,
            "hash": _hash(kok, kaynak), "dogrulama_zamani": simdi}


def statik_kenarlar(kok: str, dosyalar: list[str] | None = None, simdi: str | None = None) -> list[dict]:
    dosyalar = dosyalar if dosyalar is not None else _dosyalar(kok)
    simdi = simdi or datetime.datetime.now().isoformat(timespec="seconds")
    ad_dizin = collections.defaultdict(list)
    for f in dosyalar:
        ad_dizin[os.path.basename(f)].append(f)
    kume = set(dosyalar)
    kenarlar: list[dict] = []
    for f in dosyalar:
        if not f.endswith(".py"):
            continue
        try:
            with open(os.path.join(kok, f), encoding="utf-8") as fh:
                agac = ast.parse(fh.read())
        except (OSError, SyntaxError, ValueError):
            continue
        yerel = os.path.dirname(f)
        for x in ast.walk(agac):
            if isinstance(x, (ast.Import, ast.ImportFrom)):
                adlar = [x.module] if isinstance(x, ast.ImportFrom) and x.module else [a.name for a in x.names]
                for mod in adlar:
                    ust = (mod or "").split(".")[0]
                    adaylar = ad_dizin.get(ust + ".py", [])
                    hedef = next((a for a in adaylar if os.path.dirname(a) == yerel), adaylar[0] if len(adaylar) == 1 else None)
                    if hedef and hedef != f:
                        kenarlar.append(_kenar(kok, f, "import", hedef, "statik", "yuksek", f"{f}:{x.lineno}", simdi))
            elif isinstance(x, ast.Constant) and isinstance(x.value, str) and 2 < len(x.value) < 120:
                v = x.value.strip().replace("\\", "/")
                if v in kume and v != f:
                    kenarlar.append(_kenar(kok, f, "atif", v, "statik", "yuksek", f"{f}:{x.lineno}", simdi))
                elif "/" not in v and "." in v and v in ad_dizin and v != os.path.basename(f):
                    hedefler = ad_dizin[v]
                    hedef = hedefler[0] if len(hedefler) == 1 else "**/" + v
                    kenarlar.append(_kenar(kok, f, "atif", hedef, "statik", "orta" if len(hedefler) > 1 else "yuksek",
                                           f"{f}:{x.lineno}", simdi))
    gorulen, tekil = set(), []
    for k in kenarlar:
        anahtar = (k["kaynak"], k["iliski"], k["hedef"], k["kanit"])
        if anahtar not in gorulen:
            gorulen.add(anahtar)
            tekil.append(k)
    return tekil


def gecmis_kenarlar(kok: str, simdi: str | None = None, asgari: int = ASGARI_BIRLIKTE) -> list[dict]:
    simdi = simdi or datetime.datetime.now().isoformat(timespec="seconds")
    try:
        cikti = subprocess.run(["git", "-c", "safe.directory=*", "log", "--name-only", "--pretty=format:@@%h"], cwd=kok,
                               capture_output=True, text=True, encoding="utf-8", timeout=120, **cfg.PENCERESIZ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    sayac = collections.Counter()
    for blok in cikti.split("@@"):
        dosyalar = sorted({s.strip() for s in blok.splitlines()[1:] if s.strip()})
        if 2 <= len(dosyalar) <= MAKS_COMMIT_DOSYA:
            sayac.update(itertools.combinations(dosyalar, 2))
    kenarlar = []
    for (a, b), n in sorted(sayac.items()):
        if n >= asgari and os.path.exists(os.path.join(kok, a)) and os.path.exists(os.path.join(kok, b)):
            guven = "yuksek" if n >= 3 * asgari else "orta"
            kenarlar.append(_kenar(kok, a, "birlikte_degisir", b, "gecmis", guven, f"git:{n} commit", simdi))
    return kenarlar


def uret(kok: str) -> list[dict]:
    simdi = datetime.datetime.now().isoformat(timespec="seconds")
    return statik_kenarlar(kok, simdi=simdi) + gecmis_kenarlar(kok, simdi=simdi)


def yaz(kenarlar: list[dict], yol: str) -> tuple[int, list[str]]:
    """Şemaya uymayan kenarı yazmaz; (yazılan sayı, hata listesi) döner."""
    a, hatalar, n = S.ayar(), [], 0
    with open(yol, "w", encoding="utf-8") as f:
        for k in kenarlar:
            e = S.kenar_hatalari(k, a)
            if e:
                hatalar.append(f"{k.get('kaynak')}→{k.get('hedef')}: {'; '.join(e)}")
                continue
            f.write(json.dumps(k, ensure_ascii=False) + "\n")
            n += 1
    return n, hatalar


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("proje")
    ap.add_argument("--cikti", default="kenarlar.jsonl")
    arg = ap.parse_args()
    kenarlar = uret(arg.proje)
    yazilan, hata = yaz(kenarlar, arg.cikti)
    dagilim = collections.Counter((k["koken"], k["iliski"]) for k in kenarlar)
    print(f"kenar: {yazilan} yazıldı, {len(hata)} şema hatası; dağılım: {dict(dagilim)}")
