"""Yol notu gölge ölçümü (I-273, ADR-0103): gunluk.jsonl `yol_notu` kayıtlarını sayar ve A/B puanlamasından karar satırı üretir.

Puanlama dosyası (JSONL): her satır {"kol": "acik"|"kapali", "kacirilan": 0|1}; `kacirilan` = yanıtın atladığı mevcut
araç ya da kaynak var mı (yanıtı üretenden ayrı, kolu bilmeyen orkestra:denetci puanlar). Model çağrılmaz.

Karar: kol başına en az `MIN_N` soru; not açık kolda oran kapalı koldan en az `ESIK_PUAN` puan düşük ve fark için %95
aralığın (Wald) üst sınırı 0'ın altında ise ihlal moduna geçiş adayı; değilse gölgede kal.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys

MIN_N = 80
ESIK_PUAN = 20.0
Z95 = 1.96


def yol_notu_say(gunluk_yolu: str) -> int:
    n = 0
    try:
        with open(gunluk_yolu, encoding="utf-8") as f:
            for s in f:
                try:
                    if json.loads(s).get("tur") == "yol_notu":
                        n += 1
                except ValueError:
                    continue
    except OSError:
        return 0
    return n


def puanlari_oku(yol: str) -> dict:
    kol = {"acik": [0, 0], "kapali": [0, 0]}  # [n, kacirilan]
    with open(yol, encoding="utf-8") as f:
        for s in f:
            try:
                k = json.loads(s)
            except ValueError:
                continue
            a = kol.get(k.get("kol"))
            if a is not None and k.get("kacirilan") in (0, 1):
                a[0] += 1
                a[1] += k["kacirilan"]
    return kol


def rapor(kol: dict, yol_notu_adet: int = 0) -> dict:
    (na, ka), (nk, kk) = kol["acik"], kol["kapali"]
    ra = ka / na if na else 0.0
    rk = kk / nk if nk else 0.0
    fark = round((rk - ra) * 100, 6)  # pozitif: not açıkken daha az kaçırma
    se = math.sqrt(ra * (1 - ra) / na + rk * (1 - rk) / nk) * 100 if na and nk else 0.0
    alt, ust = fark - Z95 * se, fark + Z95 * se
    yeterli = na >= MIN_N and nk >= MIN_N
    aday = yeterli and fark >= ESIK_PUAN and alt > 0
    if not yeterli:
        karar = f"yetersiz örnek (kol başına en az {MIN_N}): gölgede kal"
    elif aday:
        karar = "ihlal moduna geçiş için aday (ayrı karar ve yeni ADR gerekir)"
    else:
        karar = "gölgede kal"
    return {"yol_notu_adet": yol_notu_adet, "n_acik": na, "n_kapali": nk, "oran_acik": round(ra, 4),
            "oran_kapali": round(rk, 4), "fark_puan": round(fark, 2), "aralik95_puan": [round(alt, 2), round(ust, 2)],
            "esik_puan": ESIK_PUAN, "karar": karar}


def metin(r: dict) -> str:
    return "\n".join([
        f"yol_notu kayıt sayısı: {r['yol_notu_adet']}",
        f"kol başına n: açık {r['n_acik']}, kapalı {r['n_kapali']} (en az {MIN_N})",
        f"kaçırılan oranı: açık {r['oran_acik']:.1%}, kapalı {r['oran_kapali']:.1%}",
        f"fark: {r['fark_puan']} puan, %95 aralık {r['aralik95_puan']} (eşik {r['esik_puan']} puan)",
        f"karar: {r['karar']}"])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--gunluk", default="", help="gunluk.jsonl yolu (yol_notu kayıtlarını sayar)")
    ap.add_argument("--puanlar", required=True, help="puanlama JSONL dosyası")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if not os.path.exists(a.puanlar):
        print(f"puanlama dosyası yok: {a.puanlar}", file=sys.stderr)
        return 2
    r = rapor(puanlari_oku(a.puanlar), yol_notu_say(a.gunluk) if a.gunluk else 0)
    print(json.dumps(r, ensure_ascii=False, indent=2) if a.json else metin(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
