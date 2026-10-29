"""Perspektif zaman maliyeti ozeti ve zaman anomali kurallari (K8-K10). Salt okuma, model cagirmaz.

ozet(sd, baslangic, bitis) zaman.jsonl, gunluk.jsonl ve isler.json dosyalarindan sure olcumu ve anomali listesi doner.
Kurallar: K8 uzun-tur (ana tur suresi esigi asan pay), K9 oturum-maraton (oturum suresi esigi asan pay),
K10 is-surunme (acik is guncelleme >= surunme_gun). Esik = onceki pencerenin p95 degeri; onceki pencerede ornek
< min_n ise ayarlar/perspektif_zaman.json tabani. Sir ve istem metni ciktiya girmez (yalniz sayi ve kimlik).
"""
from __future__ import annotations

import datetime
import json
import math
import os

AYAR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ayarlar", "perspektif_zaman.json")
VARSAYILAN = {"uzun_tur_sn": 1800, "oturum_sn": 14400, "surunme_gun": 7, "beklenen_pay": 0.05,
              "anomali_pay": 0.10, "min_n": 30, "varsayilan_gun": 14, "uzun_tur_liste": 10}


def ayar() -> dict:
    a = dict(VARSAYILAN)
    try:
        with open(AYAR, encoding="utf-8") as f:
            a.update({k: v for k, v in json.load(f).items() if not k.startswith("_")})
    except (OSError, ValueError):
        pass
    return a


