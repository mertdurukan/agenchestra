"""orkestra oner: veriye dayali baslangic basamagi onerisi ve benzer kart uyarisi (G-075).

Yontem: 'en ucuz gecen model' (FrugalGPT/RouteLLM) + Beta posterior %20 alt siniri (min_n ve usd_fark politikadan) + az veride k-NN (TF-IDF).
Salt okuma: durum klasorunden kart ve (tekillestirilmis) maliyet okur, hicbir sey yazmaz.
  basamak_oner(kartlar, kayitlar, sinif, metin='', min_n=None, usd_fark=None) -> {sinif, onerilen, gerekce, adaylar, benzer, uyarilar}
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


def _kart_token(kayitlar) -> dict:
    """{kart: dört kalemin ham token toplamı} — USD kıyasının token eşi (I-064)."""
    t: dict = {}
    for r in kayitlar or []:
        g = r.get("gorev")
        t[g] = t.get(g, 0) + sum(int(r.get(a) or 0) for a in L._TOKEN_ALANLARI)
    return t


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


VARSAYILAN_MIN_N = 20
VARSAYILAN_USD_FARK = 0.10
ALT_SINIR_KUANTIL = 0.20


def politika() -> dict:
    """karar.min_n / karar.usd_fark: model_politika.yukle() ya da ayarlar/model_politikasi.json; yoksa varsayilan."""
    out = {"min_n": VARSAYILAN_MIN_N, "usd_fark": VARSAYILAN_USD_FARK}
    karar = None
    try:
        import model_politika  # noqa: E402
        p = model_politika.yukle()
        karar = (p or {}).get("karar") if isinstance(p, dict) else None
    except Exception:
        karar = None
    if not isinstance(karar, dict):
        try:
            yol = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ayarlar", "model_politikasi.json")
            with open(yol, encoding="utf-8") as f:
                karar = (json.load(f) or {}).get("karar")
        except Exception:
            karar = None
    if isinstance(karar, dict):
        try:
            if int(karar.get("min_n")) > 0:
                out["min_n"] = int(karar["min_n"])
        except (TypeError, ValueError):
            pass
        try:
            if float(karar.get("usd_fark")) >= 0:
                out["usd_fark"] = float(karar["usd_fark"])
        except (TypeError, ValueError):
            pass
    return out


def alt_sinir(a: int, r: int, q: float = ALT_SINIR_KUANTIL) -> float:
    """Beta(a+1, r+1) posteriorunun q kuantili. Tamsayi parametrede CDF = P(Binom(a+r+1, x) >= a+1); ikili aramayla ters."""
    ap, bp = a + 1, r + 1
    m = ap + bp - 1

    def cdf(x):
        return sum(math.comb(m, j) * x ** j * (1 - x) ** (m - j) for j in range(ap, m + 1))

    lo, hi = 0.0, 1.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if cdf(mid) > q:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def _t(s):
    if not s:
        return None
    try:
        import datetime
        z = datetime.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return (z if z.tzinfo else z.astimezone()).astimezone()
    except Exception:
        return None


def _kart_dk(k):
    """olusturma -> ilk teslim/onay olayi (dk); olay yoksa kart alanlari (teslim_zamani/onay_zamani)."""
    bas = _t(k.get("olusturma"))
    if not bas:
        return None
    bit = None
    for x in sorted((x for x in (k.get("gecmis") or []) if isinstance(x, dict)), key=lambda x: str(x.get("zaman", ""))):
        if x.get("olay") in ("teslim", "denetim:onay"):
            bit = _t(x.get("zaman"))
            if bit:
                break
    if not bit:
        bit = _t(k.get("teslim_zamani")) or _t(k.get("onay_zamani"))
    if not bit or bit < bas:
        return None
    return (bit - bas).total_seconds() / 60


def _medyan(x):
    x = sorted(v for v in x if v is not None)
    if not x:
        return None
    h = len(x) // 2
    return x[h] if len(x) % 2 else (x[h - 1] + x[h]) / 2


def basamak_oner(kartlar, kayitlar, sinif, metin="", min_n=None, usd_fark=None) -> dict:
    pol = politika()
    if min_n is None:
        min_n = pol["min_n"]
    if usd_fark is None:
        usd_fark = pol["usd_fark"]
    sn = sinif_normal(sinif)
    usd = _kart_usd(kayitlar)
    tok = _kart_token(kayitlar)
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
        g = gruplar.setdefault(b, {"a": 0, "r": 0, "usd": 0.0, "token": 0, "dk": []})
        g["a" if karar == "onay" else "r"] += 1
        g["usd"] += usd.get(c.get("id"), 0.0)
        g["token"] += tok.get(c.get("id"), 0)
        g["dk"].append(_kart_dk(c))
    adaylar = []
    for b in sorted(gruplar):
        g = gruplar[b]
        n = g["a"] + g["r"]
        p = (g["a"] + 1) / (n + 2)
        al = alt_sinir(g["a"], g["r"])
        ort = g["usd"] / n
        med = _medyan(g["dk"])
        adaylar.append({"basamak": b, "n": n, "ilk_gecis_olasiligi": p, "alt_sinir": al, "ort_usd": ort,
                        "beklenen_usd": ort / al, "ort_token": g["token"] / n, "beklenen_token": g["token"] / n / al, "medyan_dk": med,
                        "beklenen_dk": (med / al) if med is not None else None})
    yeterli = [x for x in adaylar if x["n"] >= min_n]
    if yeterli:
        en = min(yeterli, key=lambda x: (x["beklenen_usd"], x["basamak"]))
        yakin = [x for x in yeterli if x["beklenen_usd"] <= en["beklenen_usd"] * (1 + usd_fark)]
        gerekce = "en-kucuk-beklenen-usd"
        if len(yakin) > 1:
            en2 = min(yakin, key=lambda x: (x["beklenen_dk"] is None, x["beklenen_dk"] or 0.0,
                                            x["beklenen_usd"], x["basamak"]))
            if en2 is not en and en2["beklenen_dk"] is not None:
                en, gerekce = en2, "usd-esit-en-kucuk-beklenen-dk"
        onerilen = en["basamak"]
        elenen = [x["basamak"] for x in adaylar if x["n"] < min_n]
        if elenen:
            gerekce = "yetersiz-veri"
    else:
        onerilen, gerekce = "T2", "yetersiz-veri"
        elenen = [x["basamak"] for x in adaylar]
    bz = benzer(kartlar, metin) if (metin or "").strip() else []
    uyarilar = []
    for x in bz:
        for kod in x["nedenler"]:
            ip = KRITER_IPUCU.get(kod)
            if ip and ip not in uyarilar:
                uyarilar.append(ip)
    return {"sinif": sn, "onerilen": onerilen, "gerekce": gerekce, "adaylar": adaylar,
            "elenen": elenen, "benzer": bz, "uyarilar": uyarilar}


def _duz(s: dict) -> str:
    sat = [f"sinif={s['sinif']}  onerilen={s['onerilen']}  gerekce={s['gerekce']}"]
    for a in s["adaylar"][:6]:
        sat.append(f"  {a['basamak']}: n={a['n']} alt={a['alt_sinir']:.2f} "
                   f"ort=${a['ort_usd']:.4f} beklenen=${a['beklenen_usd']:.4f} "
                   f"token ort={a['ort_token']:,.0f} beklenen={a['beklenen_token']:,.0f} "
                   f"dk={'-' if a['beklenen_dk'] is None else format(a['beklenen_dk'], '.0f')}")
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
    b.add_argument("--min-n", type=int, default=None)
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
