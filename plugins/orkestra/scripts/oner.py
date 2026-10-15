"""orkestra oner: veriye dayali baslangic basamagi onerisi ve benzer kart uyarisi (G-075).

Yontem: 'en ucuz gecen model' (FrugalGPT/RouteLLM) + Beta(1,1) posterior ortalamasi + az veride k-NN (TF-IDF).
Salt okuma: durum klasorunden kart ve (tekillestirilmis) maliyet okur, hicbir sey yazmaz.
  basamak_oner(kartlar, kayitlar, sinif, metin='', min_n=5) -> {sinif, onerilen, gerekce, adaylar, benzer, uyarilar}
  benzer(kartlar, metin, k=5) -> [{id, baslik, basamak, ret_sayisi, nedenler, skor}]
CLI: oner.py basamak --sinif S [--metin M] [--json] [--min-n N] [--sd DIZIN]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ork_lib as L  # noqa: E402

KRITER_IPUCU = {
    "kapsam-eksik": "Her kabul kriterini tek tek, olculebilir ve ayri madde olarak yaz; kapsam disi kalan parca olmasin.",
    "sayi-tutarsiz": "Kriterlerde gecen sayilari (adet, esik, toplam) kaynagiyla birebir ver ve kanit komutunu belirt.",
    "kanit-yok": "Her kriter icin beklenen kaniti (dosya:satir, komut ciktisi, sayi) kriterin icine yaz.",
    "kriter-belirsiz": "Kriteri tek anlamli ve dogrulanabilir yaz; 'uygun', 'dogru' gibi belirsiz ifadelerden kacin.",
    "talimat-ihlali": "Yazma alani, test alani ve protokol kisitlarini kriter olarak acikca yaz.",
}


DURAK = frozenset({"ile", "icin", "ama", "gibi", "daha", "olan", "bir", "hem", "veya", "ise"})


def sinif_normal(s) -> str:
    if s is None:
        return "belirsiz"
    s = str(s).strip().lower()
    if s in ("", "-"):
        return "belirsiz"
    return "kod" if s == "kod-duzenleme" else s


def _ilk_karar(k):
    d = k.get("denetimler")
    if isinstance(d, list) and d and isinstance(d[0], dict):
        return d[0].get("karar")
    return None


def _kart_usd(kayitlar) -> dict:
    t: dict = {}
    for r in kayitlar or []:
        g = r.get("gorev")
        try:
            v = float(r.get("maliyet_usd") or 0)
        except (TypeError, ValueError):
            v = 0.0
        t[g] = t.get(g, 0.0) + v
    return t


def _tokenler(m: str) -> list:
    return [t for t in re.findall(r"[^\W_]+", (m or "").lower()) if len(t) >= 3 and t not in DURAK]


def _kart_metni(k) -> str:
    kr = k.get("kabul_kriterleri") or []
    if isinstance(kr, str):
        kr = [kr]
    return str(k.get("baslik") or "") + " " + " ".join(str(x) for x in kr)


def benzer(kartlar, metin, k=5) -> list:
    sorgu = _tokenler(metin)
    if not sorgu or not kartlar:
        return []
    belgeler = [_tokenler(_kart_metni(c)) for c in kartlar]
    n = len(belgeler)
    df: dict = {}
    for b in belgeler:
        for t in set(b):
            df[t] = df.get(t, 0) + 1

    def vek(tokenler):
        tf: dict = {}
        for t in tokenler:
            tf[t] = tf.get(t, 0) + 1
        return {t: c * (math.log((n + 1) / (df.get(t, 0) + 1)) + 1) for t, c in tf.items()}

    def kos(a, b):
        pay = sum(v * b[t] for t, v in a.items() if t in b)
        pa = math.sqrt(sum(v * v for v in a.values()))
        pb = math.sqrt(sum(v * v for v in b.values()))
        return pay / (pa * pb) if pa and pb else 0.0

    q = vek(sorgu)
    out = []
    for c, b in zip(kartlar, belgeler):
        skor = kos(q, vek(b))
        if skor <= 0:
            continue
        rets = [x for x in (c.get("denetimler") or []) if isinstance(x, dict) and x.get("karar") == "ret"]
        nedenler = []
        for x in rets:
            if x.get("neden") and x["neden"] not in nedenler:
                nedenler.append(x["neden"])
        out.append({"id": c.get("id"), "baslik": c.get("baslik"), "basamak": c.get("basamak"),
                    "ret_sayisi": len(rets), "nedenler": nedenler, "skor": round(skor, 6)})
    out.sort(key=lambda x: (-x["skor"], str(x["id"])))
    return out[:k]


def basamak_oner(kartlar, kayitlar, sinif, metin="", min_n=5) -> dict:
    sn = sinif_normal(sinif)
    usd = _kart_usd(kayitlar)
    gruplar: dict = {}
    for c in kartlar or []:
        if sinif_normal(c.get("sinif")) != sn:
            continue
        karar = _ilk_karar(c)
        if karar not in ("onay", "ret"):
            continue
        b = c.get("baslangic_basamak") or c.get("basamak")
        if not b:
            continue
        g = gruplar.setdefault(b, {"a": 0, "r": 0, "usd": 0.0})
        g["a" if karar == "onay" else "r"] += 1
        g["usd"] += usd.get(c.get("id"), 0.0)
    adaylar = []
    for b in sorted(gruplar):
        g = gruplar[b]
        n = g["a"] + g["r"]
        p = (g["a"] + 1) / (n + 2)
        ort = g["usd"] / n
        adaylar.append({"basamak": b, "n": n, "ilk_gecis_olasiligi": p, "ort_usd": ort, "beklenen_usd": ort / p})
    yeterli = [x for x in adaylar if x["n"] >= min_n]
    if yeterli:
        en = min(yeterli, key=lambda x: (x["beklenen_usd"], x["basamak"]))
        onerilen, gerekce = en["basamak"], "en-kucuk-beklenen-usd"
    else:
        onerilen, gerekce = "T2", "yetersiz-veri"
    bz = benzer(kartlar, metin) if (metin or "").strip() else []
    uyarilar = []
    for x in bz:
        for kod in x["nedenler"]:
            ip = KRITER_IPUCU.get(kod)
            if ip and ip not in uyarilar:
                uyarilar.append(ip)
    return {"sinif": sn, "onerilen": onerilen, "gerekce": gerekce, "adaylar": adaylar,
            "benzer": bz, "uyarilar": uyarilar}


def _duz(s: dict) -> str:
    sat = [f"sinif={s['sinif']}  onerilen={s['onerilen']}  gerekce={s['gerekce']}"]
    for a in s["adaylar"][:6]:
        sat.append(f"  {a['basamak']}: n={a['n']} P={a['ilk_gecis_olasiligi']:.2f} "
                   f"ort=${a['ort_usd']:.4f} beklenen=${a['beklenen_usd']:.4f}")
    for b in s["benzer"][:3]:
        sat.append(f"  benzer {b['id']} ({b['basamak']}, ret={b['ret_sayisi']}, skor={b['skor']:.2f}) {str(b['baslik'])[:50]}")
    for u in s["uyarilar"][:3]:
        sat.append(f"  ! {u}")
    return "\n".join(sat[:15])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="oner")
    sp = ap.add_subparsers(dest="komut", required=True)
    b = sp.add_parser("basamak")
    b.add_argument("--sinif", default="")
    b.add_argument("--metin", default="")
    b.add_argument("--json", action="store_true")
    b.add_argument("--min-n", type=int, default=5)
    b.add_argument("--sd", default=None)
    a = ap.parse_args(argv)
    sd = a.sd or L.durum_dizini()
    if not sd:
        print("durum klasoru yok", file=sys.stderr)
        return 1
    s = basamak_oner(L.kartlar(sd), L.maliyet_kayitlari(sd), a.sinif, a.metin, a.min_n)
    print(json.dumps(s, ensure_ascii=False, indent=2) if a.json else _duz(s))
    return 0


if __name__ == "__main__":
    sys.exit(main())
