"""Orkestra analitiği: zaman içinde harcama, kota, basamak verimliliği, ya-şöyle-olsaydı tasarrufu, kart akışı,
birim maliyet, skill getirisi, sağlık ve tüm çalışma alanlarının karşılaştırması.

Yalnız okur; kaynaklar:
  <durum>/maliyet.jsonl, gorevler/*.json, gunluk.jsonl, ruya/durum.json, onerilen_skill/*   (proje)
  ~/.claude/projects/<proje>/memory/MEMORY.md                                              (hafıza)
  ~/.claude/orkestra-panel/kota.jsonl   (durum satırı komutu kota.py yazar; 5 saatlik ve haftalık sınır)
Tutarlar API liste fiyatıyla tahmindir; abonelikte fatura değil kota karşılığıdır.

`olustur(sd, proje)` tek alanın, `tum_alanlar()` bütün alanların sözlüğünü döner.
Komut satırı: python analitik.py [proje klasörü]  → JSON
"""
from __future__ import annotations

import calendar
import collections
import datetime
import glob
import json
import os
import re
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ork_lib as L  # noqa: E402

GENEL_DIZIN = os.path.join(os.path.expanduser("~"), ".claude", "orkestra-panel")
KOTA_YOLU = os.path.join(GENEL_DIZIN, "kota.jsonl")
HAFIZA_SATIR_SINIRI = 200
HAFIZA_BAYT_SINIRI = 25 * 1024
KUCUK_BASAMAK_HEDEFI = 0.60
KUCUK_BASAMAKLAR = ("T0", "T1", "T2")
BASAMAK_SIRASI = ("T0", "T1", "T2", "T3", "T4")


# ---------------------------------------------------------------- yardımcılar

def _zaman(s: str | None) -> datetime.datetime | None:
    if not s:
        return None
    try:
        z = datetime.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return (z if z.tzinfo else z.astimezone()).astimezone()
    except Exception:
        return None


def _dk(a: datetime.datetime | None, b: datetime.datetime | None) -> float | None:
    if not a or not b:
        return None
    return round((b - a).total_seconds() / 60, 1)


def _ort(x: list) -> float | None:
    x = [v for v in x if v is not None]
    return round(sum(x) / len(x), 2) if x else None


def _medyan(x: list) -> float | None:
    x = [v for v in x if v is not None]
    return round(statistics.median(x), 2) if x else None


def _r(v: float, n: int = 4) -> float:
    return round(v or 0.0, n)


def _kisa_model(m: str | None) -> str:
    m = (m or "-").replace("claude-", "")
    return m.split("[")[0]


def _formul_usd(r: dict, model: str) -> float:
    """Satırın token sayılarından verilen modelin liste fiyatıyla maliyet (önbellek yazma 5 dk tarifesiyle)."""
    f = L.model_fiyati(model)
    return ((r.get("giris") or 0) * f["giris"] + (r.get("cikis") or 0) * f["cikis"]
            + (r.get("onbellek_okuma") or 0) * f["onbellek_okuma"]
            + (r.get("onbellek_yazma") or 0) * f["onbellek_yazma_5dk"]) / 1_000_000


AJAN_ADLARI = {
    "ana-ajan": "Ana ajan", "ana": "Ana ajan", "orkestra:denetci": "Denetçi", "orkestra:arastirmaci": "Araştırmacı",
    "orkestra:triyaj": "Triyaj", "orkestra:ruya-ajani": "Rüya ajanı", "orkestra:skill-avcisi": "Skill avcısı",
    "orkestra:hafiza-bakimcisi": "Hafıza bakımcısı", "orkestra:arsivci": "Arşivci", "general-purpose": "Genel alt ajan",
    "Explore": "Keşif ajanı", "Plan": "Plan ajanı", "claude-code-guide": "Claude Code rehberi",
}
SUREC_ADLARI = {
    "orkestrasyon": "planlama ve koordinasyon", "is": "işçi çalışması", "denetim": "denetim", "duzeltme": "düzeltme",
    "arastirma": "araştırma", "sentez": "sentez", "ruya": "rüya (bakım)", "gecmis-ana": "orkestra öncesi · ana ajan",
    "gecmis-alt": "orkestra öncesi · alt ajan",
}


def ajan_adi(k: str | None) -> str:
    """Ajan kimliği -> kullanıcı dili (ortak.js O.E.ajan karşılığı). Bilinmeyen olduğu gibi döner."""
    k = k or ""
    m = re.fullmatch(r"orkestra:isci-t(\d+)", k)
    if m:
        return f"İşçi T{m.group(1)}"
    return AJAN_ADLARI.get(k, k or "Bilinmeyen ajan")


def _tr_sayi(v: float, ondalik: int = 1) -> str:
    return f"{v:.{ondalik}f}".replace(".", ",")


def _tr_usd(v: float) -> str:
    return "$" + _tr_sayi(v, 0 if abs(v) >= 10 else 2)


def gun_toplamlari(kayitlar: list[dict]) -> dict:
    """Kayıtların yerel gün (datetime.date) bazında USD toplamı. Bütün 'bugün' hesapları buradan geçer."""
    out: dict = collections.defaultdict(float)
    for r in kayitlar:
        z = _zaman(r.get("zaman"))
        if z:
            out[z.date()] += r.get("maliyet_usd") or 0.0
    return out


