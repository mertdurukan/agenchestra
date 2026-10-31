"""Perspektif girdisi: günlük, hata, atıf, kart ve maliyet kayıtlarından mekanik özet (LLM'siz).

`ozet(sd, baslangic, bitis)` durum dizinindeki defterleri zaman penceresinde sayar; listeler kısadır (en çok 10).
Yalnız okur; yazmaz. Projeye özgü ad içermez (ADR-0094).
"""
import collections
import datetime
import glob
import json
import os

import ork_lib as L

VARSAYILAN_GUN = 14
EN_COK = 10


def _pencere(baslangic, bitis):
    """(baslangic, bitis) -> ISO dizge çifti; None ise son 14 gün / sınırsız. datetime ya da ISO dizge kabul edilir."""
    def _s(v):
        return v.isoformat() if isinstance(v, (datetime.datetime, datetime.date)) else v
    if baslangic is None:
        baslangic = (datetime.datetime.now().astimezone() - datetime.timedelta(days=VARSAYILAN_GUN)).isoformat()
    return _s(baslangic), _s(bitis)


def _icinde(zaman, b, s) -> bool:
    z = str(zaman or "")
    return bool(z) and z >= b and (s is None or z <= s)


def _oku(sd, ad, b, s):
    return [r for r in L.jsonl_oku(os.path.join(sd, ad)) if isinstance(r, dict) and _icinde(r.get("zaman"), b, s)]


def _yuzdelik(v, p):
    if not v:
        return None
    v = sorted(v)
    return v[min(len(v) - 1, int(round(p * (len(v) - 1))))]


def _skiller(sd):
    proje = os.path.dirname(os.path.dirname(os.path.abspath(sd)))
    kokler = [os.path.join(proje, ".claude", "skills"),
              os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skills")]
    return sorted({os.path.basename(os.path.dirname(y)) for k in kokler for y in glob.glob(os.path.join(k, "*", "SKILL.md"))})


def _yukselen(sd, b, s) -> int:
    n = 0
    for yol in glob.glob(os.path.join(sd, "gorevler", "G-*.json")):
        if yol.endswith(".denetim.json"):
            continue
        try:
            with open(yol, encoding="utf-8") as f:
                kart = json.load(f)
        except (OSError, ValueError):
            continue
        gecmis = kart.get("gecmis") if isinstance(kart, dict) else None
        if isinstance(gecmis, list) and any(isinstance(e, dict) and str(e.get("olay", "")).startswith("yukselt")
                                            and _icinde(e.get("zaman"), b, s) for e in gecmis):
            n += 1
    return n


def _ilk(sayac, n=EN_COK):
    return dict(sayac.most_common(n))


def _olay(sd, b, s) -> dict:
    """Olay kaydı özeti (I-286): tür ve sonuç adetleri; okuyucu hata verirse boş bölüm, perspektif bozulmaz."""
    try:
        import olay_kaydi
        o = [x for x in olay_kaydi.oku_sd(sd) if _icinde(x.get("zaman"), b, s)]
        s: dict = {}
        for x in o:
            s[x["sonuc"]] = s.get(x["sonuc"], 0) + 1
        return {"toplam": len(o), "tur": olay_kaydi.tur_adetleri(o), "sonuc": s}
    except Exception:  # noqa: BLE001
        return {}


def ozet(sd, baslangic=None, bitis=None) -> dict:
    b, s = _pencere(baslangic, bitis)
    gun = _oku(sd, "gunluk.jsonl", b, s)
    tur = lambda t: [r for r in gun if r.get("tur") == t]  # noqa: E731

    golge = collections.Counter(r.get("kapi") or "?" for r in tur("kapi_golge"))
    ret = tur("kapi_ret")
    ret_say = collections.Counter(r.get("kapi") or "?" for r in ret)
    neden = collections.Counter((r.get("kapi") or "?", str(r.get("neden") or "")[:60]) for r in ret)
    ret_nedenleri = [{"kapi": k, "neden": n, "n": c} for (k, n), c in neden.most_common(EN_COK)]
    cift = collections.Counter((r.get("is"), r.get("kapi")) for r in ret if r.get("is"))
    uc = sum(1 for v in cift.values() if v >= 3)
    tekrar = {"cift": len(cift), "uc_ve_ustu": uc, "pay": round(uc / len(cift), 4) if cift else 0.0}

    ihlal = tur("kural_ihlal")
    kural_ihlal = _ilk(collections.Counter(r.get("kural") or "?" for r in ihlal), 50)
    ihlal_mod = dict(collections.Counter(r.get("mod") or "?" for r in ihlal))

    olc = tur("cikti_olcum")
    toplam = [r["toplam"] for r in olc if isinstance(r.get("toplam"), (int, float))]
    kapanis = sum(1 for r in olc if isinstance(r.get("kapanis"), (int, float)))
    cikti = {"adet": len(olc), "p50": _yuzdelik(toplam, 0.5), "p95": _yuzdelik(toplam, 0.95),
             "kapanis_orani": round(kapanis / len(olc), 4) if olc else 0.0}

    hata = _oku(sd, "hata.jsonl", b, s)
    hata_sinif = collections.Counter(r.get("sinif") or "?" for r in hata)
    hata_kok = collections.Counter(((r.get("kok") or {}).get("kaynak") if isinstance(r.get("kok"), dict) else None) or "?"
                                   for r in hata)
    atif = collections.Counter(r.get("kaynak") or "?" for r in _oku(sd, "atif.jsonl", b, s))

    kullanilan = {str(r.get("skill") or "").split(":")[-1] for r in tur("skill")}
    kullanilmayan = [x for x in _skiller(sd) if x not in kullanilan]

    topl = den = 0.0
    for r in _oku(sd, "maliyet.jsonl", b, s):
        m = r.get("maliyet_usd")
        if isinstance(m, (int, float)):
            topl += m
            if r.get("surec") == "denetim":
                den += m
    return {
        "pencere": {"baslangic": b, "bitis": s},
        "kapi_golge": dict(golge), "kapi_ret": dict(ret_say), "ret_nedenleri": ret_nedenleri,
        "tekrarlayan_ret": tekrar,
        "kural_ihlal": kural_ihlal, "kural_ihlal_mod": ihlal_mod,
        "cikti_olcum": cikti,
        "hook_hatasi": len(tur("hook-hatasi")), "sikistirma": len(tur("sikistirma")),
        "hata": {"sinif": dict(hata_sinif), "kok": _ilk(hata_kok)},
        "atif": dict(atif),
        "kullanilmayan_skill": kullanilmayan[:EN_COK * 5], "kullanilmayan_skill_adet": len(kullanilmayan),
        "yukseltilen_kart": _yukselen(sd, b, s),
        "denetim_payi": round(den / topl, 4) if topl else 0.0,
        "olay": _olay(sd, b, s),
    }
