"""Eklenti önbelleğindeki eski sürüm klasörlerini temizler (varsayılan: yalnız listeler).

Kullanım: python onbellek_temizle.py [--sil] [--saat 24]
Silinmez: installed_plugins.json'da kurulu sürümler ve son --saat içinde değişen klasörler (açık oturumlar
eklentiyi önbellekten yükler; yeni yayınlanmış sürüm bir oturumda kullanımda olabilir).
"""
import argparse
import json
import os
import shutil
import time


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sil", action="store_true")
    ap.add_argument("--saat", type=float, default=24.0)
    a = ap.parse_args()
    ev = os.path.expanduser("~")
    kok = os.path.join(ev, ".claude", "plugins", "cache")
    try:
        with open(os.path.join(ev, ".claude", "plugins", "installed_plugins.json"), encoding="utf-8") as f:
            kurulu = json.load(f).get("plugins", {})
    except Exception:
        print("installed_plugins.json okunamadı; hiçbir şey silinmedi.")
        return 1
    korunan = {os.path.normcase(os.path.abspath(k.get("installPath", "")))
               for liste in kurulu.values() for k in liste if isinstance(k, dict)}
    sinir = time.time() - a.saat * 3600
    adet = boyut = 0
    for pazar in os.listdir(kok):
        for eklenti in os.listdir(os.path.join(kok, pazar)):
            d = os.path.join(kok, pazar, eklenti)
            if not os.path.isdir(d):
                continue
            for surum in os.listdir(d):
                y = os.path.join(d, surum)
                if os.path.normcase(os.path.abspath(y)) in korunan or not os.path.isdir(y) or os.path.getmtime(y) > sinir:
                    continue
                b = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(y) for f in fs)
                adet += 1
                boyut += b
                print(("siliniyor " if a.sil else "silinecek ") + y)
                if a.sil:
                    shutil.rmtree(y, ignore_errors=True)
    print(f"{adet} sürüm, {boyut / 1e6:.1f} MB {'silindi' if a.sil else '(dry-run; --sil ile siler)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
