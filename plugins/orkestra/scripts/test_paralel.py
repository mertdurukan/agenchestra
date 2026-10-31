#!/usr/bin/env python3
"""Bağımlılıksız paralel pytest koşucusu: her test dosyası ayrı alt süreçte, N işçili havuzda.

Kullanım: test_paralel.py [-n N] [--zaman-asimi SN] [--en-yavas K] [yol ...]
Çıktı dosya sırasıyla birleşir; pytest'in FAILED/ERROR satırları olduğu gibi korunur.
Çıkış: 0 hepsi geçti; 1 biri düştü / zaman aşımı / toplama hatası; 2 kullanım hatası ya da koşulacak test yok;
3 makine genelindeki test kirası (kaynak_kira.py, ihlal modu) bekleme üst sınırında alınamadı.
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
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cfg  # noqa: E402
import kaynak_kira  # noqa: E402
import paralel_kos  # noqa: E402

VARSAYILAN_ZAMAN_ASIMI = 900.0
# Önceki koşuların dosya süreleri: en yavaş dosyalar havuza önce girer (LPT), kuyruk kısalır. Kayıt yoksa/bozuksa sıra korunur.
SURE_KAYDI = os.path.join(tempfile.gettempdir(), "orkestra_test_sureleri.json")
SON_GUNLUK = os.path.join(tempfile.gettempdir(), "orkestra_son_test.log")  # tam çıktı; düşen ad(lar)ı için takımı yeniden koşma
# Tek dosya tüm koşuyu belirliyorsa (LPT sırası yetmez) önceki süresi bu eşiği aşan dosya test düğümlerine bölünüp
# birden çok alt süreçte koşulur; her parça yaklaşık PARCA_HEDEF_SN sürecek kadar. Testler kendi geçici dizinini kurar.
PARCALA_ESIK_SN = 40.0
PARCA_HEDEF_SN = 30.0


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


def dugumleri_topla(dosya):
    """Dosyadaki test düğüm kimlikleri (`<mutlak dosya>::Sınıf::test`); toplanamazsa boş liste (bölünmez)."""
    mutlak = os.path.abspath(dosya)
    try:
        p = subprocess.run([sys.executable, "-m", "pytest", mutlak, "--collect-only", "-q", "-p", "no:cacheprovider"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           env=dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1"),
                           timeout=120, cwd=calisma_dizini(dosya), **cfg.PENCERESIZ)
    except (subprocess.TimeoutExpired, OSError):
        return []
    if p.returncode != 0:
        return []
    return [mutlak + "::" + l.split("::", 1)[1].strip() for l in p.stdout.splitlines() if "::" in l]


def parcalara_bol(dosya, onceki_sure, en_cok):
    """Önceki süresi eşiği aşan dosyayı en çok `en_cok` düğüm grubuna böler (döngüsel dağıtım); bölünmüyorsa None."""
    if onceki_sure is None or onceki_sure < PARCALA_ESIK_SN or en_cok < 2:
        return None
    k = min(en_cok, int(-(-onceki_sure // PARCA_HEDEF_SN)))
    dugumler = dugumleri_topla(dosya)
    k = min(k, len(dugumler))
    if k < 2:
        return None
    return [dugumler[i::k] for i in range(k)]


def tek_dosya(dosya, zaman_asimi, dugumler=None):
    """-> (dosya, çıkış_kodu, çıktı, süre, zaman_asimi_mi). `dugumler` verilirse yalnız o düğümler koşulur."""
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    env.setdefault("ORKESTRA_TEKNIK_KAPISI", "0")
    env.setdefault("ORKESTRA_MEVCUT_KAPISI", "0")
    env.setdefault("ORKESTRA_SIRA_KAPISI", "0")
    env.setdefault("ORKESTRA_KART_KONTROL", "0")  # I-224 P8: eski kart fikstürleri `kontrol:` taşımaz
    env.setdefault("ORKESTRA_DOGRULAMA_KAPISI", "0")
    komut = [sys.executable, "-m", "pytest"] + (list(dugumler) if dugumler else [os.path.abspath(dosya)]) + ["-q", "-p", "no:cacheprovider"]
    t = time.time()
    try:
        p = subprocess.run(komut, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           env=env, timeout=zaman_asimi, cwd=calisma_dizini(dosya), **cfg.PENCERESIZ)
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
    ap.add_argument("-n", type=pozitif_int, default=paralel_kos.cekirdek_sayisi(), help="işçi sayısı (varsayılan: CPU, bellek ve CI sınırından otomatik; paralel_kos.py)")
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
    sureler = sureleri_oku()
    sira = baslatma_sirasi(dosyalar, sureler)
    parcalar = {f: parcalara_bol(f, sureler.get(os.path.abspath(f)), a.n) for f in sira}
    istenen = min(a.n, len(dosyalar) + sum(len(v) for v in parcalar.values() if v))
    # I-309 P4: makine genelinde kira ve ortak işçi bütçesi koşucunun başladığı noktada alınır (kaynak_kira.py).
    try:
        with kaynak_kira.kira(istenen, komut=" ".join(["test_paralel.py"] + list(argv if argv is not None else sys.argv[1:]))) as kira:
            kisildi = f", kira: {kira.isci}" if kira.isci < istenen else ""
            with concurrent.futures.ThreadPoolExecutor(max_workers=kira.isci) as havuz:
                isler = {f: ([havuz.submit(tek_dosya, f, a.zaman_asimi, g) for g in parcalar[f]] if parcalar[f]
                             else [havuz.submit(tek_dosya, f, a.zaman_asimi)]) for f in sira}
                sonuclar, toplam = [], {}
                for f in dosyalar:  # çıktı yine dosya sırasıyla
                    r = [i.result() for i in isler[f]]
                    sonuclar.append((f, max(x[1] for x in r), chr(10).join(x[2] for x in r), max(x[3] for x in r), any(x[4] for x in r)))
                    toplam[f] = sum(x[3] for x in r)  # kayıt, bölünse de dosyanın ardışık süresidir (bir sonraki bölme kararı)
    except kaynak_kira.KiraZamanAsimi as e:
        print(str(e))
        return 3
    sureleri_yaz([(d, k, c, toplam[d], asim) for d, k, c, _, asim in sonuclar])

    dus = asim = 0
    dusenler = []
    for dosya, kod, cikti, sure, asimi in sonuclar:
        dusenler += [x.strip() for x in (cikti or "").splitlines() if x.startswith(("FAILED ", "ERROR "))]
        print(f"===== {dosya} ({sure:.1f} s) =====")
        if cikti:
            print(cikti.rstrip("\n"))
        if asimi:
            asim += 1
            print(f"zaman aşımı: {dosya} {a.zaman_asimi:g} sn içinde bitmedi, süreç öldürüldü")
        elif kod != 0:
            dus += 1
    print(f"===== {len(dosyalar)} dosya, {dus} düşen, {asim} süre aşan, {time.time() - t0:.1f} s (-n {a.n}{kisildi}) =====")
    if dusenler:
        print("Düşenler:")
        for d in dusenler:
            print("  " + d[:200])
    try:
        with open(SON_GUNLUK, "w", encoding="utf-8") as f:
            for dosya, _, cikti, sure, _ in sonuclar:
                f.write(f"===== {dosya} ({sure:.1f} s) =====" + chr(10) + (cikti or "") + chr(10))
        print(f"Tam çıktı: {SON_GUNLUK}")
    except OSError:
        pass

    if a.en_yavas > 0:
        print(f"En yavaş {a.en_yavas} dosya:")
        for dosya, _, _, sure, _ in sorted(sonuclar, key=lambda r: -r[3])[:a.en_yavas]:
            print(f"  {sure:7.1f} s  {dosya}")
    return 1 if (dus or asim) else 0


if __name__ == "__main__":
    sys.exit(main())
