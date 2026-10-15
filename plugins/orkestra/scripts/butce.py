"""Kart bütçesi: geçmişten taban ve çalışma anında kesme (BIC-1, BIC-3).

Tavan sırası: kartın kendi `butce.usd` alanı > geçmişten taban (sınıf × basamak, 2 × p90; kural_aday.butce_tavani,
grup en az 4 kart) > basamak varsayılanı. Harcama: tekilleştirilmiş maliyet defterinde karta yazılmış satırlar
(L.maliyet_kayitlari). `kart durum isleniyor` harcama tavana ulaşmışsa yeni ajanı başlatmaz (çıkış 7).
Koşmakta olan ajanın maliyeti bitişinde deftere düşer; kesme bir sonraki ajanda devreye girer.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ork_lib as L  # noqa: E402

# Grup verisi yetersizken basamak başına varsayılan tavan (USD). 15.10 ölçümü: T2 kartların çoğu < 1,5 $.
VARSAYILAN_TAVAN = {"T0": 1.0, "T1": 1.0, "T2": 3.0, "T3": 8.0, "T4": 12.0}


def _sinif(k: dict) -> str:
    import kural_aday
    return kural_aday.sinif_normal(k)


KAPALI = ("teslim", "onaylandi")
BASAMAKLAR = ("T0", "T1", "T2", "T3", "T4")


def taban(kartlar: list[dict], kayitlar: list[dict]) -> dict:
    """{(sınıf, basamak): {"tavan_usd", "n"}} — 2 × p90, grup ≥ 4 kart. Yalnız kapanmış ve harcaması olan kartlar:
    hiç koşmamış (0 $) kartlar p90'ı sıfıra çekip tavanı 0 yapmasın."""
    import kural_aday
    harcayan = {r.get("gorev") for r in kayitlar if float(r.get("maliyet_usd") or 0) > 0}
    kapali = [k for k in kartlar if k.get("durum") in KAPALI and k.get("id") in harcayan]
    out: dict = {}
    for g in kural_aday.butce_tavani(kapali, kayitlar):
        anahtar = (g["sinif"], g["basamak"])
        if anahtar not in out or g["tavan_usd"] > out[anahtar]["tavan_usd"]:
            out[anahtar] = {"tavan_usd": g["tavan_usd"], "n": g["n"]}
    return out


def _basamak(k: dict, ajan_tipi: str | None = None) -> str:
    """Kart basamağı ile çağıran işçinin basamağının büyüğü (workflow basamağı kartı değiştirmeden yükseltir)."""
    adaylar = [k.get("basamak") or "T2"]
    if ajan_tipi and ajan_tipi.startswith("orkestra:isci-t"):
        adaylar.append("T" + ajan_tipi[-1])
    return max((b for b in adaylar if b in BASAMAKLAR), key=BASAMAKLAR.index, default="T2")


def kart_tavani(k: dict, taban_: dict, ajan_tipi: str | None = None) -> tuple[float, str]:
    """Kartın butce.usd'si > max(geçmiş taban, basamak varsayılanı). Taban yalnız yukarı çeker: bütçe kaçak
    harcamayı keser, olağan işi durdurmaz."""
    b = (k.get("butce") or {}).get("usd")
    if isinstance(b, (int, float)) and b > 0:
        return float(b), "kart"
    bas = _basamak(k, ajan_tipi)
    varsayilan = VARSAYILAN_TAVAN.get(bas, 3.0)
    g = taban_.get((_sinif(k), bas))
    if g and g["tavan_usd"] > varsayilan:
        return float(g["tavan_usd"]), f"taban {bas} n={g['n']}"
    return varsayilan, f"varsayilan {bas}"


def kart_harcamasi(gid: str, kayitlar: list[dict]) -> float:
    return sum(float(r.get("maliyet_usd") or 0) for r in kayitlar if r.get("gorev") == gid)


def engel(sd: str, k: dict, ajan_tipi: str | None = None) -> str | None:
    """Harcama tavana ulaştıysa engel metni; yoksa None. Hata durumunda None (bütçe işi durdurmaz)."""
    try:
        kayitlar = L.maliyet_kayitlari(sd)
        harcama = kart_harcamasi(k["id"], kayitlar)
        if harcama <= 0:
            return None
        tavan, kaynak = kart_tavani(k, taban(L.kartlar(sd), kayitlar), ajan_tipi)
    except Exception:
        return None
    if harcama < tavan:
        return None
    return (f"kart bütçesi doldu: {harcama:.2f} $ ≥ tavan {tavan:.2f} $ ({kaynak}). Yeni ajan başlamaz; ana ajan "
            f"nedeni inceleyip kartı beklemede yapar ya da `orkestra kart butce {k['id']} --usd <yeni>` ile tavanı açar.")


def durum(sd: str, k: dict) -> dict:
    kayitlar = L.maliyet_kayitlari(sd)
    tavan, kaynak = kart_tavani(k, taban(L.kartlar(sd), kayitlar))
    return {"id": k["id"], "harcama_usd": round(kart_harcamasi(k["id"], kayitlar), 4), "tavan_usd": round(tavan, 4),
            "kaynak": kaynak}
