"""Etkin süre (I-259): ana tur süresinden kullanıcı beklemesini ayırır.

Tanım (I-257 ölçümüyle aynı): tur süresi `esik_dk` dakikayı aşarsa tur bekleme sayılır, etkin süre 0'dır;
aksi halde etkin süre ham süreye eşittir. Eşik `ayarlar/zaman_etkin.json` `esik_dk` değeridir (varsayılan 120);
proje ezmesi durum klasöründeki `zaman_etkin.json` önceliklidir. Hata ayarı varsayılana düşürür.
"""
from __future__ import annotations

import json
import os

VARSAYILAN_ESIK_DK = 120.0


def esik_dk(sd: str | None = None) -> float:
    kok = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    yollar = [os.path.join(kok, "ayarlar", "zaman_etkin.json")]
    if sd:
        yollar.append(os.path.join(sd, "zaman_etkin.json"))
    sonuc = VARSAYILAN_ESIK_DK
    for yol in yollar:
        try:
            with open(yol, encoding="utf-8") as f:
                d = json.load(f)
            v = d.get("esik_dk") if isinstance(d, dict) else None
            if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0:
                sonuc = float(v)
        except (OSError, ValueError):
            pass
    return sonuc


def etkin_ms(sure_ms, sd: str | None = None, esik: float | None = None) -> int | None:
    """Ham süre (ms) -> etkin süre (ms). Ham süre yoksa None."""
    if not isinstance(sure_ms, (int, float)) or isinstance(sure_ms, bool):
        return None
    esik = esik_dk(sd) if esik is None else esik
    return int(sure_ms) if sure_ms / 60000 <= esik else 0