def bugun_usd(kayitlar: list[dict], bugun: datetime.date | None = None) -> float:
    return gun_toplamlari(kayitlar).get(bugun or datetime.date.today(), 0.0)


def _rol(ajan: str | None) -> str:
    a = (ajan or "").lower()
    if a == "ana-ajan":
        return "ana"
    if "denetci" in a:
        return "denetci"
    if "isci" in a:
        return "isci"
    if "ruya" in a or "skill-avcisi" in a or "hafiza" in a:
        return "bakim"
    return "diger"


# ---------------------------------------------------------------- 1. zaman içinde harcama

def _trend(kayitlar: list[dict], bugun: datetime.date) -> dict:
    gun = collections.defaultdict(lambda: {"usd": 0.0, "model": collections.Counter()})
    for r in kayitlar:
        z = _zaman(r.get("zaman"))
        if not z:
            continue
        g = gun[z.date()]
        usd = r.get("maliyet_usd") or 0.0
        g["usd"] += usd
        g["model"][_kisa_model(r.get("model"))] += usd

    def kume(anahtar):
        out = collections.defaultdict(lambda: {"usd": 0.0, "model": collections.Counter()})
        for d, g in gun.items():
            k = anahtar(d)
            out[k]["usd"] += g["usd"]
            out[k]["model"].update(g["model"])
        return [{"donem": k, "usd": _r(v["usd"]), "model": {m: _r(u) for m, u in v["model"].items() if u}}
                for k, v in sorted(out.items())]

    ilk = min(gun) if gun else bugun
    bas = max(ilk, bugun - datetime.timedelta(days=59))
    gunluk = []
    d = bas
    while d <= bugun:  # boş günler de görünsün
        g = gun.get(d, {"usd": 0.0, "model": {}})
        gunluk.append({"donem": d.isoformat(), "usd": _r(g["usd"]), "model": {m: _r(u) for m, u in g["model"].items() if u}})
        d += datetime.timedelta(days=1)
    haftalik = kume(lambda d: f"{d.isocalendar()[0]}-H{d.isocalendar()[1]:02d}")[-12:]
    aylik = kume(lambda d: d.strftime("%Y-%m"))[-12:]

    # ay sonu tahmini: ay başından bugüne ortalama ve son 7 günün hızı
    ay_bas = bugun.replace(day=1)
    ay_gun = calendar.monthrange(bugun.year, bugun.month)[1]
    gecen = (bugun - ay_bas).days + 1
    simdiye = sum(g["usd"] for d, g in gun.items() if ay_bas <= d <= bugun)
    veri_bas = max(ay_bas, ilk)
    aktif_gun = (bugun - veri_bas).days + 1
    son7 = sum(g["usd"] for d, g in gun.items() if bugun - datetime.timedelta(days=6) <= d <= bugun)
    son7_gun = min(7, (bugun - ilk).days + 1) if gun else 7
    kalan = ay_gun - gecen
    tahmin_ort = simdiye + (simdiye / aktif_gun) * kalan if aktif_gun else 0.0
    tahmin_7g = simdiye + (son7 / son7_gun) * kalan if son7_gun else 0.0
    onceki_ay = (ay_bas - datetime.timedelta(days=1)).strftime("%Y-%m")
    return {
        "gunluk": gunluk, "haftalik": haftalik, "aylik": aylik,
        "ay_sonu": {"ay": bugun.strftime("%Y-%m"), "simdiye": _r(simdiye, 2), "gecen_gun": gecen, "ay_gun": ay_gun,
                    "veri_gun": aktif_gun, "gunluk_ort": _r(simdiye / aktif_gun if aktif_gun else 0, 2),
                    "son7_gunluk": _r(son7 / son7_gun if son7_gun else 0, 2),
                    "tahmin_ort": _r(tahmin_ort, 2), "tahmin_7g": _r(tahmin_7g, 2),
                    "onceki_ay": next((a["usd"] for a in aylik if a["donem"] == onceki_ay), None)},
        "ilk_kayit": ilk.isoformat() if gun else None,
    }


# ---------------------------------------------------------------- 2. kota (5 saatlik ve haftalık sınır)

