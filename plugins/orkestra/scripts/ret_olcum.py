"""Ret oranı ölçümü (I-224 P10): R1–R9 sınıfı başına ret/100 tur, Garwood üst sınırı ve önce/sonra kararı.

Salt okur, model çağırmaz. Kaynaklar (durum klasörü):
- hata.jsonl `tur: hook-red` satırları: ret. Sınıf satırın `ret_sinif` alanından; yoksa (eski satır) kapı kimliği
  `kapi` alanından, o da yoksa iletiden türetilir ve ret_nedeni.ret_sinifi() ile eşlenir. Eşlenemeyen 'siniflanmamis'.
- zaman.jsonl `tur: ana` satırları: tur paydası.
- Kart denetimleri (`denetimler[].karar`): R5 (anlamsal kalite) denetçi retidir, paydası denetçi kararıdır (100 karar).
- gunluk.jsonl `kural_ihlal`, `kapi_ret`, `kapi_golge`: R9 davranışlarında (kimlik, bütçe, konu dışı, seçim, kapanış)
  ihlal sayısı ile turu gerçekten engelleyen kayıt sayısı ayrı verilir.

İstatistik (129 plan §1): tek yanlı %95 Poisson üst sınırı (Garwood) = P(X <= x; λ) = 0,05 eşitliğinin λ çözümü
(chi2 ters CDF'ye eşdeğer; stdlib bisection). Karar: sonrası üst sınır oranı < öncesi (taban) oranı ise "etki var",
değilse "etki yok". Asgari gözlem: oran tabanın %30'una indiğinde bu kararı %80 güçle verecek en küçük payda (25'lik
adım); 129 plan §1 tablosunu (K-005 125, P-005 375, P-016 450, plan doğrulama 575, toplam 75, denetçi 150 karar)
aynen üretir. Sonrası payda asgarinin altındaysa "yetersiz örnek".
"""
from __future__ import annotations

import datetime
import functools
import math
import os
import re

import ret_nedeni as RN

GUVEN = 0.95
HEDEF_ORAN = 0.30      # etki: oranın tabanın %30'una inmesi
GUC = 0.80
ADIM = 25              # asgari gözlem adımı (tur ya da karar)
SINIFLAR = tuple(RN.RET_SINIFLARI) + (RN.SINIFLANMAMIS,)
TOPLAM = "toplam"

# Eski (kapı alanı olmayan) hook-red satırlarında kimliksiz iletiden kapı türetme. Sıra önemlidir: ilk eşleşen kazanır.
_ILETI_KAPI = (
    (re.compile(r"\b(?:[KP]-\d{3}|ADR-\d{4})\b"), None),           # None: eşleşen kimliğin kendisi
    (re.compile(r"bir işe bağlı değil|bağsız oturum", re.I), "bagsiz"),
    (re.compile(r"plan doğrulaması", re.I), "plan_dogrulama"),
)

# 129 plan §1 asgari tablosu (tabandan türetilir; test bu sayıları asgari() ile yeniden hesaplar).
ASGARI_PLAN = {"K-005": (0.087, 125), "P-005": (0.026, 375), "P-016": (0.021, 450),
               "plan_dogrulama": (0.016, 575), TOPLAM: (0.209, 75), "denetci_kb_ky": (0.062, 150)}

# R9 davranışları: (gunluk tur, kural/kapı adı) eşlemesi ve hook-red kapı kimlikleri.
DAVRANISLAR = {
    "kimlik": {"kayit": {("kural_ihlal", "kimlik_once_bak")}, "kapi": {"P-023"}},
    "butce": {"kayit": {("kapi_golge", "cikti_butce"), ("kapi_ret", "cikti_butce"),
                        ("kural_ihlal", "cikti_butce")}, "kapi": {"cikti_butcesi"}},
    "konu_disi": {"kayit": {("kural_ihlal", "konu_disi_oneri")}, "kapi": {"P-012"}},
    "secim": {"kayit": {("kural_ihlal", "secim_ekrani")}, "kapi": {"P-029"}},
    "kapanis": {"kayit": {("kural_ihlal", "kapanis_atlandi")}, "kapi": {"kapanis"}},
}
# Kip alanı olmadan da turu engelleyen kural ihlalleri (hook.py _kapanis_kapisi her zaman block döner).
_HER_ZAMAN_ENGEL = {"kapanis_atlandi"}
_ENGEL_KIP = {"block", "ihlal"}


# ---------------------------------------------------------------- istatistik

