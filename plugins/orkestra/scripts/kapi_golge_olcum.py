"""Yapısal seçim kapısının gölge kayıtlarını transkriptle eşleyip yeni tetik mantığıyla yeniden sınıflar (I-284, P4).

Salt okuma, model çağırmaz. Her `kural_ihlal / secim_ekrani_yapisal` kaydı için oturum transkriptinde kaydın zamanına en yakın
ve ondan önceki asistan satırı bulunur, transkript o satıra kadar kesilir ve `secim_ekrani_hatirlatma.yapisal_tetik` yeniden
koşulur. Çıktı: eski tetik ve yeni tetik dağılımı, gerçek ihlal (`ask_butonsuz`, `teklif_sonu`) oranı.

Döngüsellik uyarısı: sınıflama kapının kendi sinyalleriyle yapılır; sonuçlar örnek turların elle doğrulanmasıyla birlikte
okunur (`--ornek N` her sınıftan N turun son metnini yazar).

Kullanım: python kapi_golge_olcum.py <gunluk.jsonl> [--transkript-kok DİZİN] [--ornek N] [--esik 0.10]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import secim_ekrani_hatirlatma as SH  # noqa: E402

KURAL = "secim_ekrani_yapisal"
IHLAL_TETIKLERI = ("ask_butonsuz", "teklif_sonu")


def _utc(zaman: str) -> datetime:
    return datetime.fromisoformat(zaman).astimezone(timezone.utc)


def kayitlar(gunluk: str) -> list:
    """Günlükteki yapısal kapı ihlal kayıtları."""
    sonuc = []
    with open(gunluk, encoding="utf-8") as f:
        for s in f:
            try:
                o = json.loads(s)
            except Exception:
                continue
            if isinstance(o, dict) and o.get("tur") == "kural_ihlal" and o.get("kural") == KURAL and o.get("zaman"):
                sonuc.append(o)
    return sonuc


def transkript_bul(kok: str, oturum: str):
    yollar = glob.glob(os.path.join(kok, "*", f"{oturum}.jsonl"))
    return yollar[0] if yollar else None


def tur_kesiti(yol: str, an: datetime):
    """(kesilmiş satırlar, son asistan metni) ya da None: `an`dan önceki son asistan satırına kadar."""
    with open(yol, encoding="utf-8", errors="replace") as f:
        satirlar = f.read().splitlines()
    son = None
    for i, ham in enumerate(satirlar):
        try:
            o = json.loads(ham)
        except Exception:
            continue
        zt = o.get("timestamp") if isinstance(o, dict) else None
        if isinstance(o, dict) and o.get("type") == "assistant" and zt:
            try:
                if datetime.fromisoformat(zt.replace("Z", "+00:00")) <= an:
                    son = i
            except ValueError:
                continue
    if son is None:
        return None
    metin = ""
    for ham in reversed(satirlar[: son + 1]):
        try:
            o = json.loads(ham)
        except Exception:
            continue
        if isinstance(o, dict) and o.get("type") == "assistant":
            ic = (o.get("message") or {}).get("content")
            m = " ".join(b.get("text", "") for b in ic if isinstance(b, dict) and b.get("type") == "text") if isinstance(ic, list) else ""
            if m.strip():
                metin = m
                break
    return satirlar[: son + 1], metin


def yeniden_sinifla(satirlar: list, metin: str, sd=None) -> str:
    with tempfile.TemporaryDirectory() as t:
        yol = os.path.join(t, "kesit.jsonl")
        with open(yol, "w", encoding="utf-8") as f:
            f.write("\n".join(satirlar) + "\n")
        return SH.yapisal_tetik(yol, metin, sd) or "-"


def olc(gunluk: str, kok: str, sd=None, ornek: int = 0) -> dict:
    eski, yeni, bulunamadi, ornekler = Counter(), Counter(), 0, {}
    for k in kayitlar(gunluk):
        yol = transkript_bul(kok, k.get("oturum", ""))
        kesit = tur_kesiti(yol, _utc(k["zaman"])) if yol else None
        if not kesit:
            bulunamadi += 1
            continue
        satirlar, metin = kesit
        e, y = k.get("tetik") or "(eski)", yeniden_sinifla(satirlar, metin, sd)
        eski[e] += 1
        yeni[y] += 1
        if ornek and len(ornekler.setdefault(y, [])) < ornek:
            ornekler[y].append({"oturum": k.get("oturum"), "zaman": k["zaman"], "son_metin": metin[-200:]})
    toplam = sum(yeni.values())
    ihlal = sum(yeni[t] for t in IHLAL_TETIKLERI)
    return {"toplam": toplam, "bulunamadi": bulunamadi, "eski_tetik": dict(eski), "yeni_tetik": dict(yeni),
            "gercek_ihlal": ihlal, "gercek_ihlal_orani": round(ihlal / toplam, 3) if toplam else None, "ornekler": ornekler}


def esik_raporu(sonuc: dict, esik: float) -> str:
    """Eski kayıtların yeni mantıkla ihlal kalmayan payı (yanlış pozitif azalması)."""
    toplam = sonuc["toplam"]
    if not toplam:
        return "ölçülecek kayıt yok"
    yp = 1 - (sonuc["gercek_ihlal"] / toplam)
    return (f"eski kayıtların {yp:.0%}'i yeni mantıkla ihlal değil "
            f"(hedef: gölge penceresinde yanlış pozitif <= {esik:.0%}, 7 gün, en az 30 tur)")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("gunluk")
    ap.add_argument("--transkript-kok", default=os.path.join(os.path.expanduser("~"), ".claude", "projects"))
    ap.add_argument("--ornek", type=int, default=0)
    ap.add_argument("--esik", type=float, default=0.10)
    a = ap.parse_args(argv)
    sonuc = olc(a.gunluk, a.transkript_kok, os.path.dirname(os.path.abspath(a.gunluk)), a.ornek)
    print(json.dumps(sonuc, ensure_ascii=False, indent=2))
    print(esik_raporu(sonuc, a.esik))
    return 0


if __name__ == "__main__":
    sys.exit(main())