def _kota() -> dict:
    noktalar = L.jsonl_oku(KOTA_YOLU)
    simdi = datetime.datetime.now().astimezone()
    kaynak = "durum-satiri" if noktalar else None
    sinir = simdi - datetime.timedelta(days=8)
    noktalar = [n for n in noktalar if (_zaman(n.get("zaman")) or simdi) >= sinir]

    def pencere(ad: str, sure_s: int) -> dict | None:
        son = next((n for n in reversed(noktalar) if n.get(ad)), None)
        if not son:
            return None
        p = son[ad]
        sifir = p.get("sifirlanma")
        sifir_z = datetime.datetime.fromtimestamp(sifir).astimezone() if isinstance(sifir, (int, float)) else None
        if sifir_z and sifir_z < simdi:
            return {"yuzde": 0, "kalan": 100, "sifirlanma": None, "olcum": son["zaman"], "eski": True,
                    "not": "pencere sıfırlandı; yeni ölçüm bekleniyor"}
        yuzde = float(p.get("yuzde") or 0)
        # mevcut hız: aynı pencere içindeki ilk ve son ölçüm
        hiz = tahmin = None
        if sifir:
            ayni = [n for n in noktalar if n.get(ad) and n[ad].get("sifirlanma") == sifir]
            if len(ayni) >= 2:
                a, b = ayni[0], ayni[-1]
                dt = ((_zaman(b["zaman"]) - _zaman(a["zaman"])).total_seconds() / 3600) if _zaman(a["zaman"]) else 0
                if dt > 0.05:
                    hiz = (b[ad]["yuzde"] - a[ad]["yuzde"]) / dt
                    if hiz > 0:
                        dolma = simdi + datetime.timedelta(hours=(100 - yuzde) / hiz)
                        tahmin = {"dolma": dolma.isoformat(timespec="minutes"),
                                  "sifirlanmadan_once": bool(sifir_z and dolma < sifir_z)}
        seviye = "kritik" if yuzde >= 95 else "uyari" if yuzde >= 80 or (tahmin and tahmin["sifirlanmadan_once"]) else "iyi"
        return {"yuzde": round(yuzde, 1), "kalan": round(100 - yuzde, 1),
                "sifirlanma": sifir_z.isoformat(timespec="minutes") if sifir_z else None,
                "olcum": son["zaman"], "saat_basi_hiz": round(hiz, 2) if hiz is not None else None,
                "tahmin": tahmin, "seviye": seviye}

    seri = [{"zaman": n["zaman"], "bes_saat": (n.get("bes_saat") or {}).get("yuzde"),
             "haftalik": (n.get("haftalik") or {}).get("yuzde")} for n in noktalar][-600:]
    return {"kaynak": kaynak, "bes_saat": pencere("bes_saat", 5 * 3600), "haftalik": pencere("haftalik", 7 * 86400),
            "seri": seri, "kota_dosyasi": KOTA_YOLU}


# ---------------------------------------------------------------- 3. basamak verimliliği

def _basamak(kartlar: list[dict], kayitlar: list[dict]) -> dict:
    satir = {b: {"basamak": b, "kart": 0, "teslim": 0, "denetlenen": 0, "ilk_gecis": 0, "denetim": 0, "ret": 0,
                 "yukseltilen": 0, "usd": 0.0} for b in BASAMAK_SIRASI}
    kart_usd = collections.Counter()
    for r in kayitlar:
        if r.get("gorev") not in (None, "-"):
            kart_usd[r["gorev"]] += r.get("maliyet_usd") or 0.0
    teslim, kucuk = 0, 0
    for k in kartlar:
        bas = k.get("baslangic_basamak") or k.get("basamak")
        son = k.get("basamak") or bas
        if bas not in satir:
            continue
        s = satir[bas]
        s["kart"] += 1
        s["usd"] += kart_usd.get(k["id"], 0.0)
        yukseldi = bas != son or any(g.get("olay") == "yukseltme" for g in k.get("gecmis", []))
        s["yukseltilen"] += int(yukseldi)
        dnt = sorted(k.get("denetimler") or [], key=lambda d: (d.get("sira", 0), d.get("zaman", "")))
        if dnt:
            s["denetlenen"] += 1
            s["ilk_gecis"] += int(dnt[0].get("karar") == "onay")
        for d in dnt:  # denetimi, denetlendiği andaki basamağa yaz
            b = d.get("basamak") if d.get("basamak") in satir else bas
            satir[b]["denetim"] += 1
            satir[b]["ret"] += int(d.get("karar") == "ret")
        if L.kart_durumu_hesapla(k) == "teslim":
            teslim += 1
            s["teslim"] += 1
            kucuk += int(son in KUCUK_BASAMAKLAR)
    for s in satir.values():
        s["ilk_gecis_orani"] = _r(s["ilk_gecis"] / s["denetlenen"], 3) if s["denetlenen"] else None
        s["ret_orani"] = _r(s["ret"] / s["denetim"], 3) if s["denetim"] else None
        s["yukseltme_orani"] = _r(s["yukseltilen"] / s["kart"], 3) if s["kart"] else None
        s["usd"] = _r(s["usd"])
        s["kart_basi_usd"] = _r(s["usd"] / s["kart"]) if s["kart"] else None

    # işçi harcamasının (süreç 'is') model payı
    is_usd = collections.Counter()
    for r in kayitlar:
        if r.get("surec") in ("is", "duzeltme") or _rol(r.get("ajan")) == "isci":
            is_usd[_kisa_model(r.get("model"))] += r.get("maliyet_usd") or 0.0
    toplam_is = sum(is_usd.values())
    kucuk_usd = sum(v for m, v in is_usd.items() if m.startswith(("haiku", "sonnet")))
    return {
        "hedef": KUCUK_BASAMAK_HEDEFI, "teslim_kart": teslim,
        "kucuk_pay_kart": _r(kucuk / teslim, 3) if teslim else None,
        "kucuk_pay_is_usd": _r(kucuk_usd / toplam_is, 3) if toplam_is else None,
        "is_model_usd": {m: _r(v) for m, v in is_usd.most_common()},
        "satirlar": [s for s in satir.values() if s["kart"] or s["denetim"]],
    }


