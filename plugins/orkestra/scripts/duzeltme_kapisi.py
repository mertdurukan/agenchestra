"""A9 kapısı (ADR-0083): denetçinin mekanik düzeltmesini model çağırmadan doğrular.

Denetçi `Edit` ile yalnız biçim ya da sayı düzeltir ve her düzeltmeyi `duzeltmeler[]` satırıyla bildirir
(`dosya`, `tur`, `once`, `sonra`, `kanit_komutu`). Kapı üç şeyi sınar: kart çıktılarında is-bitti anından beri
değişen her dosya bir satırla anılmış mı, her satır gerçekten değişen bir dosyayı ve yazılan `sonra` metnini
gösteriyor mu, `kanit_komutu` yeniden koşunca geçiyor mu. Yalnız `cfg` (PENCERESIZ) bağımlılığı vardır.
"""
from __future__ import annotations

import hashlib
import os
import subprocess

import cfg

# düzeltme türü -> ret nedeni kodu (ret_nedeni.NEDENLER); ret defterine "duzeltildi:<kod>" olarak düşer
TUR_NEDEN = {"bicim": "bicim", "sayi": "sayi-tutarsiz"}
KOMUT_ZAMAN_ASIMI_S = 60


def norm(yol: str, proje: str) -> str:
    return os.path.normcase(os.path.abspath(yol if os.path.isabs(yol) else os.path.join(proje, yol))).replace("\\", "/")


def _sha(yol: str):
    try:
        with open(yol, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return None


def dosya_shalari(proje: str, ciktilar) -> dict:
    """Kart çıktılarının dosya başına sha256'sı (var olmayan dosya None). is-bitti anında kayda alınır."""
    return {norm(c, proje): _sha(norm(c, proje)) for c in (ciktilar or []) if isinstance(c, str) and c}


def neden_kodlari(duz) -> list:
    return ["duzeltildi:" + TUR_NEDEN[d["tur"]] for d in duz or [] if isinstance(d, dict) and d.get("tur") in TUR_NEDEN]


def _kos(komut: str, proje: str) -> tuple:
    try:
        p = subprocess.run(komut, shell=True, cwd=proje, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=KOMUT_ZAMAN_ASIMI_S, **cfg.PENCERESIZ)
        return p.returncode, p.stdout or ""
    except subprocess.TimeoutExpired:
        return 124, ""
    except OSError:
        return 127, ""


def _metin(yol: str) -> str:
    try:
        with open(yol, encoding="utf-8", errors="replace", newline="") as f:  # newline="": CRLF/LF düzeltmesi görünür kalır
            return f.read()
    except OSError:
        return ""


def kapi(proje: str, ciktilar, onceki_sha, duz, kos=_kos) -> list:
    """Hata iletilerinin listesi; boş liste = geçti. `onceki_sha`: is-bitti anındaki dosya_shalari (yoksa değişim
    tespiti yapılamaz, yalnız verilen satırlar sınanır)."""
    hatalar: list = []
    if duz is None:
        duz = []
    if not isinstance(duz, list) or not all(isinstance(d, dict) for d in duz):
        return ["duzeltmeler[] satır nesnelerinden oluşan bir liste olmalı"]
    onceki = onceki_sha if isinstance(onceki_sha, dict) else None
    degisen = set()
    if onceki is not None:
        degisen = {p for p, s in onceki.items() if _sha(p) != s}
    anilan = set()
    for i, d in enumerate(duz, 1):
        et = "duzeltmeler[%d]" % i
        eksik = [a for a in ("dosya", "tur", "once", "sonra") if not (isinstance(d.get(a), str) and d.get(a))]
        if eksik:
            hatalar.append("%s alanı eksik: %s" % (et, ",".join(eksik)))
            continue
        if d["tur"] not in TUR_NEDEN:
            hatalar.append("%s tur %r geçersiz (bicim|sayi)" % (et, d["tur"]))
            continue
        if d["once"] == d["sonra"]:
            hatalar.append("%s once ile sonra aynı" % et)
            continue
        komut = d.get("kanit_komutu")
        if d["tur"] == "sayi" and not (isinstance(komut, str) and komut.strip()):
            hatalar.append("%s sayı düzeltmesinde kanit_komutu şart (K-002)" % et)
            continue
        yol = norm(d["dosya"], proje)
        if onceki is not None and yol not in onceki:
            hatalar.append("%s dosya kartın çıktısı değil: %s" % (et, d["dosya"]))
            continue
        if onceki is not None and yol not in degisen:
            hatalar.append("%s dosya is-bitti'den beri değişmemiş: %s" % (et, d["dosya"]))
            continue
        if d["sonra"] not in _metin(yol):
            hatalar.append("%s sonra metni dosyada yok: %s" % (et, d["dosya"]))
            continue
        anilan.add(yol)
        if isinstance(komut, str) and komut.strip():
            kod, cikti = kos(komut, proje)
            if kod != 0:
                hatalar.append("%s kanit_komutu çıkış %s verdi" % (et, kod))
            elif d["tur"] == "sayi" and d["sonra"] not in cikti:
                hatalar.append("%s kanit_komutu çıktısı sonra değerini (%s) içermiyor" % (et, d["sonra"]))
    for p in sorted(degisen - anilan):
        hatalar.append("dosya değişti ama duzeltmeler[] satırı yok: %s" % p)
    return hatalar