def _zaman(v) -> datetime.datetime | None:
    if isinstance(v, datetime.datetime):
        d = v
    elif isinstance(v, str) and v:
        try:
            d = datetime.datetime.fromisoformat(v.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    return d if d.tzinfo else d.replace(tzinfo=datetime.timezone.utc)


def p_nr(degerler, p: float):
    """Nearest-rank yuzdelik: sirali listede ceil(p/100*n). Bos liste None."""
    s = sorted(degerler)
    if not s:
        return None
    return s[max(1, math.ceil(p / 100 * len(s))) - 1]


def _jsonl(yol: str):
    try:
        with open(yol, encoding="utf-8") as f:
            for satir in f:
                try:
                    o = json.loads(satir)
                except ValueError:
                    continue
                if isinstance(o, dict):
                    yield o
    except OSError:
        return


def _yukle(sd: str) -> dict:
    """Ham kayitlar: ana/alt turlar (bitis, sure sn, is, oturum), oturum basina [ilk, son] zaman, acik isler."""
    turlar, oturum = [], {}

    def _isle(o, bit, bas):
        s = o.get("oturum")
        if not s or bit is None:
            return
        a, b = oturum.get(s, (bas or bit, bit))
        oturum[s] = (min(a, bas or bit), max(b, bit))

    for o in _jsonl(os.path.join(sd, "zaman.jsonl")):
        bit = _zaman(o.get("zaman"))
        try:
            sure = float(o.get("sure_ms")) / 1000.0
        except (TypeError, ValueError):
            sure = None
        if bit is not None and sure is not None and o.get("tur") in ("ana", "alt"):
            turlar.append({"tur": o["tur"], "bit": bit, "sure": sure, "is": o.get("is"), "oturum": o.get("oturum")})
        _isle(o, bit, bit - datetime.timedelta(seconds=sure) if (bit and sure is not None) else None)
    for o in _jsonl(os.path.join(sd, "gunluk.jsonl")):
        t = _zaman(o.get("zaman"))
        _isle(o, t, t)
    isler = []
    try:
        with open(os.path.join(sd, "isler.json"), encoding="utf-8") as f:
            kayit = (json.load(f) or {}).get("isler") or {}
    except (OSError, ValueError):
        kayit = {}
    for iid, v in kayit.items():
        if not isinstance(v, dict) or v.get("durum") != "acik":
            continue
        g = None
        try:
            with open(os.path.join(v.get("klasor") or "", "is.json"), encoding="utf-8") as f:
                g = _zaman((json.load(f) or {}).get("guncelleme"))
        except (OSError, ValueError, TypeError):
            pass
        g = g or _zaman(v.get("olusturma"))
        if g is not None:
            isler.append({"id": iid, "guncelleme": g})
    return {"turlar": turlar, "oturum": oturum, "isler": isler}


def _ozet_say(vals, pler):
    r = {"adet": len(vals)}
    for p in pler:
        r["p%d" % p] = p_nr(vals, p)
    return r


def _esik(vals, taban, min_n):
    """(esik, kaynak): ornek >= min_n ise onceki pencerenin p95 degeri, degilse taban."""
    if len(vals) >= min_n:
        return p_nr(vals, 95), "onceki_pencere_p95"
    return taban, "taban"


def _pencere(v: dict, bas, bit):
    ana = [t for t in v["turlar"] if t["tur"] == "ana" and bas <= t["bit"] < bit]
    alt = [t for t in v["turlar"] if t["tur"] == "alt" and bas <= t["bit"] < bit]
    otr = {s: (b - a).total_seconds() for s, (a, b) in v["oturum"].items() if bas <= b < bit}
    return ana, alt, otr


def _pay_kural(kural, ad, hedef, vals, esik, a, ayrinti):
    n = len(vals)
    if not n:
        return None, None
    pay = sum(1 for x in vals if x > esik) / n
    if n >= a["min_n"] and pay > a["anomali_pay"]:
        return {"kural": kural, "ad": ad, "hedef": hedef, "ayrinti": ayrinti % (round(esik), round(pay * 100)),
                "deger": round(pay, 4), "pay": round(pay, 4), "beklenen_pay": a["beklenen_pay"], "n": n}, pay
    return None, pay


def _hesapla(v: dict, bas, bit, a: dict) -> dict:
    sure = bit - bas
    ana, alt, otr = _pencere(v, bas, bit)
    onc_ana, _, onc_otr = _pencere(v, bas - sure, bas)
    tur_esik, tur_kay = _esik([t["sure"] for t in onc_ana], a["uzun_tur_sn"], a["min_n"])
    otr_esik, otr_kay = _esik(list(onc_otr.values()), a["oturum_sn"], a["min_n"])
    ana_s = [t["sure"] for t in ana]
    otr_s = list(otr.values())
    k8, pay8 = _pay_kural("K8", "uzun-tur", "ana_tur", ana_s, tur_esik, a,
                          "ana tur suresi esigi (%d sn) asan pay %%%d")
    k9, pay9 = _pay_kural("K9", "oturum-maraton", "oturum", otr_s, otr_esik, a,
                          "oturum suresi esigi (%d sn) asan pay %%%d")
    anomali = [k for k in (k8, k9) if k]
    yaslar = [(bit - i["guncelleme"]).total_seconds() / 86400 for i in v["isler"] if i["guncelleme"] <= bit]
    for i in v["isler"]:
        gun = (bit - i["guncelleme"]).total_seconds() / 86400
        if gun >= a["surunme_gun"]:
            anomali.append({"kural": "K10", "ad": "is-surunme", "hedef": i["id"],
                            "ayrinti": "acik is %d gundur guncellenmedi" % int(gun), "deger": round(gun, 1),
                            "pay": None, "beklenen_pay": None, "n": 1})
    surunen = sum(1 for g in yaslar if g >= a["surunme_gun"])
    uzun = sorted((t for t in ana if t["sure"] > tur_esik), key=lambda t: -t["sure"])[: a["uzun_tur_liste"]]
    p50g = p_nr(yaslar, 50)
    return {
        "olcum": {
            "ana_tur": _ozet_say(ana_s, (50, 90, 95)),
            "alt_tur": _ozet_say([t["sure"] for t in alt], (50, 95)),
            "oturum": _ozet_say(otr_s, (50, 95)),
            "is": {"acik": len(yaslar), "surunen_7gun": surunen,
                   "p50_gun": round(p50g, 1) if p50g is not None else None},
            "uzun_turlar": [{"is": t["is"], "oturum": t["oturum"], "sure_sn": round(t["sure"])} for t in uzun],
        },
        "anomali": anomali,
        "esik": {"uzun_tur_sn": tur_esik, "uzun_tur_kaynak": tur_kay, "oturum_sn": otr_esik,
                 "oturum_kaynak": otr_kay, "surunme_gun": a["surunme_gun"], "beklenen_pay": a["beklenen_pay"],
                 "anomali_pay": a["anomali_pay"], "min_n": a["min_n"]},
        "_pay": {"K8": pay8, "K9": pay9},
    }


def ozet(sd: str, baslangic=None, bitis=None) -> dict:
    a = ayar()
    bit = _zaman(bitis) or datetime.datetime.now(datetime.timezone.utc)
    bas = _zaman(baslangic) or bit - datetime.timedelta(days=a["varsayilan_gun"])
    r = _hesapla(_yukle(sd), bas, bit, a)
    r.pop("_pay")
    return r


def pencere_raporu(sd: str, gun: int = 14, adet: int = 2, simdi=None) -> list[dict]:
    """Son adet pencere (en yeni once): K8/K9 pay, beklenen_pay, n, anomali adedi."""
    a = ayar()
    son = _zaman(simdi) or datetime.datetime.now(datetime.timezone.utc)
    v = _yukle(sd)
    out = []
    for i in range(adet):
        bit = son - datetime.timedelta(days=gun * i)
        bas = bit - datetime.timedelta(days=gun)
        r = _hesapla(v, bas, bit, a)
        satir = {"pencere": [bas.isoformat(), bit.isoformat()], "beklenen_pay": a["beklenen_pay"],
                 "anomali": len(r["anomali"])}
        for k, n in (("K8", r["olcum"]["ana_tur"]["adet"]), ("K9", r["olcum"]["oturum"]["adet"])):
            p = r["_pay"][k]
            satir[k] = {"pay": round(p, 4) if p is not None else None, "beklenen_pay": a["beklenen_pay"], "n": n,
                        "anomali": sum(1 for x in r["anomali"] if x["kural"] == k)}
        out.append(satir)
    return out