# ---------------------------------------------------------------- 4. ya şöyle olsaydı

def _tasarruf(kayitlar: list[dict]) -> dict:
    sonnet = "claude-sonnet-5-5"

    def senaryo(filtre, ad, aciklama):
        sec = [r for r in kayitlar if _kisa_model(r.get("model")).startswith("opus") and filtre(r)]
        gercek = sum(r.get("maliyet_usd") or 0.0 for r in sec)
        opus_f = sum(_formul_usd(r, r.get("model")) for r in sec)
        sonnet_f = sum(_formul_usd(r, sonnet) for r in sec)
        oran = sonnet_f / opus_f if opus_f else 0.0
        return {"ad": ad, "aciklama": aciklama, "kosu": len(sec), "gercek": _r(gercek, 2),
                "sonnet_olsa": _r(gercek * oran, 2), "fark": _r(gercek * (1 - oran), 2),
                "oran": _r(1 - oran, 3)}

    senaryolar = [
        senaryo(lambda r: _rol(r.get("ajan")) in ("isci", "diger"), "Opus'taki alt ajan işleri",
                "İşçi ve genel amaçlı alt ajanlar; denetçi işçinin üstünde kalmalı diye hariç."),
        senaryo(lambda r: _rol(r.get("ajan")) != "ana", "Bütün alt ajanlar", "Denetçiler dahil."),
        senaryo(lambda r: True, "Ana ajan dahil hepsi", "Planlama da Sonnet'te olsaydı."),
    ]
    # önbellek: okunan token tam giriş fiyatıyla okunsaydı; yazmanın giriş fiyatından fazlası düşülür
    kazanc = ek_yazma = 0.0
    okuma = yazma = 0
    model_kazanc = collections.Counter()
    for r in kayitlar:
        f = L.model_fiyati(r.get("model"))
        o, w = r.get("onbellek_okuma") or 0, r.get("onbellek_yazma") or 0
        k = o * (f["giris"] - f["onbellek_okuma"]) / 1e6
        e = w * (f["onbellek_yazma_5dk"] - f["giris"]) / 1e6
        kazanc += k
        ek_yazma += e
        okuma += o
        yazma += w
        model_kazanc[_kisa_model(r.get("model"))] += k - e
    toplam = sum(r.get("maliyet_usd") or 0.0 for r in kayitlar)
    net = kazanc - ek_yazma
    return {"senaryolar": senaryolar,
            "onbellek": {"brut": _r(kazanc, 2), "yazma_eki": _r(ek_yazma, 2), "net": _r(net, 2),
                         "onbelleksiz_toplam": _r(toplam + net, 2), "gercek_toplam": _r(toplam, 2),
                         "oran": _r(net / (toplam + net), 3) if toplam + net else None,
                         "okuma_token": okuma, "yazma_token": yazma,
                         "model": {m: _r(v, 2) for m, v in model_kazanc.most_common()}}}


# ---------------------------------------------------------------- 5. kart akışı

def _akis(kartlar: list[dict], kayitlar: list[dict]) -> dict:
    out = []
    for k in kartlar:
        g = sorted(k.get("gecmis") or [], key=lambda x: x.get("zaman", ""))
        olus = _zaman(k.get("olusturma")) or (_zaman(g[0]["zaman"]) if g else None)
        ilk_is = next((_zaman(x["zaman"]) for x in g if x.get("olay") == "isleniyor"), None)
        teslim = next((_zaman(x["zaman"]) for x in g if x.get("olay") == "teslim"), None)
        bekleme, is_sure = [], []
        bas_is = None
        for i, x in enumerate(g):
            if x.get("olay") == "isleniyor":
                bas_is = _zaman(x["zaman"])
            if x.get("olay") == "is-bitti":
                bitis = _zaman(x["zaman"])
                if bas_is:
                    is_sure.append(_dk(bas_is, bitis))
                    bas_is = None
                d = next((_zaman(y["zaman"]) for y in g[i + 1:] if str(y.get("olay", "")).startswith("denetim:")), None)
                if d:
                    bekleme.append(_dk(bitis, d))
                    bas_is = d  # sonraki düzeltme turu denetim kararından başlar
        out.append({"id": k["id"], "baslik": (k.get("baslik") or "")[:70], "basamak": k.get("basamak"),
                    "durum": L.kart_durumu_hesapla(k), "olusturma": k.get("olusturma"),
                    "kuyruk_dk": _dk(olus, ilk_is), "is_dk": _r(sum(v for v in is_sure if v), 1) if is_sure else None,
                    "denetim_bekleme_dk": _r(sum(v for v in bekleme if v), 1) if bekleme else None,
                    "tur": len([x for x in g if x.get("olay") == "is-bitti"]),
                    "toplam_dk": _dk(olus, teslim)})
    teslimler = [k for k in out if k["toplam_dk"] is not None]
    ozet = {"kart": len(teslimler),
            "toplam_ort": _ort([k["toplam_dk"] for k in teslimler]), "toplam_medyan": _medyan([k["toplam_dk"] for k in teslimler]),
            "kuyruk_ort": _ort([k["kuyruk_dk"] for k in teslimler]), "is_ort": _ort([k["is_dk"] for k in teslimler]),
            "denetim_bekleme_ort": _ort([k["denetim_bekleme_dk"] for k in teslimler])}
    asamalar = {"kuyruk": ozet["kuyruk_ort"] or 0, "is": ozet["is_ort"] or 0, "denetim bekleme": ozet["denetim_bekleme_ort"] or 0}
    ozet["darbogaz"] = max(asamalar, key=asamalar.get) if any(asamalar.values()) else None

    # paralel çalışan ajanların zaman çizelgesi (alt ajan koşuları)
    kosular = []
    for r in kayitlar:
        if not r.get("agent_id") or not r.get("sure_ms"):
            continue
        bit = _zaman(r.get("zaman"))
        if not bit:
            continue
        bas = bit - datetime.timedelta(milliseconds=r["sure_ms"])
        kosular.append({"bas": bas.isoformat(timespec="seconds"), "bit": bit.isoformat(timespec="seconds"),
                        "gun": bas.date().isoformat(), "ajan": r.get("ajan"), "rol": _rol(r.get("ajan")),
                        "gorev": r.get("gorev"), "surec": r.get("surec"), "model": _kisa_model(r.get("model")),
                        "usd": _r(r.get("maliyet_usd") or 0.0), "oturum": (r.get("oturum") or "")[:8],
                        "aciklama": (r.get("aciklama") or "")[:60]})
    kosular.sort(key=lambda k: k["bas"])
    gunler = sorted({k["gun"] for k in kosular}, reverse=True)[:14]
    return {"kartlar": sorted(out, key=lambda k: k["id"]), "ozet": ozet,
            "kosular": [k for k in kosular if k["gun"] in gunler], "gunler": gunler}