def _poisson_cdf(x: int, m: float) -> float:
    """P(X <= x), X ~ Poisson(m); log uzayında toplanır (büyük m'de taşma olmaz)."""
    if x < 0:
        return 0.0
    if m <= 0:
        return 1.0
    lm = math.log(m)
    return min(1.0, sum(math.exp(k * lm - m - math.lgamma(k + 1)) for k in range(x + 1)))


@functools.lru_cache(maxsize=4096)
def garwood_ust(x: int, guven: float = GUVEN) -> float:
    """Tek yanlı Garwood üst sınırı (olay sayısı cinsinden): P(X <= x; λ) = 1 - guven çözümü. 0 → 2,996; 1 → 4,744."""
    a = 1.0 - guven
    lo, hi = 0.0, x + 10.0 + 10.0 * math.sqrt(x + 1.0)
    while _poisson_cdf(x, hi) > a:
        hi *= 2
    for _ in range(200):
        mid = (lo + hi) / 2
        if _poisson_cdf(x, mid) > a:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def asgari(taban_orani: float, adim: int = ADIM, hedef: float = HEDEF_ORAN, guc: float = GUC,
           en_cok: int = 1_000_000):
    """Oran tabanın `hedef` katına indiğinde "etki var" kararını `guc` olasılıkla verecek en küçük payda; taban 0 → None."""
    if not taban_orani or taban_orani <= 0:
        return None
    n = adim
    while n <= en_cok:
        sinir = taban_orani * n
        x = -1
        while garwood_ust(x + 1) < sinir:
            x += 1
        if x >= 0 and _poisson_cdf(x, hedef * sinir) >= guc:
            return n
        n += adim
    return None


def _oran(n: int, payda: int):
    return round(100.0 * n / payda, 2) if payda else None


def _ust(n: int, payda: int):
    return round(100.0 * garwood_ust(n) / payda, 2) if payda else None


# ---------------------------------------------------------------- kayıt okuma

