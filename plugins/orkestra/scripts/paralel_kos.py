#!/usr/bin/env python3
"""Paralel koşu çekirdeği (P-036): test ve test benzeri süreçler varsayılan paralel koşar.

`cekirdek_sayisi()` işçi sayısını makine kapasitesinden türetir:
  min(mantıksal çekirdek, (kullanılabilir bellek - rezerv) / işçi başı MB, üst sınır)
Ezme sırası: ORKESTRA_PARALEL_N > proje `.claude/orkestra/paralel_kosu.json` > eklenti `ayarlar/paralel_kosu.json`.
`1` seri koşudur. Bellek ya da CPU okunamazsa kalan değerler kullanılır; hiçbir durumda 1'in altına inmez.
Yalnız standart kütüphane (psutil gerekmez): Windows, Linux ve macOS.
"""
import json
import os
import subprocess
import sys

AYAR_ADI = "paralel_kosu.json"
VARSAYILAN = {"ust_sinir": 32, "isci_basina_mb": 400, "bellek_rezervi_mb": 1536, "ci_ust_sinir": 8, "paralel": True}


def _json(yol):
    try:
        with open(yol, encoding="utf-8") as f:
            v = json.load(f)
        return v if isinstance(v, dict) else {}
    except (OSError, ValueError):
        return {}


def ayarlar(proje=None):
    """Eklenti varsayılanı üstüne proje ezmesi. Bozuk ya da eksik dosya varsayılana düşer."""
    kok = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    d = dict(VARSAYILAN)
    d.update({k: v for k, v in _json(os.path.join(kok, "ayarlar", AYAR_ADI)).items() if k in VARSAYILAN})
    proje = proje or os.getcwd()
    d.update({k: v for k, v in _json(os.path.join(proje, ".claude", "orkestra", AYAR_ADI)).items() if k in VARSAYILAN})
    return d


def paralel_acik_mi(proje=None):
    """ORKESTRA_PARALEL=0 ya da ayarda paralel=false: paralel koşu kapalı (komut dönüşümü yapılmaz)."""
    if os.environ.get("ORKESTRA_PARALEL", "").strip() == "0":
        return False
    return ayarlar(proje).get("paralel") is not False


def mantiksal_cekirdek():
    """İşlemci kısıtı (affinity) ve Linux cgroup CPU kotası dikkate alınır."""
    n = os.cpu_count() or 1
    try:
        n = min(n, len(os.sched_getaffinity(0)))
    except (AttributeError, OSError):
        pass
    try:
        with open("/sys/fs/cgroup/cpu.max", encoding="utf-8") as f:
            kota, donem = f.read().split()[:2]
        if kota != "max":
            n = min(n, max(1, int(int(kota) / int(donem))))
    except (OSError, ValueError):
        pass
    return max(1, n)


def kullanilabilir_bellek_mb():
    """Kullanılabilir fiziksel bellek (MB); okunamazsa None."""
    try:
        if os.name == "nt":
            import ctypes

            class MS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]
            ms = MS()
            ms.dwLength = ctypes.sizeof(MS)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms)):
                return int(ms.ullAvailPhys // (1024 * 1024))
            return None
        if sys.platform == "darwin":
            toplam = int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=10).stdout.strip())
            return int(toplam * 0.6 // (1024 * 1024))  # macOS'ta "kullanılabilir" ayrı okunmaz: toplamın %60'ı
        with open("/proc/meminfo", encoding="utf-8") as f:
            for satir in f:
                if satir.startswith("MemAvailable:"):
                    return int(satir.split()[1]) // 1024
    except (OSError, ValueError, subprocess.SubprocessError, AttributeError):
        return None
    return None


def _ci_mi():
    return bool(os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS") or os.environ.get("TF_BUILD"))


def _pozitif(v, varsayilan):
    try:
        v = int(v)
    except (TypeError, ValueError):
        return varsayilan
    return v if v >= 1 else varsayilan


def cekirdek_sayisi(proje=None, cekirdek=None, bellek_mb=None):
    """Otomatik işçi sayısı (>= 1). `cekirdek` ve `bellek_mb` testte sahte değer vermek içindir."""
    ezme = os.environ.get("ORKESTRA_PARALEL_N", "").strip()
    if ezme:
        v = _pozitif(ezme, 0)
        if v:
            return v
    a = ayarlar(proje)
    n = cekirdek if cekirdek is not None else mantiksal_cekirdek()
    mb = bellek_mb if bellek_mb is not None else kullanilabilir_bellek_mb()
    if mb is not None:
        sinir = (mb - _pozitif(a["bellek_rezervi_mb"], 0)) // _pozitif(a["isci_basina_mb"], 400)
        n = min(n, max(1, int(sinir)))
    n = min(n, _pozitif(a["ust_sinir"], 32))
    if _ci_mi():
        n = min(n, _pozitif(a["ci_ust_sinir"], 8))
    return max(1, n)


if __name__ == "__main__":
    print(cekirdek_sayisi())