# ---------------------------------------------------------------- 6. birim maliyet

def _birim(kartlar: list[dict], kayitlar: list[dict], sohbetler: list[dict], trend: dict) -> dict:
    kart_usd = collections.Counter()
    for r in kayitlar:
        if r.get("gorev") not in (None, "-"):
            kart_usd[r["gorev"]] += r.get("maliyet_usd") or 0.0
    teslim = [k for k in kartlar if L.kart_durumu_hesapla(k) == "teslim"]
    kart_maliyetleri = sorted(([k["id"], _r(kart_usd.get(k["id"], 0.0))] for k in teslim), key=lambda x: -x[1])
    sohbet_usd = [s["usd"] for s in sohbetler if s.get("usd")]

    kosular = []
    for r in kayitlar:
        if not r.get("agent_id"):
            continue  # ana ajan satırları tur/oturum toplamıdır, ajan koşusu değil
        kosular.append({"zaman": r.get("zaman"), "ajan": r.get("ajan"), "gorev": r.get("gorev"), "surec": r.get("surec"),
                        "model": _kisa_model(r.get("model")), "usd": _r(r.get("maliyet_usd") or 0.0),
                        "oturum": (r.get("oturum") or "")[:8], "aciklama": (r.get("aciklama") or "")[:60],
                        "kaynak": r.get("kaynak") or "hook"})
    en_pahali = sorted(kosular, key=lambda k: -k["usd"])[:10]

    # anormal sıçrama: aynı ajan türünün medyanının 3 katı ve en az 0,50 $; gün: önceki 7 gün ortalamasının 2 katı
    tur_usd = collections.defaultdict(list)
    for k in kosular:
        tur_usd[(k["ajan"], k["surec"])].append(k["usd"])
    uyarilar = []
    sinir = (datetime.datetime.now().astimezone() - datetime.timedelta(days=14))
    for k in kosular:
        grup = tur_usd[(k["ajan"], k["surec"])]
        z = _zaman(k["zaman"])
        if len(grup) >= 4 and z and z >= sinir:
            med = statistics.median(grup)
            if k["usd"] >= max(0.5, 3 * med):
                uyarilar.append({"tur": "kosu", "zaman": k["zaman"], "metin":
                                 f"{ajan_adi(k['ajan'])} · {SUREC_ADLARI.get(k['surec'], k['surec'] or 'etiketsiz')} koşusu {_tr_usd(k['usd'])}: "
                                 f"bu türün medyanının {_tr_sayi(k['usd'] / med)} katı (medyan {_tr_usd(med)})"
                                 if med else f"{ajan_adi(k['ajan'])} koşusu {_tr_usd(k['usd'])}"})
    # gün sıçraması: yalnız tamamlanmış günler (bugünün kısmi günü dışarıda); önceki en çok 7 dolu günün ortalamasının 2 katı
    bugun_iso = datetime.date.today().isoformat()
    gunluk = [g for g in trend["gunluk"] if g["donem"] < bugun_iso]
    for i, g in enumerate(gunluk):
        onceki = [x["usd"] for x in gunluk[max(0, i - 7):i] if x["usd"]]
        if len(onceki) >= 3 and g["usd"] >= 2 * (sum(onceki) / len(onceki)) and g["usd"] >= 2:
            ort = sum(onceki) / len(onceki)
            gg = datetime.date.fromisoformat(g["donem"]).strftime("%d.%m")
            uyarilar.append({"tur": "gun", "zaman": g["donem"],
                             "metin": f"{gg}: önceki günlerin {_tr_sayi(g['usd'] / ort)} katı ({_tr_usd(g['usd'])} · ort. {_tr_usd(ort)})"})
    return {"kart_basi": _r(sum(v for _, v in kart_maliyetleri) / len(kart_maliyetleri), 3) if kart_maliyetleri else None,
            "kart_medyan": _medyan([v for _, v in kart_maliyetleri]), "teslim_kart": len(kart_maliyetleri),
            "kart_maliyetleri": kart_maliyetleri[:15],
            "sohbet_basi": _r(sum(sohbet_usd) / len(sohbet_usd), 3) if sohbet_usd else None,
            "sohbet_medyan": _medyan(sohbet_usd), "sohbet_sayisi": len(sohbet_usd),
            "en_pahali": en_pahali, "uyarilar": sorted(uyarilar, key=lambda u: u["zaman"] or "", reverse=True)[:12]}


