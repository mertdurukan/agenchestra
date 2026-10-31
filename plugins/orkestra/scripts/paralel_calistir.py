#!/usr/bin/env python3
"""Genel paralel çalıştırıcı (P-041): bağımsız komutları (lint, derleme, doğrulama betikleri, testler) havuzda koşar.

Kullanım: paralel_calistir.py [-n N] [--zaman-asimi SN] [--ilk-hatada-dur] -- "komut1" "komut2" ...
Genişlik `paralel_kos.cekirdek_sayisi()` (ORKESTRA_PARALEL_N / ayar ezer) ile komut sayısının küçüğüdür.
Çıktı komut sırasıyla birleşir. Çıkış: 0 hepsi 0 döndü; 1 biri düştü / zaman aşımı / iptal; 2 kullanım hatası.
"""
import argparse
import concurrent.futures
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ork_lib as L  # noqa: E402
import paralel_kos  # noqa: E402

VARSAYILAN_ZAMAN_ASIMI = 900.0


def calistir(komutlar, genislik=None, zaman_asimi=VARSAYILAN_ZAMAN_ASIMI, ilk_hatada_dur=False, cwd=None):
    """-> [(komut, çıkış_kodu | None (iptal), çıktı, süre)] komut sırasıyla. `genislik` yoksa otomatik."""
    cwd = cwd or os.getcwd()
    n = max(1, min(genislik or paralel_kos.cekirdek_sayisi(cwd), len(komutlar)))
    dur = threading.Event()

    def is_(komut):
        if dur.is_set():
            return None, "", 0.0
        kod, cikti, sure = L.kabuk_kos(komut, cwd, zaman_asimi)
        if kod != 0 and ilk_hatada_dur:
            dur.set()
        return kod, cikti, sure

    with concurrent.futures.ThreadPoolExecutor(max_workers=n) as havuz:
        vadeler = [havuz.submit(is_, k) for k in komutlar]
        return [(k,) + v.result() for k, v in zip(komutlar, vadeler)]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("komutlar", nargs="+", help="paralel koşacak bağımsız komutlar")
    ap.add_argument("-n", type=int, default=None, help="genişlik (varsayılan: otomatik)")
    ap.add_argument("--zaman-asimi", type=float, default=VARSAYILAN_ZAMAN_ASIMI, help="komut başına saniye")
    ap.add_argument("--ilk-hatada-dur", action="store_true", help="biri düşünce başlamamış işleri iptal et")
    a = ap.parse_args(argv)
    if a.n is not None and a.n < 1:
        print("-n 1 ya da daha büyük olmalı")
        return 2
    t0 = time.time()
    sonuc = calistir(a.komutlar, a.n, a.zaman_asimi, a.ilk_hatada_dur)
    dusen = []
    for komut, kod, cikti, sure in sonuc:
        durum = "iptal" if kod is None else ("zaman aşımı" if kod == -1 else f"çıkış {kod}")
        print(f"===== {komut} ({sure:.1f} s, {durum}) =====")
        if cikti:
            print(cikti.rstrip("\n"))
        if kod != 0:
            dusen.append(komut)
    print(f"===== {len(sonuc)} komut, {len(dusen)} düşen/iptal, {time.time() - t0:.1f} s =====")
    for k in dusen:
        print("  düşen: " + k[:200])
    return 1 if dusen else 0


if __name__ == "__main__":
    sys.exit(main())