def zaman_coz(z):
    """ISO zaman ya da YYYY-MM-DD → saat dilimli datetime; çözülemezse None. Saat dilimsiz değer yerel sayılır."""
    if isinstance(z, datetime.datetime):
        t = z
    else:
        try:
            t = datetime.datetime.fromisoformat(str(z or "").strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    return t if t.tzinfo else t.astimezone()


def kapi_turet(satir: dict):
    """Satırın kapı kimliği: `kapi` alanı, yoksa iletiden (_ILETI_KAPI); bulunamazsa None."""
    if satir.get("kapi"):
        return satir["kapi"]
    ileti = str(satir.get("ileti") or "")
    for desen, ad in _ILETI_KAPI:
        m = desen.search(ileti)
        if m:
            return ad or m.group(0)
    return None


def sinif_turet(satir: dict) -> str:
    """R1–R9 sınıfı: kayıttaki `ret_sinif` (P1 sonrası), yoksa kapıdan ret_nedeni.ret_sinifi()."""
    s = satir.get("ret_sinif")
    if s in RN.RET_SINIFLARI or s == RN.SINIFLANMAMIS:
        return s
    return RN.ret_sinifi(kapi_turet(satir))


def yukle(sd: str) -> dict:
    """Durum klasöründen ölçüm girdileri (salt okuma)."""
    import ork_lib as L
    import hata_kayit as HK

    def oku(ad):
        return [r for r in L.jsonl_oku(os.path.join(sd, ad)) if isinstance(r, dict)]

    denetimler = []
    for k in L.kartlar(sd):
        if k.get("durum") == "iptal":   # analitik.ret_kayitlari ile aynı kural: iptal kartın kararları sayılmaz
            continue
        for d in k.get("denetimler") or []:
            if isinstance(d, dict) and d.get("karar") in ("onay", "ret"):
                denetimler.append({"zaman": d.get("zaman"), "karar": d.get("karar"), "neden": d.get("neden")})
    return {"hatalar": oku(HK.DOSYA), "gunluk": oku("gunluk.jsonl"), "zaman": oku("zaman.jsonl"),
            "denetimler": denetimler}


# ---------------------------------------------------------------- sayım

def _pencere(kayitlar, bas, bit):
    """[bas, bit) aralığındaki kayıtlar (None sınırı açık)."""
    out = []
    for r in kayitlar:
        t = zaman_coz(r.get("zaman"))
        if t is None or (bas and t < bas) or (bit and t >= bit):
            continue
        out.append(r)
    return out


def _engelleyen(g: dict) -> bool:
    if g.get("tur") == "kapi_ret":
        return True
    if g.get("tur") != "kural_ihlal":
        return False
    return g.get("mod") in _ENGEL_KIP or (g.get("mod") is None and g.get("kural") in _HER_ZAMAN_ENGEL)


def say(girdi: dict, bas=None, bit=None) -> dict:
    """Bir pencerenin sayımı: tur ve karar paydası, sınıf/kapı ret sayısı, davranış ihlal/engel sayısı."""
    turlar = sum(1 for r in _pencere(girdi.get("zaman") or [], bas, bit) if r.get("tur") == "ana")
    retler = [r for r in _pencere(girdi.get("hatalar") or [], bas, bit) if r.get("tur") == "hook-red"]
    den = _pencere(girdi.get("denetimler") or [], bas, bit)
    gun = [g for g in _pencere(girdi.get("gunluk") or [], bas, bit)
           if g.get("tur") in ("kural_ihlal", "kapi_ret", "kapi_golge")]

    sinif = {s: 0 for s in SINIFLAR}
    kapi: dict = {}
    for r in retler:
        sinif[sinif_turet(r)] += 1
        k = kapi_turet(r) or "?"
        kapi[k] = kapi.get(k, 0) + 1
    den_ret = [d for d in den if d.get("karar") == "ret"]
    davranis = {}
    for ad, tanim in DAVRANISLAR.items():
        kayit = [g for g in gun if (g.get("tur"), g.get("kural") or g.get("kapi")) in tanim["kayit"]]
        hook = sum(1 for r in retler if kapi_turet(r) in tanim["kapi"])
        davranis[ad] = {"ihlal": len(kayit) + hook, "engelleyen": sum(1 for g in kayit if _engelleyen(g)) + hook}
    return {"tur": turlar, "karar": len(den), "ret_toplam": len(retler), "sinif": sinif, "kapi": kapi,
            "denetci_ret": len(den_ret),
            "denetci_kb_ky": sum(1 for d in den_ret if d.get("neden") in ("kriter-belirsiz", "kanit-yok")),
            "davranis": davranis}


def _satirlar(s: dict) -> list[tuple]:
    """(ad, olay, payda, birim) satırları: R1–R9 + siniflanmamis + toplam, sonra kapılar ve denetçi alt kümesi."""
    out = []
    for c in SINIFLAR:
        if c == "R5":   # anlamsal kalite: denetçi reti / denetçi kararı (hook-red R5'i toplamda kalır)
            out.append(("R5", s["denetci_ret"], s["karar"], "karar"))
        else:
            out.append((c, s["sinif"][c], s["tur"], "tur"))
    out.append((TOPLAM, s["ret_toplam"], s["tur"], "tur"))
    return out


def _kapi_satirlari(s: dict, ek=()) -> list[tuple]:
    adlar = sorted(set(s["kapi"]) | set(ek), key=lambda k: (-s["kapi"].get(k, 0), k))
    out = [(f"kapi:{k}", s["kapi"].get(k, 0), s["tur"], "tur") for k in adlar]
    out.append(("denetci_kb_ky", s["denetci_kb_ky"], s["karar"], "karar"))
    return out


def _tek(ad, n, payda, birim) -> dict:
    return {"ad": ad, "birim": birim, "ret": n, "payda": payda, "oran_100": _oran(n, payda), "ust_100": _ust(n, payda)}


def karar(on: dict, son: dict) -> dict:
    """Öncesi/sonrası tek satır kararı: yetersiz örnek | etki var | etki yok | taban yok."""
    taban = on["ret"] / on["payda"] if on["payda"] else 0.0
    gerekli = asgari(taban)
    if not taban:
        k = "taban yok"
    elif son["payda"] < (gerekli or 0) or not son["payda"]:
        k = "yetersiz örnek"
    else:
        k = "etki var" if garwood_ust(son["ret"]) / son["payda"] < taban else "etki yok"
    return {"asgari": gerekli, "karar": k}


def ozet(girdi: dict, baslangic=None, oncesi=None, sonrasi=None, bitis=None) -> dict:
    """Ölçüm sonucu. Sınır yoksa tek pencere [baslangic, bitis); `oncesi`/`sonrasi` verilirse öncesi [baslangic, oncesi),
    sonrası [sonrasi, bitis) (biri verilmezse diğerine eşit; aradaki dönem dışarıda kalır)."""
    bas, bit = zaman_coz(baslangic) if baslangic else None, zaman_coz(bitis) if bitis else None
    if oncesi is None and sonrasi is None:
        s = say(girdi, bas, bit)
        return {"mod": "tek", "pencere": {"baslangic": baslangic, "bitis": bitis, "tur": s["tur"], "karar": s["karar"]},
                "siniflar": [_tek(*r) for r in _satirlar(s)],
                "kapilar": [_tek(*r) for r in _kapi_satirlari(s)],
                "davranislar": [{"ad": k, **v, "ihlal_100": _oran(v["ihlal"], s["tur"]),
                                 "engelleyen_100": _oran(v["engelleyen"], s["tur"])} for k, v in s["davranis"].items()]}
    o_sinir = zaman_coz(oncesi if oncesi is not None else sonrasi)
    s_sinir = zaman_coz(sonrasi if sonrasi is not None else oncesi)
    so, ss = say(girdi, bas, o_sinir), say(girdi, s_sinir, bit)

    def eslestir(on_s, son_s):
        out = []
        for a, b in zip(on_s, son_s):
            on, son = _tek(*a), _tek(*b)
            out.append({"ad": a[0], "birim": a[3], "oncesi": on, "sonrasi": son, **karar(on, son)})
        return out
    kapi_adlari = set(so["kapi"]) | set(ss["kapi"])
    return {"mod": "karsilastirma",
            "pencere": {"baslangic": baslangic, "oncesi": oncesi if oncesi is not None else sonrasi,
                        "sonrasi": sonrasi if sonrasi is not None else oncesi, "bitis": bitis,
                        "oncesi_tur": so["tur"], "sonrasi_tur": ss["tur"],
                        "oncesi_karar": so["karar"], "sonrasi_karar": ss["karar"]},
            "siniflar": eslestir(_satirlar(so), _satirlar(ss)),
            "kapilar": eslestir(_kapi_satirlari(so, kapi_adlari), _kapi_satirlari(ss, kapi_adlari)),
            "davranislar": [{"ad": k, "oncesi": so["davranis"][k], "sonrasi": ss["davranis"][k]}
                            for k in DAVRANISLAR]}


# ---------------------------------------------------------------- metin

def _s(v) -> str:
    return "-" if v is None else (f"{v:.2f}" if isinstance(v, float) else str(v))


def metin(o: dict) -> list[str]:
    """Okunur tablo satırları."""
    p = o["pencere"]
    if o["mod"] == "tek":
        out = [f"pencere: {p['baslangic'] or 'başından'} → {p['bitis'] or 'şimdi'} · tur {p['tur']} · denetçi kararı {p['karar']}",
               f"{'sınıf':<24}{'ret':>6}{'payda':>8}{'ret/100':>10}{'üst%95/100':>12}"]
        for r in o["siniflar"] + o["kapilar"]:
            out.append(f"{r['ad']:<24}{r['ret']:>6}{r['payda']:>8}{_s(r['oran_100']):>10}{_s(r['ust_100']):>12}"
                       + ("  (karar)" if r["birim"] == "karar" else ""))
        out.append(f"{'davranış':<24}{'ihlal':>6}{'engel':>8}{'ihlal/100':>10}{'engel/100':>12}")
        for d in o["davranislar"]:
            out.append(f"{d['ad']:<24}{d['ihlal']:>6}{d['engelleyen']:>8}{_s(d['ihlal_100']):>10}{_s(d['engelleyen_100']):>12}")
        return out
    out = [f"öncesi: {p['baslangic'] or 'başından'} → {p['oncesi']} (tur {p['oncesi_tur']}, karar {p['oncesi_karar']}) · "
           f"sonrası: {p['sonrasi']} → {p['bitis'] or 'şimdi'} (tur {p['sonrasi_tur']}, karar {p['sonrasi_karar']})",
           f"{'sınıf':<24}{'önce ret':>9}{'önce/100':>10}{'sonra ret':>10}{'sonra/100':>10}{'üst/100':>9}{'asgari':>8}  karar"]
    for r in o["siniflar"] + o["kapilar"]:
        a, b = r["oncesi"], r["sonrasi"]
        out.append(f"{r['ad']:<24}{a['ret']:>9}{_s(a['oran_100']):>10}{b['ret']:>10}{_s(b['oran_100']):>10}"
                   f"{_s(b['ust_100']):>9}{_s(r['asgari']):>8}  {r['karar']}")
    out.append(f"{'davranış':<24}{'önce ihlal':>11}{'önce engel':>11}{'sonra ihlal':>12}{'sonra engel':>12}")
    for d in o["davranislar"]:
        out.append(f"{d['ad']:<24}{d['oncesi']['ihlal']:>11}{d['oncesi']['engelleyen']:>11}"
                   f"{d['sonrasi']['ihlal']:>12}{d['sonrasi']['engelleyen']:>12}")
    return out