# ---------------------------------------------------------------- 7. skill getirisi

def _tasarruf_metni(metin: str) -> tuple[str | None, float | None]:
    satir = next((s.strip(" -*#") for s in metin.splitlines() if re.search(r"(?i)tasarruf", s)), None)
    usd = None
    if satir:
        m = re.search(r"\$\s*([0-9]+(?:[.,][0-9]+)?)|([0-9]+(?:[.,][0-9]+)?)\s*\$", satir)
        if m:
            usd = float((m.group(1) or m.group(2)).replace(",", "."))
    return (satir[:200] if satir else None), usd


def _skill(sd: str, kayitlar: list[dict]) -> dict:
    olaylar = L.jsonl_oku(os.path.join(sd, "gunluk.jsonl"))
    kayitli_oturum = {o.get("oturum") for o in olaylar if o.get("oturum")}
    skill_oturum = collections.defaultdict(set)
    for o in olaylar:
        if o.get("tur") == "skill" and o.get("oturum"):
            skill_oturum[o["oturum"]].add(o.get("skill"))
    oturum_usd = collections.Counter()
    for r in kayitlar:
        if r.get("oturum") in kayitli_oturum:
            oturum_usd[r["oturum"]] += r.get("maliyet_usd") or 0.0
    ile = [v for o, v in oturum_usd.items() if o in skill_oturum]
    siz = [v for o, v in oturum_usd.items() if o not in skill_oturum and v > 0]
    # skill'li oturumlarda kart başı maliyet de karşılaştırılır (iş büyüklüğü farkını kısmen dengeler)
    kart_oturum = collections.Counter()
    for k in L.kartlar(sd):
        if k.get("oturum"):
            kart_oturum[k["oturum"]] += 1
    skill_sayaci = collections.Counter(s for ss in skill_oturum.values() for s in ss)

    adaylar = []
    for d in sorted(glob.glob(os.path.join(sd, "onerilen_skill", "*"))):
        if not os.path.isdir(d):
            continue
        metin = ""
        for ad in ("GEREKCE.md", "SKILL.md"):
            try:
                with open(os.path.join(d, ad), encoding="utf-8") as f:
                    metin += f.read() + "\n"
            except OSError:
                pass
        satir, usd = _tasarruf_metni(metin)
        siklik = re.search(r"(?i)(\d+)\s*(?:kez|kere|defa|tekrar)", metin)
        adaylar.append({"ad": os.path.basename(d), "tasarruf_metni": satir, "tasarruf_usd": usd,
                        "siklik": int(siklik.group(1)) if siklik else None,
                        "zaman": datetime.datetime.fromtimestamp(os.path.getmtime(d)).astimezone().isoformat(timespec="minutes")})
    return {"ile": {"oturum": len(ile), "ort_usd": _ort(ile), "medyan_usd": _medyan(ile)},
            "siz": {"oturum": len(siz), "ort_usd": _ort(siz), "medyan_usd": _medyan(siz)},
            "fark_ort": _r((_ort(siz) or 0) - (_ort(ile) or 0), 2) if ile and siz else None,
            "kullanim": dict(skill_sayaci.most_common(12)), "adaylar": adaylar,
            "aday_tasarruf_toplam": _r(sum(a["tasarruf_usd"] or 0 for a in adaylar), 2),
            "not": "Skill olayı günlüğe 13.10'dan beri yazılıyor; örneklem küçükken fark yönsel okunmalı."}


# ---------------------------------------------------------------- 8. sağlık

