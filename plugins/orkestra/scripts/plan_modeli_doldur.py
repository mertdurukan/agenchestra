"""Eski kartlara plan_modeli alanını yazar (I-058 P1).

Kullanım: py plan_modeli_doldur.py <durum_dizini>   (örn. <proje>/.claude/orkestra)

Eşleme: kartın 'oturum' id'sindeki ana ajan satırlarının (gorev boş ya da '-') maliyet.jsonl'de modele göre
toplam maliyeti en yüksek olan model. Bulunamazsa '-'. Betik okuduğu modeli yazar, filtrelemez.
Idempotent: plan_modeli dolu ve '-' dışı kart değişmez; '-' olan kart yalnız model bulunursa güncellenir.
"""
from __future__ import annotations

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ork_lib as L  # noqa: E402


def ana_ajan_modeli(satirlar: list[dict], oturum: str) -> str:
    """Oturumun ana ajan satırlarında maliyeti en yüksek model; yoksa '-'."""
    if not oturum or oturum == "-":
        return "-"
    toplam: dict[str, float] = {}
    for s in satirlar:
        if s.get("oturum") != oturum or not L.ana_ajan_satiri_mi(s):
            continue
        m = s.get("model")
        if not isinstance(m, str) or not m or m == "-":
            continue
        try:
            toplam[m] = toplam.get(m, 0.0) + float(s.get("maliyet_usd") or 0)
        except (TypeError, ValueError):
            continue
    return max(toplam.items(), key=lambda x: x[1])[0] if toplam else "-"


def plan_modeli_bul(sd: str, oturum: str) -> str:
    try:
        satirlar = L.maliyet_kayitlari(sd)
    except Exception:
        satirlar = []
    return ana_ajan_modeli(satirlar, oturum)


def doldur(sd: str) -> dict:
    ozet = {"toplam": 0, "dolduruldu": 0, "bulunamadi": 0, "bos": 0}
    d = os.path.join(sd, "gorevler")
    if not os.path.isdir(d):
        return ozet
    satirlar = L.maliyet_kayitlari(sd)
    for ad in sorted(os.listdir(d)):
        if not re.fullmatch(r"G-\d+\.json", ad):
            continue
        yol = os.path.join(d, ad)
        try:
            with open(yol, encoding="utf-8") as f:
                k = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(k, dict):
            continue
        ozet["toplam"] += 1
        mevcut = k.get("plan_modeli")
        if isinstance(mevcut, str) and mevcut and mevcut != "-":
            continue
        model = ana_ajan_modeli(satirlar, k.get("oturum"))
        if model != "-":
            ozet["dolduruldu"] += 1
        else:
            ozet["bulunamadi"] += 1
        if mevcut != model:
            k["plan_modeli"] = model
            L.atomik_yaz(yol, json.dumps(k, ensure_ascii=False, indent=2) + "\n")
    for ad in sorted(os.listdir(d)):
        if re.fullmatch(r"G-\d+\.json", ad):
            try:
                with open(os.path.join(d, ad), encoding="utf-8") as f:
                    k = json.load(f)
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(k, dict) and not k.get("plan_modeli"):
                ozet["bos"] += 1
    return ozet


def main(argv: list[str]) -> int:
    if len(argv) != 2 or not os.path.isdir(argv[1]):
        print("kullanım: plan_modeli_doldur.py <durum_dizini>", file=sys.stderr)
        return 2
    o = doldur(argv[1])
    print(f"toplam {o['toplam']}")
    print(f"dolduruldu {o['dolduruldu']}")
    print(f"bulunamadı {o['bulunamadi']}")
    print(f"plan_modeli boş: {o['bos']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
