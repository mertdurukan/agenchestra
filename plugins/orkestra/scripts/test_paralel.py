#!/usr/bin/env python3
"""Bağımlılıksız paralel pytest koşucusu: her test dosyası ayrı alt süreçte, N işçili havuzda.

Kullanım: test_paralel.py [-n N] [--zaman-asimi SN] [--en-yavas K] [yol ...]
Çıktı dosya sırasıyla birleşir; pytest'in FAILED/ERROR satırları olduğu gibi korunur.
Çıkış: 0 hepsi geçti; 1 biri düştü / zaman aşımı / toplama hatası; 2 kullanım hatası ya da koşulacak test yok.
"""
import argparse
import concurrent.futures
import glob
import os
import json
import subprocess
import sys
import tempfile
import time

VARSAYILAN_ZAMAN_ASIMI = 900.0
# Önceki koşuların dosya süreleri: en yavaş dosyalar havuza önce girer (LPT), kuyruk kısalır. Kayıt yoksa/bozuksa sıra korunur.
SURE_KAYDI = os.path.join(tempfile.gettempdir(), "orkestra_test_sureleri.json")


def sureleri_oku():
    try:
        with open(SURE_KAYDI, encoding="utf-8") as f:
            v = json.load(f)
        return v if isinstance(v, dict) else {}
    except (OSError, ValueError):
        return {}


def sureleri_yaz(sonuclar):
    try:
        v = sureleri_oku()
        v.update({os.path.abspath(d): round(s, 2) for d, _, _, s, asimi in sonuclar if not asimi})
        with open(SURE_KAYDI, "w", encoding="utf-8") as f:
            json.dump(v, f)
    except OSError:
        pass


def baslatma_sirasi(dosyalar, sureler):
    """Bilinmeyen dosya en önde (yeni/değişmiş olabilir), sonra süresi uzun olandan kısaya; eşitlikte dosya sırası."""
    return sorted(dosyalar, key=lambda f: -sureler.get(os.path.abspath(f), float("inf")))


def dosyalari_bul(yollar):
    bulunan, hatalar = [], []
    for y in yollar:
        if os.path.isdir(y):
            bulunan += sorted(glob.glob(os.path.join(y, "**", "test_*.py"), recursive=True))
        elif os.path.isfile(y):
            bulunan.append(y)
        else:
            hatalar.append(y)
    gorulen, sirali = set(), []
    for f in bulunan:
        k = os.path.abspath(f)
        if k not in gorulen:
            gorulen.add(k)
            sirali.append(f)
    return sirali, hatalar


def calisma_dizini(dosya):
    """Dosya geçerli dizinin altındaysa dizini değiştirme; dışındaysa dosyanın dizini (pytest ortak atayı
    köke alıp tüm kullanıcı dizinini taramasın)."""
    cwd = os.path.abspath(os.getcwd())
    mutlak = os.path.abspath(dosya)
    try:
        if os.path.commonpath([cwd, mutlak]) == cwd:
            return None
    except ValueError:
        pass
    return os.path.dirname(mutlak)


def tek_dosya(dosya, zaman_asimi):
    """-> (dosya, çıkış_kodu, çıktı, süre, zaman_asimi_mi)"""
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    komut = [sys.executable, "-m", "pytest", os.path.abspath(dosya), "-q", "-p", "no:cacheprovider"]
    t = time.time()
    try:
        p = subprocess.run(komut, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           env=env, timeout=zaman_asimi, cwd=calisma_dizini(dosya))
        return dosya, p.returncode, (p.stdout or "") + (p.stderr or ""), time.time() - t, False
    except subprocess.TimeoutExpired as e:
        def _s(v):
            return v.decode("utf-8", "replace") if isinstance(v, bytes) else (v or "")
        return dosya, 1, _s(e.stdout) + _s(e.stderr), time.time() - t, True


def pozitif_int(s):
    try:
        v = int(s)
    except ValueError:
        raise argparse.ArgumentTypeError(f"geçersiz sayı: {s}")
    if v < 1:
        raise argparse.ArgumentTypeError("1 ya da daha büyük olmalı")
    return v


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("yollar", nargs="*", help="dizin ya da test dosyaları (varsayılan: ../tests)")
    ap.add_argument("-n", type=pozitif_int, default=max(2, (os.cpu_count() or 2) // 2), help="işçi sayısı")
    ap.add_argument("--zaman-asimi", type=float, default=VARSAYILAN_ZAMAN_ASIMI, help="dosya başına saniye")
    ap.add_argument("--en-yavas", type=int, default=0, metavar="K", help="en yavaş K dosyayı süresiyle bas")
    a = ap.parse_args(argv)

    yollar = a.yollar or [os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tests")]
    dosyalar, hatalar = dosyalari_bul(yollar)
    if hatalar:
        print("yol bulunamadı: " + ", ".join(hatalar))
        return 2
    if not dosyalar:
        print("koşulacak test dosyası yok")
        return 2

    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(a.n, len(dosyalar))) as havuz:
        isler = {f: havuz.submit(tek_dosya, f, a.zaman_asimi) for f in baslatma_sirasi(dosyalar, sureleri_oku())}
        sonuclar = [isler[f].result() for f in dosyalar]  # çıktı yine dosya sırasıyla
    sureleri_yaz(sonuclar)

    dus = asim = 0
    for dosya, kod, cikti, sure, asimi in sonuclar:
        print(f"===== {dosya} ({sure:.1f} s) =====")
        if cikti:
            print(cikti.rstrip("\n"))
        if asimi:
            asim += 1
            print(f"zaman aşımı: {dosya} {a.zaman_asimi:g} sn içinde bitmedi, süreç öldürüldü")
        elif kod != 0:
            dus += 1
    print(f"===== {len(dosyalar)} dosya, {dus} düşen, {asim} süre aşan, {time.time() - t0:.1f} s (-n {a.n}) =====")

    if a.en_yavas > 0:
        print(f"En yavaş {a.en_yavas} dosya:")
        for dosya, _, _, sure, _ in sorted(sonuclar, key=lambda r: -r[3])[:a.en_yavas]:
            print(f"  {sure:7.1f} s  {dosya}")
    return 1 if (dus or asim) else 0


if __name__ == "__main__":
    sys.exit(main())