def _saglik(sd: str, proje: str, kayitlar: list[dict]) -> dict:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import ruya  # noqa: E402
    hafiza = os.path.join(ruya.hafiza_dizini(proje), "MEMORY.md")
    h = {"yol": hafiza, "var": os.path.exists(hafiza), "satir": 0, "bayt": 0,
         "satir_sinir": HAFIZA_SATIR_SINIRI, "bayt_sinir": HAFIZA_BAYT_SINIRI, "dosya": 0, "toplam_bayt": 0}
    if h["var"]:
        with open(hafiza, "rb") as f:
            veri = f.read()
        h["satir"] = veri.count(b"\n") + (0 if veri.endswith(b"\n") else 1)
        h["bayt"] = len(veri)
        konu = [p for p in glob.glob(os.path.join(os.path.dirname(hafiza), "*.md")) if not p.endswith("MEMORY.md")]
        h["dosya"] = len(konu)
        h["toplam_bayt"] = sum(os.path.getsize(p) for p in konu) + len(veri)
        h["en_buyuk"] = sorted(([os.path.basename(p), os.path.getsize(p)] for p in konu), key=lambda x: -x[1])[:3]
    h["doluluk"] = _r(max(h["satir"] / HAFIZA_SATIR_SINIRI, h["bayt"] / HAFIZA_BAYT_SINIRI), 3)
    h["seviye"] = "kritik" if h["doluluk"] >= 0.9 else "uyari" if h["doluluk"] >= 0.7 else "iyi"

    rd = ruya.durum(sd)
    hatalar = sorted(glob.glob(os.path.join(sd, "ruya", "ruya_hata_*.md")))
    r = {"son": rd.get("son_ruya"), "gun_once": rd.get("gun_once"), "zamani_geldi": rd.get("zamani_geldi"),
         "oturum_sayaci": rd.get("oturum_sayaci"), "okunmamis_rapor": bool(rd.get("okunmamis_rapor")),
         "son_hata": os.path.basename(hatalar[-1]) if hatalar else None}
    r["seviye"] = "uyari" if rd.get("zamani_geldi") or r["gun_once"] is None else "iyi"

    sinir = datetime.datetime.now().astimezone() - datetime.timedelta(days=7)
    alt = [x for x in kayitlar if x.get("agent_id") and x.get("kaynak") != "gecmis"
           and (_zaman(x.get("zaman")) or sinir) >= sinir]

    def etiketsiz(x):
        if x.get("surec") in (None, "bilinmiyor"):
            return True
        return _rol(x.get("ajan")) in ("isci", "denetci") and x.get("gorev") in (None, "-")
    ets = [x for x in alt if etiketsiz(x)]
    e = {"kosu": len(alt), "etiketsiz": len(ets), "oran": _r(len(ets) / len(alt), 3) if alt else None,
         "ajanlar": dict(collections.Counter(x.get("ajan") for x in ets).most_common(5))}
    e["seviye"] = "uyari" if (e["oran"] or 0) > 0.2 else "iyi"

    olaylar = L.jsonl_oku(os.path.join(sd, "gunluk.jsonl"))
    hh = [o for o in olaylar if o.get("tur") == "hook-hatasi"]
    hh7 = [o for o in hh if (_zaman(o.get("zaman")) or sinir) >= sinir]
    k = {"toplam": len(hh), "son7": len(hh7), "son": hh[-1] if hh else None,
         "olaylar": dict(collections.Counter(o.get("olay") for o in hh7).most_common(5))}
    k["seviye"] = "kritik" if len(hh7) >= 5 else "uyari" if hh7 else "iyi"
    return {"hafiza": h, "ruya": r, "etiketsiz": e, "hook": k}


# ---------------------------------------------------------------- tek alan / tüm alanlar

def olustur(sd: str, proje: str) -> dict:
    kayitlar = L.maliyet_kayitlari(sd)
    kartlar = L.kartlar(sd)
    bugun = datetime.date.today()
    try:
        sohbet_ham = L.sohbetler(sd, proje, limit=60, tahmin=True)
    except TypeError:  # eski ork_lib
        sohbet_ham = L.sohbetler(sd, proje, limit=60)
    sohbetler = [{"oturum": s["oturum"], "baslik": s["baslik"],
                  "usd": s.get("motor_usd") or s.get("defter_usd") or s.get("tahmin_usd") or 0.0} for s in sohbet_ham]
    trend = _trend(kayitlar, bugun)
    return {
        "surum": 1, "uretim": L.simdi(), "proje": os.path.basename(os.path.abspath(proje)), "yol": os.path.abspath(proje),
        "trend": trend, "kota": _kota(), "basamak": _basamak(kartlar, kayitlar), "tasarruf": _tasarruf(kayitlar),
        "akis": _akis(kartlar, kayitlar), "birim": _birim(kartlar, kayitlar, sohbetler, trend),
        "skill": _skill(sd, kayitlar), "saglik": _saglik(sd, proje, kayitlar),
    }


def _alan_listesi() -> list[dict]:
    if hasattr(L, "calisma_alanlari"):
        return L.calisma_alanlari()
    kok = os.path.join(os.path.expanduser("~"), ".claude", "projects")
    return [{"id": os.path.basename(d), "ad": os.path.basename(d), "yol": None, "orkestra": False}
            for d in glob.glob(os.path.join(kok, "*")) if os.path.isdir(d)]


