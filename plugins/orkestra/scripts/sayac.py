"""Tekrar eden iş sayacı: aynı iş her 5. kez yapıldığında toast bildirimi gönderir (skill avcısı eşiği).

Sayaç `<durum dizini>/sayac.json` dosyasında tutulur: {anahtar: {"sayi": N, "son_bildirilen": M}}.
Bildirim yalnız sayı 5'in yeni bir katına ulaşınca gider (5, 10, 15, …); aynı eşik iki kez bildirilmez.
Komut satırı (skill avcısı için): `python sayac.py artir "<iş adı>"`.
"""
from __future__ import annotations

import json
import os
import re
import sys

import ork_lib as L

ESIK = 5


def anahtar(*parcalar) -> str:
    """Parçaları küçük harfe, tek boşluğa ve 80 karaktere indirgeyen sayaç anahtarı."""
    s = re.sub(r"\s+", " ", " | ".join(str(p) for p in parcalar if p)).strip().lower()
    return s[:80]


def _oku(yol: str) -> dict:
    try:
        with open(yol, encoding="utf-8") as f:
            v = json.load(f)
        return v if isinstance(v, dict) else {}
    except (OSError, ValueError):
        return {}


def artir(sd: str, ad: str) -> int:
    """Anahtarın sayısını bir artırır; eşik katına ulaşıldıysa bildirim gönderir. Yeni sayıyı döner."""
    if not ad:
        return 0
    yol = os.path.join(sd, "sayac.json")
    veri = _oku(yol)
    kayit = veri.get(ad) or {"sayi": 0, "son_bildirilen": 0}
    kayit["sayi"] = int(kayit.get("sayi", 0)) + 1
    if kayit["sayi"] // ESIK > int(kayit.get("son_bildirilen", 0)) // ESIK:
        kayit["son_bildirilen"] = kayit["sayi"]
        import bildirim
        bildirim.gonder("Orkestra: tekrar eden iş",
                        f"{ad}: toplam {kayit['sayi']} kez yapıldı. Skill önerisi için perspektifi çalıştır.")
    veri[ad] = kayit
    L.atomik_yaz(yol, json.dumps(veri, ensure_ascii=False, indent=1))
    return kayit["sayi"]


def main(argv=None) -> int:
    a = list(sys.argv[1:] if argv is None else argv)
    if a == ["esik"]:
        print(ESIK)  # ajan metinleri sabit sayı yazmaz; eşik tek kaynaktan okunur
        return 0
    if len(a) < 2 or a[0] != "artir":
        print('kullanım: sayac.py artir "<iş adı>"', file=sys.stderr)
        return 2
    sd = L.durum_dizini(os.getcwd())
    if not sd:
        print("sayac: durum dizini yok", file=sys.stderr)
        return 1
    print(artir(sd, anahtar(" ".join(a[1:]))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
