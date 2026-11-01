"""Test hatası atfı (I-324 P2, S3): düşen testi `konum.yazilan` kaydıyla en çok bir sahip oturuma eşler.

Model çağırmaz, subprocess ve ağ açmaz; test dosyası çalıştırılmaz (içe aktarmalar `ast` ile okunur).
Eşleme dosyaya dayanır, yalnız "son yazan oturum"a körü körüne atıf yapılmaz: bir oturum ancak test dosyasını ya da
test dosyasının aday kaynaklarından birini yazdıysa sahip olur; hiçbiri yoksa sonuç "sahipsiz"dir (sahip None).
Kanıt gücü sırası: test dosyası > ad kuralı (test_x.py -> scripts/x.py) > test dosyasının içe aktardığı yerel modül.
Aynı sırada birden çok oturum varsa en yeni yazan (`konum.gorulme`, yoksa kayıt mtime'ı) seçilir.
Git blame kullanılmaz (K4): blame commit sahibini verir, oturumu ve bağlamını vermez.
"""
from __future__ import annotations

import ast
import json
import os
import re
import sys
import time

import oturum_farkindalik as F

# pytest kısa özet satırları: "FAILED yol::düğüm - ileti", "ERROR yol - ileti", "ERROR yol::düğüm - ileti".
# Yol Windows sürücü harfi taşıyabilir; düğüm parametre kimliği ([...]) boşluk ve " - " içerebilir.
_SATIR = re.compile(
    r"^(?P<tur>FAILED|ERROR)\s+(?P<yol>(?:[A-Za-z]:)?[^:\s][^:]*?\.py)"
    r"(?:::(?P<ad>[^\[\s]+(?:\[.*?\])?))?(?:\s+-\s.*)?\s*$")

GUC = {"test": 0, "ad_kurali": 1, "import": 2}


def _norm(yol: str) -> str:
    return F._norm(yol)


def dusenleri_ayikla(cikti_metni, kok: str | None = None) -> list[dict]:
    """pytest çıktısından düşen testler: [{test_dosyasi, test_adi, tur}]. Göreli yol `kok`a (yoksa cwd) göre mutlaklaşır.
    Bozuk ya da metin olmayan girdi boş liste verir; aynı (dosya, ad) bir kez döner, sıra korunur."""
    if not isinstance(cikti_metni, str):
        return []
    taban = kok or os.getcwd()
    sonuc, gorulen = [], set()
    for ham in cikti_metni.splitlines():
        m = _SATIR.match(ham.strip())
        if not m:
            continue
        yol = m.group("yol").strip()
        if not os.path.isabs(yol):
            yol = os.path.join(taban, yol)
        dosya = _norm(yol)
        ad = m.group("ad")
        anahtar = (dosya, ad)
        if anahtar in gorulen:
            continue
        gorulen.add(anahtar)
        sonuc.append({"test_dosyasi": dosya, "test_adi": ad, "tur": m.group("tur")})
    return sonuc


def _yerel_importlar(test_dosyasi: str) -> list[str]:
    """Test dosyasının içe aktardığı modül adları (çalıştırmadan, ast ile). Okunamaz/bozuk dosyada boş liste."""
    try:
        with open(test_dosyasi, encoding="utf-8", errors="replace") as f:
            agac = ast.parse(f.read(), filename=test_dosyasi)
    except (OSError, SyntaxError, ValueError):
        return []
    adlar = []
    for dugum in ast.walk(agac):
        if isinstance(dugum, ast.Import):
            adlar += [a.name for a in dugum.names]
        elif isinstance(dugum, ast.ImportFrom):
            if dugum.module:
                adlar.append(dugum.module)
                adlar += [dugum.module + "." + a.name for a in dugum.names if a.name != "*"]
            else:  # from . import x
                adlar += [a.name for a in dugum.names if a.name != "*"]
    return list(dict.fromkeys(adlar))


def kaynak_adaylari(test_dosyasi: str, eklenti_koku: str) -> list[dict]:
    """Test dosyasının aday kaynak dosyaları: [{dosya, tur}] (tur: ad_kurali | import). Yollar normalize mutlak.
    Ad kuralı: test_x.py -> <kök>/scripts/x.py (dosya yoksa da aday; silinmiş kaynak yine eşlenebilir).
    İçe aktarma: modül adı <kök>/scripts, test dizini ve <kök> altında .py ya da paket __init__.py olarak VARSA aday."""
    test_n = _norm(test_dosyasi)
    adaylar, gorulen = [], {test_n}

    def ekle(yol, tur):
        n = _norm(yol)
        if n not in gorulen:
            gorulen.add(n)
            adaylar.append({"dosya": n, "tur": tur})

    kok = os.path.abspath(eklenti_koku)
    scripts = os.path.join(kok, "scripts")
    ad = os.path.basename(test_dosyasi)
    if ad.startswith("test_") and ad.endswith(".py") and len(ad) > len("test_.py"):
        ekle(os.path.join(scripts, ad[len("test_"):]), "ad_kurali")
    dizinler = [scripts, os.path.dirname(os.path.abspath(test_dosyasi)), kok]
    for modul in _yerel_importlar(test_dosyasi):
        parca = modul.split(".")
        for d in dizinler:
            for yol in (os.path.join(d, *parca) + ".py", os.path.join(d, *parca, "__init__.py")):
                if os.path.isfile(yol):
                    ekle(yol, "import")
    return adaylar