def tum_alanlar() -> dict:
    """Bütün çalışma alanlarının toplamı ve karşılaştırması. Orkestralı alan: token defteri; diğerleri: sohbet maliyeti."""
    bugun = datetime.date.today()
    hafta_bas = bugun - datetime.timedelta(days=6)
    ay = bugun.strftime("%Y-%m")
    satirlar, gunluk = [], collections.defaultdict(lambda: collections.Counter())
    en_erken = [bugun]  # en erken kayıt günü (30 günlük pencereden önceki kayıtlar da sayılır)
    for a in _alan_listesi():
        s = {"id": a["id"], "ad": a["ad"], "yol": a.get("yol"), "orkestra": a.get("orkestra"), "son": a.get("son"),
             "bugun": 0.0, "hafta": 0.0, "ay": 0.0, "toplam": 0.0, "model": collections.Counter(),
             "kart": 0, "teslim": 0, "sohbet": a.get("sohbet"), "kaynak": "defter" if a.get("orkestra") else "sohbet"}
        try:
            if a.get("orkestra") and a.get("yol"):
                sd = os.path.join(a["yol"], ".claude", "orkestra")
                for r in L.maliyet_kayitlari(sd):
                    z = _zaman(r.get("zaman"))
                    usd = r.get("maliyet_usd") or 0.0
                    if not z:
                        continue
                    d = z.date()
                    en_erken.append(d)
                    s["toplam"] += usd
                    s["model"][_kisa_model(r.get("model"))] += usd
                    s["bugun"] += usd if d == bugun else 0
                    s["hafta"] += usd if d >= hafta_bas else 0
                    s["ay"] += usd if d.strftime("%Y-%m") == ay else 0
                    if d >= bugun - datetime.timedelta(days=29):
                        gunluk[d.isoformat()][a["ad"]] += usd
                ks = L.kartlar(sd)
                s["kart"] = len(ks)
                s["teslim"] = sum(1 for k in ks if L.kart_durumu_hesapla(k) == "teslim")
            else:
                dizin = os.path.join(os.path.expanduser("~"), ".claude", "projects", a["id"])
                try:
                    ls = L.sohbetler(None, a.get("yol") or dizin, limit=60, tahmin=True, oturum_dizini=dizin)
                except TypeError:
                    ls = []
                for c in ls:
                    usd = c.get("motor_usd") or c.get("tahmin_usd") or 0.0
                    z = _zaman(c.get("son"))
                    s["toplam"] += usd
                    for m, v in (c.get("modeller") or {}).items():
                        s["model"][_kisa_model(m)] += v
                    if z:
                        d = z.date()
                        en_erken.append(d)
                        s["bugun"] += usd if d == bugun else 0
                        s["hafta"] += usd if d >= hafta_bas else 0
                        s["ay"] += usd if d.strftime("%Y-%m") == ay else 0
                        if d >= bugun - datetime.timedelta(days=29):
                            gunluk[d.isoformat()][a["ad"]] += usd
        except Exception as e:  # noqa: BLE001
            s["hata"] = f"{type(e).__name__}: {e}"[:200]
        for k in ("bugun", "hafta", "ay", "toplam"):
            s[k] = _r(s[k], 2)
        s["model"] = {m: _r(v, 2) for m, v in s["model"].most_common(5)}
        satirlar.append(s)
    satirlar.sort(key=lambda s: -s["toplam"])
    gunler = []
    d = max(min(en_erken), bugun - datetime.timedelta(days=29))  # ilk kayıt gününden başlar, öncesi boş gün yok
    while d <= bugun:
        gunler.append({"donem": d.isoformat(), "alan": {k: _r(v, 2) for k, v in gunluk.get(d.isoformat(), {}).items()}})
        d += datetime.timedelta(days=1)
    return {"uretim": L.simdi(), "alanlar": satirlar, "gunluk": gunler,
            "toplam": {k: _r(sum(s[k] for s in satirlar), 2) for k in ("bugun", "hafta", "ay", "toplam")},
            "kota": _kota(),
            "not": "Orkestralı alanlarda token defteri, diğerlerinde sohbet maliyeti (Claude'un hesabı ya da transkript tahmini). "
                   "Sohbet maliyeti son etkinlik gününe yazılır."}


def alan_analitigi(alan_id: str | None) -> dict:
    alanlar = [a for a in _alan_listesi() if a.get("orkestra")]
    alan = next((a for a in alanlar if a["id"] == alan_id), None) or (alanlar[0] if alanlar else None)
    if alan is None:
        sd = L.durum_dizini()
        if not sd:
            return {"hata": "Orkestra kurulu çalışma alanı bulunamadı."}
        return olustur(sd, os.path.dirname(os.path.dirname(sd)))
    o = olustur(os.path.join(alan["yol"], ".claude", "orkestra"), alan["yol"])
    o["alan"] = {"id": alan["id"], "ad": alan["ad"]}
    o["alanlar"] = [{"id": a["id"], "ad": a["ad"]} for a in alanlar]
    return o


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--tum":
        print(json.dumps(tum_alanlar(), ensure_ascii=False, indent=1))
    else:
        proje = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else L.proje_dizini()
        sd = os.path.join(proje, ".claude", "orkestra")
        if not os.path.isdir(sd):
            sys.exit(f"orkestra kurulu değil: {proje}")
        print(json.dumps(olustur(sd, proje), ensure_ascii=False, indent=1))
