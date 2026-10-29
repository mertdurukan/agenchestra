"""Perspektif trend (P3): bu pencere (son `gun` gün) ile önceki pencerenin (ondan önceki `gun` gün) karşılaştırması.

`hesapla(sd, gun, simdi=None)` salt okunur; kpi, maliyet_anomali, perspektif_zaman ve perspektif_gunluk
ölçümlerini değiştirmeden iki pencereyle çağırır. Her ölçü: {simdi, onceki, delta, yon}.
yon: iyi | kotu | ayni | belirsiz. Önceki pencere boşsa (sayısal yaprakların hepsi 0/None) tümü belirsiz.
Anomali: maliyet_anomali yalnız alt sınır alır; önceki adet = calistir(2*gun) - calistir(gun) (yaklaşık).
"""
from __future__ import annotations

import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kpi as K  # noqa: E402
import maliyet_anomali as MA  # noqa: E402
import ork_lib as L  # noqa: E402
import perspektif_gunluk as PG  # noqa: E402
import perspektif_zaman as PZ  # noqa: E402

# Beklenti tablosu: ölçü adındaki parça -> istenen yön. Önce AZALMALI sınanır; eşleşme yoksa belirsiz.
ARTMALI = ("isabet", "kapanis", "dogrulanmis_basari")
AZALMALI = ("maliyet", "usd", "ret", "sure", "bekleme", "anomali", "ihlal", "hata", "token", "carpan",
            "golge", "atlandi", "p50", "p90", "p95", "yukselt")


def beklenti(ad: str):
    """'artmali' | 'azalmali' | None (bilinmeyen)."""
    a = ad.lower()
    # Kötü sayaçlar (ihlal, gölge, ret, hata...) önce sınanır: 'kural_ihlal.kapanis_atlandi' artmalı sayılmamalı.
    if any(t in a for t in AZALMALI):
        return "azalmali"
    if any(t in a for t in ARTMALI):
        return "artmali"
    return None


def yapraklar(obj, onek: str = "") -> dict:
    """İç içe sözlüklerdeki sayısal (bool hariç) ve None yaprakları 'a.b.c' anahtarıyla düzleştirir; listeler/dizgeler atlanır."""
    out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            yol = f"{onek}.{k}" if onek else str(k)
            if isinstance(v, dict):
                out.update(yapraklar(v, yol))
            elif v is None or (isinstance(v, (int, float)) and not isinstance(v, bool)):
                out[yol] = v
    return out


# Pencereden bağımsız (sabit) yapraklar boşluk sınamasına girmez: eşikler, skill envanteri, beklenen pay.
SABIT = ("esik", "skill", "beklenen")


def _bos(y: dict) -> bool:
    return not any(isinstance(v, (int, float)) and v != 0 and not any(t in ad for t in SABIT)
                   for ad, v in y.items())


def karsilastir(simdi: dict, onceki: dict) -> dict:
    """İki düz yaprak sözlüğünü {simdi, onceki, delta, yon} sözlüğüne çevirir."""
    bos = _bos(onceki)
    out = {}
    for ad in sorted(set(simdi) | set(onceki)):
        s, o = simdi.get(ad), onceki.get(ad)
        # Bir pencerede hiç görünmeyen sayaç anahtarı 0 sayılır; None (ölçülemedi) None kalır.
        if ad not in simdi:
            s = 0
        if ad not in onceki:
            o = 0
        delta = round(s - o, 6) if isinstance(s, (int, float)) and isinstance(o, (int, float)) else None
        b = beklenti(ad)
        if bos or delta is None or b is None:
            yon = "belirsiz"
        elif abs(delta) < 1e-9:
            yon = "ayni"
        elif (delta < 0) == (b == "azalmali"):
            yon = "iyi"
        else:
            yon = "kotu"
        out[ad] = {"simdi": s, "onceki": o, "delta": delta, "yon": yon}
    return out


def _anomali_say(sd: str, gun: int, simdi) -> dict:
    """{'anomali_toplam': n, 'anomali_K1': n, ...} son gun için."""
    liste = MA.calistir(sd, gun, simdi=simdi)
    say = {"anomali_toplam": len(liste)}
    for a in liste:
        k = "anomali_" + str(a.get("kural") or "?")
        say[k] = say.get(k, 0) + 1
    return say


def hesapla(sd: str, gun: int = 14, simdi=None) -> dict:
    simdi = simdi or datetime.datetime.now().astimezone()
    bas = L.gun_baslangici(gun, simdi)
    onc_bas = L.gun_baslangici(2 * gun, simdi)
    bit = simdi + datetime.timedelta(seconds=1)

    kpi_s = yapraklar(K.olcum(sd, aralik=(bas, bit)).get("genel"))
    kpi_o = yapraklar(K.olcum(sd, aralik=(onc_bas, bas)).get("genel"))

    an_s = _anomali_say(sd, gun, simdi)
    an_2 = _anomali_say(sd, 2 * gun, simdi)
    an_o = {k: max(an_2.get(k, 0) - an_s.get(k, 0), 0) for k in an_2}
    # Önceki pencerede veri yoksa anomali de boş sayılmasın diye yalnız sayımlar karşılaştırılır.

    def _pz(b, e):
        r = PZ.ozet(sd, b, e)
        y = yapraklar({"olcum": r.get("olcum"), "esik": r.get("esik")})
        y["anomali_adet"] = len(r.get("anomali") or [])
        return y

    zam_s, zam_o = _pz(bas, bit), _pz(onc_bas, bas)
    gun_s = yapraklar({k: v for k, v in PG.ozet(sd, bas, bit).items() if k != "pencere"})
    gun_o = yapraklar({k: v for k, v in PG.ozet(sd, onc_bas, bas).items() if k != "pencere"})

    return {
        "pencere": {"gun": gun, "simdi": [bas.isoformat(), bit.isoformat()],
                    "onceki": [onc_bas.isoformat(), bas.isoformat()]},
        "kpi": karsilastir(kpi_s, kpi_o),
        "anomali": karsilastir(an_s, an_o),
        "zaman": karsilastir(zam_s, zam_o),
        "gunluk": karsilastir(gun_s, gun_o),
    }


if __name__ == "__main__":
    import json
    print(json.dumps(hesapla(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 14), ensure_ascii=False, indent=1))