def _oturum_kayitlari(sd: str) -> list[tuple[str, dict, float]]:
    """(oturum kimliği, konum, mtime) listesi; bozuk/konumsuz kayıtlar atlanır."""
    sonuc = []
    try:
        girdiler = list(os.scandir(os.path.join(sd, "oturumlar")))
    except OSError:
        return []
    for e in girdiler:
        ad = e.name
        if not ad.endswith(".json") or ".baglanti" in ad or ad.startswith("acik_ajan_"):
            continue
        try:
            mtime = e.stat().st_mtime
            with open(e.path, encoding="utf-8") as f:
                kayit = json.load(f)
        except (OSError, ValueError):
            continue
        k = kayit.get("konum") if isinstance(kayit, dict) else None
        if isinstance(k, dict) and isinstance(k.get("yazilan"), list):
            sonuc.append((ad[:-5], k, mtime))
    return sonuc


def _zaman(konum: dict, mtime: float) -> float:
    try:
        return float(konum.get("gorulme") or 0) or mtime
    except (TypeError, ValueError):
        return mtime


def sahip_bul(sd: str, test_dosyasi: str, adaylar: list, simdi: float | None = None,
              esik_s: float = F.CANLI_S, test_adi: str | None = None) -> dict:
    """{test, sahip, kanit, canli}: sahip, test dosyasını ya da aday kaynaklarından birini `konum.yazilan`da taşıyan
    oturumdur. Önce kanıt gücü (test > ad_kurali > import), sonra en yeni yazan. Eşleşme yoksa sahip None (sahipsiz)."""
    t = time.time() if simdi is None else simdi
    test_n = _norm(test_dosyasi)
    hedef = {test_n: "test"}
    for a in adaylar or []:
        dosya, tur = (a.get("dosya"), a.get("tur", "import")) if isinstance(a, dict) else (a, "import")
        if isinstance(dosya, str):
            n = _norm(dosya)
            if n not in hedef:
                hedef[n] = tur if tur in GUC else "import"
    en_iyi = None  # (güç, -zaman, oturum, kanıt dosyası, zaman)
    for oturum, konum, mtime in _oturum_kayitlari(sd):
        yazilan = {_norm(x) for x in konum.get("yazilan") if isinstance(x, str)}
        eslesen = [d for d in hedef if d in yazilan]
        if not eslesen:
            continue
        kanit = min(eslesen, key=lambda d: GUC[hedef[d]])
        z = _zaman(konum, mtime)
        aday = (GUC[hedef[kanit]], -z, oturum, kanit, z)
        if en_iyi is None or aday[:3] < en_iyi[:3]:
            en_iyi = aday
    test = test_n + ("::" + test_adi if test_adi else "")
    if en_iyi is None:
        return {"test": test, "sahip": None, "kanit": None, "canli": False}
    return {"test": test, "sahip": en_iyi[2], "kanit": en_iyi[3], "canli": t - en_iyi[4] <= esik_s}


def atfet(cikti_metni, sd: str, eklenti_koku: str, kok: str | None = None, simdi: float | None = None) -> list[dict]:
    """Uçtan uca: çıktıdaki her düşen test için sahip_bul sonucu."""
    sonuc = []
    for d in dusenleri_ayikla(cikti_metni, kok):
        adaylar = kaynak_adaylari(d["test_dosyasi"], eklenti_koku)
        sonuc.append(sahip_bul(sd, d["test_dosyasi"], adaylar, simdi=simdi, test_adi=d["test_adi"]))
    return sonuc


def main(argv=None) -> int:
    """stdin: pytest çıktısı; argüman: <durum dizini> [eklenti kökü]. Çıktı: JSON liste."""
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print("kullanım: test_atif.py <durum_dizini> [eklenti_koku] < pytest_ciktisi")
        return 2
    kok = argv[1] if len(argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    print(json.dumps(atfet(sys.stdin.read(), argv[0], kok), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
