"""Orkestra analitiği: zaman içinde harcama, kota, basamak verimliliği, ya-şöyle-olsaydı tasarrufu, kart akışı,
birim maliyet, skill getirisi, sağlık ve tüm çalışma alanlarının karşılaştırması.

Yalnız okur; kaynaklar:
  <durum>/maliyet.jsonl, gorevler/*.json, gunluk.jsonl, perspektif/durum.json, onerilen_skill/*   (proje)
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
import math
import os
import re
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ork_lib as L  # noqa: E402
import ret_nedeni as RN  # noqa: E402

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


def _ek(satirlar: list[dict]) -> dict:
    """Her kıyas satırına eklenen ikili ölçü: token bazlı ve USD bazlı, dört kalemle (I-064). 'token' = dört kalemin ham
    toplamı; 'kalem' = ork_lib.kalemler (token ve usd, giris/cikis/onbellek_okuma/onbellek_yazma/toplam)."""
    k = L.kalemler(satirlar)
    return {"token": k["token"]["toplam"], "kalem": k}


def _formul_usd(r: dict, model: str) -> float:
    """Satırın token sayılarından verilen modelin liste fiyatıyla maliyet (önbellek yazma 1 sa tarifesiyle; defterdeki hook ve tur satırlarıyla aynı)."""
    f = L.model_fiyati(model)
    return ((r.get("giris") or 0) * f["giris"] + (r.get("cikis") or 0) * f["cikis"]
            + (r.get("onbellek_okuma") or 0) * f["onbellek_okuma"]
            + (r.get("onbellek_yazma") or 0) * f["onbellek_yazma_1sa"]) / 1_000_000


AJAN_ADLARI = {
    "ana-ajan": "Ana ajan", "ana": "Ana ajan", "orkestra:denetci": "Denetçi", "orkestra:arastirmaci": "Araştırmacı",
    "orkestra:triyaj": "Triyaj", "orkestra:perspektif-ajani": "Perspektif ajanı", "orkestra:ruya-ajani": "Perspektif ajanı", "orkestra:skill-avcisi": "Skill avcısı",
    "orkestra:hafiza-bakimcisi": "Hafıza bakımcısı", "orkestra:arsivci": "Arşivci", "general-purpose": "Genel alt ajan",
    "Explore": "Keşif ajanı", "Plan": "Plan ajanı", "claude-code-guide": "Claude Code rehberi",
}
SUREC_ADLARI = {
    "orkestrasyon": "planlama ve koordinasyon", "is": "işçi çalışması", "denetim": "denetim", "duzeltme": "düzeltme",
    "arastirma": "araştırma", "sentez": "sentez", "perspektif": "perspektif (bakım)", "ruya": "perspektif (bakım)", "gecmis-ana": "orkestra öncesi · ana ajan",
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
    if "perspektif" in a or "ruya" in a or "skill-avcisi" in a or "hafiza" in a:
        return "bakim"
    return "diger"


# ---------------------------------------------------------------- 1. zaman içinde harcama

def _trend(kayitlar: list[dict], bugun: datetime.date) -> dict:
    gun = collections.defaultdict(lambda: {"usd": 0.0, "model": collections.Counter(), "satir": []})
    for r in kayitlar:
        z = _zaman(r.get("zaman"))
        if not z:
            continue
        g = gun[z.date()]
        usd = r.get("maliyet_usd") or 0.0
        g["usd"] += usd
        g["model"][_kisa_model(r.get("model"))] += usd
        g["satir"].append(r)

    def kume(anahtar):
        out = collections.defaultdict(lambda: {"usd": 0.0, "model": collections.Counter(), "satir": []})
        for d, g in gun.items():
            k = anahtar(d)
            out[k]["usd"] += g["usd"]
            out[k]["model"].update(g["model"])
            out[k]["satir"].extend(g["satir"])
        return [{"donem": k, "usd": _r(v["usd"]), "model": {m: _r(u) for m, u in v["model"].items() if u}, **_ek(v["satir"])}
                for k, v in sorted(out.items())]

    ilk = min(gun) if gun else bugun
    bas = max(ilk, bugun - datetime.timedelta(days=59))
    gunluk = []
    d = bas
    while d <= bugun:  # boş günler de görünsün
        g = gun.get(d, {"usd": 0.0, "model": {}, "satir": []})
        gunluk.append({"donem": d.isoformat(), "usd": _r(g["usd"]), "model": {m: _r(u) for m, u in g["model"].items() if u},
                       **_ek(g["satir"])})
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
    yeterli = aktif_gun >= 7  # 7 günden az veriyle ay sonu tahmini yanıltıcı
    tahmin_ort = simdiye + (simdiye / aktif_gun) * kalan if aktif_gun else 0.0
    tahmin_7g = simdiye + (son7 / son7_gun) * kalan if son7_gun else 0.0
    onceki_ay = (ay_bas - datetime.timedelta(days=1)).strftime("%Y-%m")
    return {
        "gunluk": gunluk, "haftalik": haftalik, "aylik": aylik,
        "ay_sonu": {"ay": bugun.strftime("%Y-%m"), "simdiye": _r(simdiye, 2), "gecen_gun": gecen, "ay_gun": ay_gun,
                    "veri_gun": aktif_gun, "gunluk_ort": _r(simdiye / aktif_gun if aktif_gun else 0, 2),
                    "son7_gunluk": _r(son7 / son7_gun if son7_gun else 0, 2) if son7_gun >= 7 else None,
                    "tahmin_ort": _r(tahmin_ort, 2) if yeterli else None, "tahmin_7g": _r(tahmin_7g, 2) if yeterli and son7_gun >= 7 else None,
                    "tahmin_yeterli": yeterli,
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

def son_basamak(kart: dict) -> str | None:
    """Kartın son basamağı: gecmis'teki is-bitti olaylarının en yüksek 'isci-tN' ajanı (K09).
    is-bitti yoksa 'basamak', o da yoksa 'baslangic_basamak'."""
    en = 0
    for g in kart.get("gecmis") or []:
        if g.get("olay") != "is-bitti":
            continue
        # kayıtta ajan_tipi 'orkestra:isci-t3' biçiminde; eklenti öneki isteğe bağlı
        m = re.fullmatch(r"(?:[\w-]+:)?isci-t(\d+)", str(g.get("ajan") or "").strip().lower())
        if m:
            en = max(en, int(m.group(1)))
    if en:
        return f"T{en}"
    return kart.get("basamak") or kart.get("baslangic_basamak")


def _basamak(kartlar: list[dict], kayitlar: list[dict]) -> dict:
    satir = {b: {"basamak": b, "kart": 0, "teslim": 0, "denetlenen": 0, "ilk_gecis": 0, "denetim": 0, "ret": 0,
                 "yukseltilen": 0, "usd": 0.0} for b in BASAMAK_SIRASI}
    kart_usd = collections.Counter()
    kart_satir = collections.defaultdict(list)
    for r in kayitlar:
        if r.get("gorev") not in (None, "-"):
            kart_usd[r["gorev"]] += r.get("maliyet_usd") or 0.0
            kart_satir[r["gorev"]].append(r)
    basamak_satir = {b: [] for b in BASAMAK_SIRASI}
    teslim, kucuk = 0, 0
    for k in kartlar:
        bas = k.get("baslangic_basamak") or k.get("basamak")
        son = son_basamak(k) or bas
        if bas not in satir:
            continue
        s = satir[bas]
        s["kart"] += 1
        s["usd"] += kart_usd.get(k["id"], 0.0)
        basamak_satir[bas].extend(kart_satir.get(k["id"], []))
        yukseldi = bas != son or any(g.get("olay") == "yukseltme" for g in k.get("gecmis", []))
        s["yukseltilen"] += int(yukseldi)
        dnt = sorted(k.get("denetimler") or [], key=lambda d: (d.get("sira", 0), d.get("zaman", "")))
        if k.get("durum") == "iptal":
            dnt = []   # iptal kartın kararları ret oranına girmez (KPI ret_orani ile aynı tanım)
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
        s.update(_ek(basamak_satir[s["basamak"]]))
        s["kart_basi_token"] = _r(s["token"] / s["kart"], 1) if s["kart"] else None

    # işçi harcamasının (süreç 'is') model payı
    is_usd = collections.Counter()
    is_token = collections.Counter()
    for r in kayitlar:
        if r.get("surec") in ("is", "duzeltme") or _rol(r.get("ajan")) == "isci":
            is_usd[_kisa_model(r.get("model"))] += r.get("maliyet_usd") or 0.0
            is_token[_kisa_model(r.get("model"))] += sum(int(r.get(a) or 0) for a in L._TOKEN_ALANLARI)
    toplam_is = sum(is_usd.values())
    kucuk_usd = sum(v for m, v in is_usd.items() if m.startswith(("haiku", "sonnet")))
    return {
        "hedef": KUCUK_BASAMAK_HEDEFI, "teslim_kart": teslim,
        "kucuk_pay_kart": _r(kucuk / teslim, 3) if teslim else None,
        "kucuk_pay_is_usd": _r(kucuk_usd / toplam_is, 3) if toplam_is else None,
        "is_model_usd": {m: _r(v) for m, v in is_usd.most_common()},
        "is_model_token": {m: is_token[m] for m, _ in is_usd.most_common()},
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
        return {"ad": ad, "aciklama": aciklama, "kosu": len(sec), "gercek": _r(gercek, 2), **_ek(sec),
                "sonnet_olsa": _r(gercek * oran, 2), "fark": _r(gercek * (1 - oran), 2),
                "oran": _r(1 - oran, 3)}

    senaryolar = [
        senaryo(lambda r: _rol(r.get("ajan")) in ("isci", "diger"), "Opus'taki alt ajan işleri",
                "İşçi ve genel amaçlı alt ajanlar; denetçi işçinin üstünde kalmalı diye hariç."),
        senaryo(lambda r: _rol(r.get("ajan")) != "ana", "Bütün alt ajanlar", "Denetçiler dahil."),
        senaryo(lambda r: True, "Ana ajan dahil hepsi", "Planlama da Sonnet'te olsaydı."),
    ]
    # önbellek: okunan token tam giriş fiyatıyla okunsaydı; yazmanın giriş fiyatından fazlası (1 sa tarifesi) düşülür
    kazanc = ek_yazma = 0.0
    okuma = yazma = 0
    model_kazanc = collections.Counter()
    for r in kayitlar:
        f = L.model_fiyati(r.get("model"))
        o, w = r.get("onbellek_okuma") or 0, r.get("onbellek_yazma") or 0
        k = o * (f["giris"] - f["onbellek_okuma"]) / 1e6
        e = w * (f["onbellek_yazma_1sa"] - f["giris"]) / 1e6  # defter satırları 1 sa tarifesiyle fiyatlanır
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
                         "okuma_token": okuma, "yazma_token": yazma, "kalem": L.kalemler(kayitlar),
                         "model": {m: _r(v, 2) for m, v in model_kazanc.most_common()}}}


# ---------------------------------------------------------------- 5. kart akışı

UZUN_BEKLEME_DK = 30   # kuyruk ve denetçi başlamayı bekleme için işaret eşiği (panelde ⚠)


def _denetci_basi(kart_id: str, kayitlar: list[dict], bitis, karar) -> datetime.datetime | None:
    """Denetim-basladi olayı olmayan eski turlarda denetçi koşu kaydından başlangıç: [bitis, karar] içinde başlayan ilk koşu."""
    adaylar = []
    for r in kayitlar:
        if r.get("gorev") != kart_id or _rol(r.get("ajan")) != "denetci" or not r.get("sure_ms"):
            continue
        bit = _zaman(r.get("zaman"))
        if bit:
            bas = bit - datetime.timedelta(milliseconds=r["sure_ms"])
            if bitis - datetime.timedelta(minutes=1) <= bas <= karar:
                adaylar.append(bas)
    return min(adaylar) if adaylar else None


def _akis(kartlar: list[dict], kayitlar: list[dict]) -> dict:
    out = []
    for k in kartlar:
        g = sorted(k.get("gecmis") or [], key=lambda x: x.get("zaman", ""))
        olus = _zaman(k.get("olusturma")) or (_zaman(g[0]["zaman"]) if g else None)
        ilk_is = next((_zaman(x["zaman"]) for x in g if x.get("olay") == "isleniyor"), None)
        teslim = next((_zaman(x["zaman"]) for x in g if x.get("olay") == "teslim"), None)
        bekleme, calisma, toplam_den, is_sure = [], [], [], []
        ayrildi = True       # her denetim turunda denetçinin başlangıcı biliniyor mu
        bas_is = None
        for i, x in enumerate(g):
            if x.get("olay") == "isleniyor":
                bas_is = _zaman(x["zaman"])
            if x.get("olay") == "is-bitti":
                bitis = _zaman(x["zaman"])
                if bas_is:
                    is_sure.append(_dk(bas_is, bitis))
                    bas_is = None
                j = next((n for n in range(i + 1, len(g)) if str(g[n].get("olay", "")).startswith("denetim:")), None)
                # denetimsiz tekrar is-bitti: bekleme son is-bitti'den sayılır, ara olaylar çifte sayılmaz
                if j is not None and any(y.get("olay") == "is-bitti" for y in g[i + 1:j]):
                    continue
                d = _zaman(g[j]["zaman"]) if j is not None else None
                if d:
                    toplam_den.append(_dk(bitis, d))
                    zamanlar = [_zaman(y.get("zaman")) for y in g[i + 1:] if y.get("olay") == "denetim-basladi"]
                    b = next((t for t in zamanlar if t and bitis <= t <= d), None)
                    b = b or _denetci_basi(k["id"], kayitlar, bitis, d)
                    if b:
                        bekleme.append(_dk(bitis, b))
                        calisma.append(_dk(b, d))
                    else:
                        ayrildi = False
                    bas_is = d  # sonraki düzeltme turu denetim kararından başlar
        son_bitti = max((i for i, y in enumerate(g) if y.get("olay") == "is-bitti"), default=None)
        out.append({"id": k["id"], "baslik": (k.get("baslik") or "")[:70], "basamak": k.get("basamak"),
                    "durum": L.kart_durumu_hesapla(k), "olusturma": k.get("olusturma"),
                    "kuyruk_dk": _dk(olus, ilk_is), "is_dk": _r(sum(v for v in is_sure if v), 1) if is_sure else None,
                    "denetim_bekleme_dk": _r(sum(v for v in bekleme if v), 1) if bekleme and ayrildi else None,
                    "denetim_calisma_dk": _r(sum(v for v in calisma if v), 1) if calisma and ayrildi else None,
                    "denetim_toplam_dk": _r(sum(v for v in toplam_den if v), 1) if toplam_den else None,
                    "denetim_basladi": any(y.get("olay") == "denetim-basladi" for y in g[son_bitti:]) if son_bitti is not None else False,
                    "tur": len([x for x in g if x.get("olay") == "is-bitti"]),
                    "toplam_dk": _dk(olus, teslim)})
    teslimler = [k for k in out if k["toplam_dk"] is not None]
    ozet = {"kart": len(teslimler),
            "toplam_ort": _ort([k["toplam_dk"] for k in teslimler]), "toplam_medyan": _medyan([k["toplam_dk"] for k in teslimler]),
            "kuyruk_ort": _ort([k["kuyruk_dk"] for k in teslimler]), "is_ort": _ort([k["is_dk"] for k in teslimler]),
            "denetim_bekleme_ort": _ort([k["denetim_bekleme_dk"] for k in teslimler]),
            "denetim_calisma_ort": _ort([k["denetim_calisma_dk"] for k in teslimler]),
            "denetim_toplam_ort": _ort([k["denetim_toplam_dk"] for k in teslimler]),
            "denetim_ayrilan": len([k for k in teslimler if k["denetim_bekleme_dk"] is not None])}
    # medyan: birkaç uzun bekleyen kart ortalamayı şişirir; darboğaz medyana göre, uzun bekleyenler ayrıca sayılır
    for ad, alan in (("kuyruk", "kuyruk_dk"), ("is", "is_dk"), ("denetim_bekleme", "denetim_bekleme_dk"),
                     ("denetim_calisma", "denetim_calisma_dk")):
        ozet[ad + "_medyan"] = _medyan([k[alan] for k in teslimler])
    ozet["uzun_esik_dk"] = UZUN_BEKLEME_DK
    ozet["kuyruk_uzun"] = len([k for k in teslimler if (k["kuyruk_dk"] or 0) > UZUN_BEKLEME_DK])
    ozet["denetim_uzun"] = len([k for k in teslimler if (k["denetim_bekleme_dk"] or 0) > UZUN_BEKLEME_DK])
    asamalar = {"kuyruk": ozet["kuyruk_medyan"] or 0, "is": ozet["is_medyan"] or 0,
                "denetim bekleme": ozet["denetim_bekleme_medyan"] or 0, "denetim calisma": ozet["denetim_calisma_medyan"] or 0}
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
    kart_tok = collections.Counter()
    kart_satir = collections.defaultdict(list)
    for r in kayitlar:
        if r.get("gorev") not in (None, "-"):
            kart_usd[r["gorev"]] += r.get("maliyet_usd") or 0.0
            kart_tok[r["gorev"]] += sum(int(r.get(a) or 0) for a in L._TOKEN_ALANLARI)
            kart_satir[r["gorev"]].append(r)
    teslim = [k for k in kartlar if L.kart_durumu_hesapla(k) == "teslim"]
    kart_maliyetleri = sorted(([k["id"], _r(kart_usd.get(k["id"], 0.0))] for k in teslim), key=lambda x: -x[1])
    kart_tokenleri = [kart_tok.get(k["id"], 0) for k in teslim]
    teslim_satir = [r for k in teslim for r in kart_satir.get(k["id"], [])]
    sohbet_usd = [s["usd"] for s in sohbetler if s.get("usd")]

    kosular = []
    for r in kayitlar:
        if not r.get("agent_id"):
            continue  # ana ajan satırları tur/oturum toplamıdır, ajan koşusu değil
        kosular.append({"zaman": r.get("zaman"), "ajan": r.get("ajan"), "gorev": r.get("gorev"), "surec": r.get("surec"),
                        "model": _kisa_model(r.get("model")), "usd": _r(r.get("maliyet_usd") or 0.0), **_ek([r]),
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
            "kart_basi_token": _r(sum(kart_tokenleri) / len(kart_tokenleri), 1) if kart_tokenleri else None,
            "kart_medyan_token": _medyan(kart_tokenleri), "kart_kalem": L.kalemler(teslim_satir),
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
    oturum_tok = collections.Counter()
    for r in kayitlar:
        if r.get("oturum") in kayitli_oturum:
            oturum_usd[r["oturum"]] += r.get("maliyet_usd") or 0.0
            oturum_tok[r["oturum"]] += sum(int(r.get(a) or 0) for a in L._TOKEN_ALANLARI)
    ile = [v for o, v in oturum_usd.items() if o in skill_oturum]
    siz = [v for o, v in oturum_usd.items() if o not in skill_oturum and v > 0]
    ile_tok = [oturum_tok[o] for o in oturum_usd if o in skill_oturum]
    siz_tok = [oturum_tok[o] for o, v in oturum_usd.items() if o not in skill_oturum and v > 0]
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
    return {"ile": {"oturum": len(ile), "ort_usd": _ort(ile), "medyan_usd": _medyan(ile),
                    "ort_token": _ort(ile_tok), "medyan_token": _medyan(ile_tok)},
            "siz": {"oturum": len(siz), "ort_usd": _ort(siz), "medyan_usd": _medyan(siz),
                    "ort_token": _ort(siz_tok), "medyan_token": _medyan(siz_tok)},
            "fark_ort": _r((_ort(siz) or 0) - (_ort(ile) or 0), 2) if ile and siz else None,
            "fark_ort_token": _r((_ort(siz_tok) or 0) - (_ort(ile_tok) or 0), 0) if ile and siz else None,
            "kullanim": dict(skill_sayaci.most_common(12)), "adaylar": adaylar,
            "aday_tasarruf_toplam": _r(sum(a["tasarruf_usd"] or 0 for a in adaylar), 2),
            "not": "Skill olayı günlüğe 13.10'dan beri yazılıyor; örneklem küçükken fark yönsel okunmalı."}


# ---------------------------------------------------------------- 8. sağlık

def _saglik(sd: str, proje: str, kayitlar: list[dict]) -> dict:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import perspektif  # noqa: E402
    hafiza = os.path.join(perspektif.hafiza_dizini(proje), "MEMORY.md")
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

    rd = perspektif.durum(sd)
    hatalar = sorted(glob.glob(os.path.join(sd, "perspektif", "perspektif_hata_*.md")))
    r = {"son": rd.get("son_perspektif"), "gun_once": rd.get("gun_once"), "zamani_geldi": rd.get("zamani_geldi"),
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
    return {"hafiza": h, "perspektif": r, "etiketsiz": e, "hook": k}


# ---------------------------------------------------------------- tek alan / tüm alanlar

def _sinif(k: dict) -> str:
    s = k.get("sinif")
    return s if s and s != "-" else "sınıfsız"


def _ders(kartlar: list[dict], kayitlar: list[dict]) -> dict:
    """Ret nedenleri (sınıf x basamak) ve verim (sınıf x başlangıç basamağı)."""
    kart_usd = collections.Counter()
    for r in kayitlar:
        if r.get("gorev") not in (None, "-"):
            kart_usd[r["gorev"]] += r.get("maliyet_usd") or 0.0
    ned: dict = {}
    ver: dict = {}
    for k in kartlar:
        sinif = _sinif(k)
        bas = k.get("baslangic_basamak") or k.get("basamak")
        for d in [] if k.get("durum") == "iptal" else k.get("denetimler") or []:   # iptal kartın retleri sayılmaz
            if d.get("karar") != "ret":
                continue
            kod = d.get("neden")
            kod = kod if kod in RN.NEDENLER else RN.SINIFLANMAMIS
            e = ned.setdefault((sinif, d.get("basamak") or bas),
                               {"ret": 0, "nedenler": collections.Counter(), "kok": collections.Counter()})
            e["ret"] += 1
            e["nedenler"][kod] += 1
            e["kok"][RN.kok(kod)] += 1
        v = ver.setdefault((sinif, bas), {"kart": 0, "onaylanan": 0, "tur": 0, "usd": 0.0})
        v["kart"] += 1
        v["tur"] += sum(1 for g in k.get("gecmis") or [] if g.get("olay") == "is-bitti")
        v["usd"] += kart_usd.get(k.get("id"), 0.0)
        v["onaylanan"] += int(k.get("durum") in ("onaylandi", "teslim")
                              or L.kart_durumu_hesapla(k) in ("onaylandi", "teslim"))

    def _sira(a):
        return tuple(str(x) for x in a[0])

    nedenler = [{"sinif": s, "basamak": b, "ret": e["ret"], "nedenler": dict(e["nedenler"]), "kok": dict(e["kok"])}
                for (s, b), e in sorted(ned.items(), key=_sira)]
    verim = [{"sinif": s, "baslangic_basamak": b, "kart": v["kart"], "onaylanan": v["onaylanan"],
              "ort_tur": round(v["tur"] / v["kart"], 2), "toplam_usd": _r(v["usd"]),
              "onayli_is_basi_usd": _r(v["usd"] / v["onaylanan"]) if v["onaylanan"] else None}
             for (s, b), v in sorted(ver.items(), key=_sira)]
    kart_t = sum(v["kart"] for v in ver.values())
    onay_t = sum(v["onaylanan"] for v in ver.values())
    usd_t = sum(v["usd"] for v in ver.values())
    tur_t = sum(v["tur"] for v in ver.values())
    kod_t, kok_t = collections.Counter(), collections.Counter()
    for e in ned.values():
        kod_t.update(e["nedenler"])
        kok_t.update(e["kok"])
    return {
        "nedenler": nedenler, "verim": verim,
        "toplam": {"ret": sum(e["ret"] for e in ned.values()), "nedenler": dict(kod_t), "kok": dict(kok_t),
                   "kart": kart_t, "onaylanan": onay_t, "ort_tur": round(tur_t / kart_t, 2) if kart_t else None,
                   "toplam_usd": _r(usd_t), "onayli_is_basi_usd": _r(usd_t / onay_t) if onay_t else None},
    }


# ---------------------------------------------------------------- hedef panosu (5 ölçü) ve önlenebilir israf (K11)

AYAR_DIZINI = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ayarlar")
ONAYLI_DURUM = ("onaylandi", "teslim")
PENCERE_SIRASI = ("bugun", "son_3_gun", "son_7_gun", "bu_ay", "tum_zaman")
OLCU_SIRASI = ("ana_ajan_payi", "isci_cagrisi_kart", "onayli_kart_usd", "ret_orani", "teknik_not_kapsama")


def _ayar(ad: str, dizin: str | None = None) -> dict:
    """ayarlar/<ad>.json; yok ya da bozuksa boş sözlük."""
    try:
        with open(os.path.join(dizin or AYAR_DIZINI, ad), encoding="utf-8") as f:
            v = json.load(f)
        return v if isinstance(v, dict) else {}
    except (OSError, ValueError):
        return {}


def olcu_durumu(deger, spec: dict, uyari_carpani: float = 1.25, teknik_uyari_alt: float = 0.8) -> tuple:
    """(durum, yorum). deger None -> veri-yok. ust: <=hedef iyi, <=hedef*çarpan uyarı, üstü kötü.
    alt (ör. =1,0): >=hedef iyi, >=teknik_uyari_alt uyarı, altı kötü. band: [alt, ust] iyi; altı uyarı (gevsek-riski),
    üstü kötü (plan-kusuru)."""
    if deger is None:
        return "veri-yok", None
    tur = spec.get("tur")
    if tur == "band":
        if deger < spec["alt"]:
            return "uyari", "gevsek-riski"
        if deger > spec["ust"]:
            return "kotu", "plan-kusuru"
        return "iyi", None
    if tur == "alt":
        if deger >= spec["hedef"]:
            return "iyi", None
        return ("uyari" if deger >= teknik_uyari_alt else "kotu"), None
    if deger <= spec["hedef"]:
        return "iyi", None
    return ("uyari" if deger <= spec["hedef"] * uyari_carpani else "kotu"), None


def olcu_sapmasi(deger, spec: dict):
    """Hedeften sapma, ölçünün kendi biriminde. Artı = hedefin üstünde, eksi = altında; hedef (ya da bant) içindeyse 0.
    ust: deger - hedef (artı kötü). alt: deger - hedef (eksi kötü). band: bant dışına taşan miktar. Veri ya da hedef yoksa None."""
    if deger is None or not spec:
        return None
    if spec.get("tur") == "band":
        return deger - spec["ust"] if deger > spec["ust"] else (deger - spec["alt"] if deger < spec["alt"] else 0.0)
    if spec.get("hedef") is None:
        return None
    return deger - spec["hedef"]


def _kart_durum(k: dict) -> str:
    try:
        return L.kart_durumu_hesapla(k)
    except Exception:  # noqa: BLE001
        return k.get("durum") or ""


def _teknik_dolu(k: dict) -> bool:
    t = k.get("teknik")
    return bool(t.strip()) if isinstance(t, str) else bool(t)


def _ret_tur_maliyeti(k: dict, d: dict, usd_ajan: dict):
    """Ret alan işçi turunun maliyeti: denetimin sira'sından önceki en yakın is_turlari.agent_id'nin DEFTER maliyeti.
    Kartın token/maliyet alanı kullanılmaz. Tur bulunamazsa None."""
    sira = d.get("sira")
    turlar = [t for t in k.get("is_turlari") or [] if isinstance(t, dict) and t.get("agent_id")]
    if sira is not None:
        turlar = [t for t in turlar if t.get("sira", -1) < sira]
    if not turlar:
        return None
    t = max(turlar, key=lambda x: x.get("sira", -1))
    return usd_ajan.get(t["agent_id"], 0.0)


def onlenebilir_israf(kartlar: list, usd_ajan: dict, esik: dict) -> dict:
    siniflar: dict = {}
    esleme = esik.get("ret_sinifi") or {}
    israf_sinif = set(esik.get("israf_siniflari") or ["onlenebilir"])
    toplam = 0.0
    for k in kartlar:
        for d in k.get("denetimler") or []:
            if d.get("karar") != "ret":
                continue
            sinif = esleme.get(d.get("neden")) if isinstance(d.get("neden"), str) else None
            sinif = sinif or RN.SINIFLANMAMIS
            usd = _ret_tur_maliyeti(k, d, usd_ajan)
            e = siniflar.setdefault(sinif, {"ret": 0, "usd": 0.0, "tur_bulunamadi": 0})
            e["ret"] += 1
            if usd is None:
                e["tur_bulunamadi"] += 1
            else:
                e["usd"] += usd
                if sinif in israf_sinif:
                    toplam += usd
    for e in siniflar.values():
        e["usd"] = _r(e["usd"])
    return {"esik_surumu": esik.get("surum"), "onlenebilir_usd": _r(toplam), "siniflar": siniflar}


EK_SIRASI = ("ana_kirilim", "onayli_kart_toplam_usd", "onayli_kart_toplam_token", "toplam_kalem", "isci_dagilim", "onayli_usd_dagilim", "ilk_gecis_onay", "onbellek_isabet",
             "sinif_basina")


def _dagilim(x: list) -> dict:
    """Ortalamanın gizlediği kuyruk için: adet, medyan, P90 (en yakın sıra) ve en çok."""
    x = sorted(v for v in x if v is not None)
    n = len(x)
    if not n:
        return {"adet": 0, "medyan": None, "p90": None, "en_cok": None}
    med = x[n // 2] if n % 2 else (x[n // 2 - 1] + x[n // 2]) / 2
    return {"adet": n, "medyan": _r(med), "p90": _r(x[min(n - 1, int(round(0.9 * (n - 1))))]), "en_cok": _r(x[-1])}


def _onbellek_isabet(rs: list) -> dict:
    """Okunan önbellek / tüm giriş tokenı. Payda 0 ise deger None."""
    o = sum(r.get("onbellek_okuma") or 0 for r in rs)
    t = o + sum((r.get("giris") or 0) + (r.get("onbellek_yazma") or 0) for r in rs)
    return {"deger": _r(o / t) if t else None, "pay": o, "payda": t}


def ek_olculer(ks: list, rs: list, onayli: list) -> dict:
    """Hedefsiz ek ölçüler (hedef.json'a dokunmaz): ana ajan kırılımı, toplam maliyet, dağılımlar, ilk geçiş onayı,
    önbellek isabeti, iş sınıfı başına maliyet. ks pencere içindeki iptal olmayan kartlar, rs pencere içindeki defter satırları."""
    usd = lambda xs: sum(r.get("maliyet_usd") or 0.0 for r in xs)  # noqa: E731
    ana = [r for r in rs if L.ana_ajan_satiri_mi(r)]
    karta = [r for r in rs if not L.ana_ajan_satiri_mi(r)]
    persp = [r for r in ana if r.get("perspektif") or r.get("ruya")]
    kalan = [r for r in ana if not (r.get("perspektif") or r.get("ruya"))]
    kart_usd: dict = collections.defaultdict(float)
    kart_tok: dict = collections.defaultdict(int)
    for r in karta:
        kart_usd[r.get("gorev")] += r.get("maliyet_usd") or 0.0
        kart_tok[r.get("gorev")] += sum(int(r.get(a) or 0) for a in L._TOKEN_ALANLARI)
    toplam_tok = sum(int(r.get(a) or 0) for r in rs for a in L._TOKEN_ALANLARI)
    ilk = [next((d.get("karar") for d in k.get("denetimler") or [] if d.get("karar") in ("onay", "ret")), None) for k in ks]
    ilk = [x for x in ilk if x]
    sinif: dict = {}
    for k in ks:
        e = sinif.setdefault(str(k.get("sinif") or "-"), {"kart": 0, "usd": 0.0, "token": 0})
        e["kart"] += 1
        e["usd"] += kart_usd.get(k.get("id"), 0.0)
        e["token"] += kart_tok.get(k.get("id"), 0)
    isci = [len(k.get("isciler") or []) for k in ks]
    return {
        "ana_kirilim": {"is_bagli_usd": _r(usd([r for r in kalan if r.get("is")])), "is_bagsiz_usd": _r(usd([r for r in kalan if not r.get("is")])),
                        "perspektif_usd": _r(usd(persp)), "ana_usd": _r(usd(ana)), "toplam_usd": _r(usd(rs))},
        "onayli_kart_toplam_usd": {"deger": _r(usd(rs) / len(onayli)) if onayli else None, "pay": _r(usd(rs)), "payda": len(onayli)},
        "onayli_kart_toplam_token": {"deger": _r(toplam_tok / len(onayli), 1) if onayli else None, "pay": toplam_tok, "payda": len(onayli)},
        "toplam_kalem": L.kalemler(rs),
        "isci_dagilim": dict(_dagilim(isci), kart_ge4=sum(1 for x in isci if x >= 4)),
        "onayli_usd_dagilim": _dagilim([kart_usd.get(k.get("id"), 0.0) for k in onayli]),
        "ilk_gecis_onay": {"deger": _r(ilk.count("onay") / len(ilk)) if ilk else None, "pay": ilk.count("onay"), "payda": len(ilk)},
        "onbellek_isabet": {"ana": _onbellek_isabet(ana), "karta_bagli": _onbellek_isabet(karta)},
        "sinif_basina": {s: {"kart": e["kart"], "usd": _r(e["usd"]), "token": e["token"]} for s, e in sorted(sinif.items(), key=lambda kv: -kv[1]["usd"])},
    }


def hedef_panosu(kartlar: list, kayitlar: list, simdi=None, hedef: dict | None = None, esik: dict | None = None) -> dict:
    """5 hedef ölçüsü x PENCERE_SIRASI (bugun, son_3_gun, son_7_gun, bu_ay, tum_zaman) ve önlenebilir israf.
    Her ölçü {deger, hedef, durum, sapma, ornek, pay, payda}. Pencere: kart olusturma / defter satırı zamanı >= pencere başı
    (bugun: yerel gün başı, son_3_gun: simdi - pencere_gun, son_7_gun: simdi - 7 gün, bu_ay: ayın 1'i 00:00).
    Payda 0 -> deger None, durum veri-yok."""
    hedef = hedef if hedef is not None else _ayar("hedef.json")
    esik = esik if esik is not None else _ayar("kpi_esikleri.json")
    simdi = simdi or datetime.datetime.now().astimezone()
    gun = hedef.get("pencere_gun", 3)
    carpan = hedef.get("uyari_carpani", 1.25)
    t_alt = hedef.get("teknik_uyari_alt", 0.8)
    olculer = hedef.get("olculer") or {}
    kapi = _zaman(hedef["teknik_kapi_baslangic"] + "T00:00:00") if hedef.get("teknik_kapi_baslangic") else None
    if kapi is not None and kapi.tzinfo is None:
        kapi = kapi.replace(tzinfo=simdi.tzinfo)
    gun_basi = simdi.replace(hour=0, minute=0, second=0, microsecond=0)
    pencereler = {"bugun": gun_basi, "son_3_gun": simdi - datetime.timedelta(days=gun),
                  "son_7_gun": simdi - datetime.timedelta(days=7), "bu_ay": gun_basi.replace(day=1), "tum_zaman": None}

    usd_ajan: dict = collections.defaultdict(float)
    for r in kayitlar:
        if r.get("agent_id"):
            usd_ajan[r["agent_id"]] += r.get("maliyet_usd") or 0.0
    out: dict = {"surum": 1, "uretim": L.simdi(), "pencere_gun": gun,
                 "teknik_kapi_baslangic": hedef.get("teknik_kapi_baslangic"),
                 "olculer": {a: {} for a in OLCU_SIRASI}, "israf": {}, "ek": {a: {} for a in EK_SIRASI}}

    for ad, alt in pencereler.items():
        def icinde(z):
            if alt is None:
                return True
            zz = _zaman(z)
            return bool(zz and zz >= alt)
        ks = [k for k in kartlar if k.get("durum") != "iptal" and icinde(k.get("olusturma"))]
        rs = [r for r in kayitlar if icinde(r.get("zaman"))]
        onayli = [k for k in ks if _kart_durum(k) in ONAYLI_DURUM]
        usd_ana = sum(r.get("maliyet_usd") or 0.0 for r in rs if L.ana_ajan_satiri_mi(r))
        usd_tum = sum(r.get("maliyet_usd") or 0.0 for r in rs)
        onayli_idler = {k.get("id") for k in onayli}
        usd_onayli = sum(r.get("maliyet_usd") or 0.0 for r in rs if r.get("gorev") in onayli_idler)
        cagri = sum(len(k.get("isciler") or []) for k in ks)
        kararlar = [d.get("karar") for k in ks for d in k.get("denetimler") or [] if d.get("karar") in ("onay", "ret")]
        tk = []
        for k in onayli:
            z = _zaman(k.get("olusturma"))
            if kapi is not None and z is not None and z >= kapi:
                tk.append(k)
        ham = {
            "ana_ajan_payi": (usd_ana, usd_tum, len(rs)),
            "isci_cagrisi_kart": (cagri, len(ks), len(ks)),
            "onayli_kart_usd": (usd_onayli, len(onayli), len(onayli)),
            "ret_orani": (kararlar.count("ret"), len(kararlar), len(kararlar)),
            "teknik_not_kapsama": (sum(1 for k in tk if _teknik_dolu(k)), len(tk), len(tk)),
        }
        for o in OLCU_SIRASI:
            pay, payda, ornek = ham[o]
            deger = pay / payda if payda else None
            spec = olculer.get(o) or {}
            durum, yorum = olcu_durumu(deger, spec, carpan, t_alt) if spec else ("veri-yok", None)
            hd = [spec.get("alt"), spec.get("ust")] if spec.get("tur") == "band" else spec.get("hedef")
            sapma = olcu_sapmasi(deger, spec)
            e = {"deger": _r(deger) if deger is not None else None, "hedef": hd, "tur": spec.get("tur"), "durum": durum,
                 "sapma": _r(sapma) if sapma is not None else None, "ornek": ornek, "pay": _r(pay), "payda": _r(payda)}
            if yorum:
                e["yorum"] = yorum
            out["olculer"][o][ad] = e
        out["israf"][ad] = onlenebilir_israf(ks, usd_ajan, esik)
        for a, v in ek_olculer(ks, rs, onayli).items():
            out["ek"][a][ad] = v
    return out


# ---------------------------------------------------------------- baglam kırılımı

BELIRSIZ = "(belirsiz)"


def _oturum_baglami(sd: str, ad: str, onb: dict) -> str:
    if ad not in onb:
        try:
            with open(os.path.join(sd, "oturumlar", ad + ".json"), encoding="utf-8") as f:
                v = json.load(f).get("baglam")
        except (OSError, ValueError, AttributeError):
            v = None
        onb[ad] = v if isinstance(v, str) else ""
    return onb[ad]


def baglam_coz(sd: str, kayitlar: list[dict]) -> list[dict]:
    """Her satıra çözülmüş 'baglam' ekler (kopya döner). Sıra: satır > ajan_<aid>.json > <oturum>.json > '(belirsiz)'."""
    onb: dict = {}
    out = []
    for r in kayitlar:
        b = r.get("baglam") if isinstance(r.get("baglam"), str) else ""
        if not b and r.get("agent_id"):
            b = _oturum_baglami(sd, "ajan_" + str(r["agent_id"]), onb)
        if not b and r.get("oturum"):
            b = _oturum_baglami(sd, str(r["oturum"]), onb)
        out.append(dict(r, baglam=b or BELIRSIZ))
    return out


def baglam_filtre(kayitlar: list[dict], onek: str | None) -> list[dict]:
    """Çözülmüş baglamı verilen önekle başlayan satırlar."""
    if not onek:
        return kayitlar
    return [r for r in kayitlar if (r.get("baglam") or BELIRSIZ).startswith(onek)]


def baglam_kirilim(kayitlar: list[dict]) -> dict:
    """Çözülmüş satırlardan proje (ilk parça) ve tam baglam düzeyinde USD kırılımı."""
    tam: dict = collections.defaultdict(float)
    tam_satir: dict = collections.defaultdict(list)
    for r in kayitlar:
        tam[r.get("baglam") or BELIRSIZ] += r.get("maliyet_usd") or 0.0
        tam_satir[r.get("baglam") or BELIRSIZ].append(r)
    toplam = sum(tam.values())
    pay = lambda v: _r(v / toplam, 4) if toplam else 0.0  # noqa: E731
    proj: dict = collections.defaultdict(list)
    for b, v in tam.items():
        proj[b.split("/")[0]].append((b, v))
    projeler = []
    for pr, lst in proj.items():
        pu = sum(v for _, v in lst)
        projeler.append({"proje": pr, "usd": _r(pu), "pay": pay(pu), **_ek([r for b, _ in lst for r in tam_satir[b]]),
                         "baglamlar": [{"baglam": b, "usd": _r(v), "pay": pay(v), **_ek(tam_satir[b])} for b, v in sorted(lst, key=lambda x: -x[1])]})
    projeler.sort(key=lambda x: -x["usd"])
    return {"toplam_usd": _r(toplam), **_ek([r for v in tam_satir.values() for r in v]), "projeler": projeler}


# ---------------------------------------------------------------- planlayıcı modeli x sınıf x basamak (I-058 P2)

PLANLAYICI_MIN_N_VARSAYILAN = 20


def planlayici_min_n() -> int:
    """ayarlar/model_politikasi.json karar.min_n; dosya ya da alan yoksa 20."""
    yol = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ayarlar", "model_politikasi.json")
    try:
        with open(yol, encoding="utf-8") as f:
            n = (json.load(f).get("karar") or {}).get("min_n")
        return int(n) if isinstance(n, (int, float)) and n > 0 else PLANLAYICI_MIN_N_VARSAYILAN
    except (OSError, ValueError, AttributeError):
        return PLANLAYICI_MIN_N_VARSAYILAN


def beta_alt_sinir(basari: int, n: int, q: float = 0.2) -> float | None:
    """Beta(1+basari, 1+n-basari) dağılımının q (varsayılan %20) kuantili. Tam sayı parametrede CDF iki terimli toplamdır."""
    if n <= 0:
        return None
    a, m = 1 + basari, n + 1          # CDF(x) = P(Binom(m, x) >= a)

    def cdf(x):
        return sum(math.comb(m, j) * x ** j * (1 - x) ** (m - j) for j in range(a, m + 1))
    lo, hi = 0.0, 1.0
    for _ in range(50):
        mid = (lo + hi) / 2
        if cdf(mid) < q:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2, 3)


def _model_ailesi(m: str | None) -> str:
    m = _kisa_model(m)
    f = re.match(r"(opus|sonnet|haiku)", m)
    return f.group(1) if f else m


def _persentil(x: list, p: float) -> float | None:
    x = sorted(v for v in x if v is not None)
    if not x:
        return None
    i = (len(x) - 1) * p
    lo = int(i)
    hi = min(lo + 1, len(x) - 1)
    return round(x[lo] + (x[hi] - x[lo]) * (i - lo), 1)


def planlayici_modeli(kart: dict, ana_oturum: dict) -> str:
    """kart.plan_modeli; yoksa/'-' ise kart.oturum'un ana ajan satırlarında maliyeti en yüksek model; o da yoksa 'bilinmiyor'."""
    pm = kart.get("plan_modeli")
    if pm and pm != "-":
        return _model_ailesi(pm)
    m = ana_oturum.get(kart.get("oturum"))
    if m:
        return _model_ailesi(max(m.items(), key=lambda kv: kv[1])[0])
    return "bilinmiyor"


def _planlayici_satir(ad, sinif, bas, ks, usd_isci, usd_den, min_n, isci_satir=(), den_satir=()):
    denetlenen = ilk = ret = onay = 0
    sure = []
    cagri = sum(len(k.get("isciler") or []) for k in ks)
    for k in ks:
        dnt = sorted(k.get("denetimler") or [], key=lambda d: (d.get("sira", 0), d.get("zaman", "")))
        if dnt:
            denetlenen += 1
            ilk += int(dnt[0].get("karar") == "onay")
        ret += sum(1 for d in dnt if d.get("karar") == "ret")
        onay += int(k.get("durum") in ("onaylandi", "teslim") or L.kart_durumu_hesapla(k) in ("onaylandi", "teslim"))
        g = sorted(k.get("gecmis") or [], key=lambda x: x.get("zaman", ""))
        olus = _zaman(k.get("olusturma")) or (_zaman(g[0].get("zaman")) if g else None)
        teslim = next((_zaman(x.get("zaman")) for x in g if x.get("olay") == "teslim"), None)
        d = _dk(olus, teslim)
        if d is not None:
            sure.append(d)
    n = len(ks)
    yeterli = n >= min_n
    tok = lambda xs: sum(int(r.get(a) or 0) for r in xs for a in L._TOKEN_ALANLARI)  # noqa: E731
    tok_isci, tok_den = tok(isci_satir), tok(den_satir)
    return {"planlayici": ad, "sinif": sinif, "baslangic_basamak": bas, "n": n,
            "ilk_gecis": _r(ilk / denetlenen, 3) if denetlenen else None,
            "alt_sinir": beta_alt_sinir(ilk, denetlenen), "ret": ret, "denetlenen": denetlenen,
            "onaylanan": onay, "isci_kart": _r(cagri / n, 2) if n else None,
            "isci_usd_kart": _r(usd_isci / n) if n else None,
            "kabul_usd": _r((usd_isci + usd_den) / onay) if onay else None,
            "isci_token_kart": _r(tok_isci / n, 1) if n else None,
            "kabul_token": _r((tok_isci + tok_den) / onay, 1) if onay else None,
            **_ek(list(isci_satir) + list(den_satir)),
            "dk_medyan": _medyan(sure), "dk_p90": _persentil(sure, 0.9), "teslim": len(sure),
            "yeterli": yeterli, "etiket": None if yeterli else "yetersiz veri", "karar_satiri": yeterli}


def _planlayici(kartlar: list[dict], kayitlar: list[dict], min_n: int | None = None) -> dict:
    """Planlayıcı modeli x sınıf x başlangıç basamağı: ilk geçiş (+Beta %20 alt sınır), ret, işçi/kart, kabul başına USD, süre.
    Satırlar hücre bazlı; 'toplam' her planlayıcının bütün hücreleri. n < min_n hücre 'yetersiz veri' (yeterli=False,
    karar_satiri=False) olarak kalır. İptal kartlar dışarıda."""
    min_n = planlayici_min_n() if min_n is None else min_n
    ana_oturum: dict = {}
    isci, den = collections.Counter(), collections.Counter()
    isci_s, den_s = collections.defaultdict(list), collections.defaultdict(list)
    for r in kayitlar:
        if L.ana_ajan_satiri_mi(r):
            if r.get("oturum"):
                ana_oturum.setdefault(r["oturum"], collections.Counter())[r.get("model")] += r.get("maliyet_usd") or 0.0
            continue
        if _rol(r.get("ajan")) == "denetci":
            den[r["gorev"]] += r.get("maliyet_usd") or 0.0
            den_s[r["gorev"]].append(r)
        elif r.get("surec") in ("is", "duzeltme") or _rol(r.get("ajan")) == "isci":
            isci[r["gorev"]] += r.get("maliyet_usd") or 0.0
            isci_s[r["gorev"]].append(r)
    hucre: dict = collections.defaultdict(list)
    pl: dict = collections.defaultdict(list)
    for k in kartlar:
        if k.get("durum") == "iptal":
            continue
        ad = planlayici_modeli(k, ana_oturum)
        hucre[(ad, _sinif(k), k.get("baslangic_basamak") or k.get("basamak") or "-")].append(k)
        pl[ad].append(k)

    def usd(ks, c):
        return sum(c.get(k["id"], 0.0) for k in ks)

    def satirlari(ks, c):
        return [r for k in ks for r in c.get(k["id"], [])]
    satirlar = [_planlayici_satir(a, s, b, ks, usd(ks, isci), usd(ks, den), min_n, satirlari(ks, isci_s), satirlari(ks, den_s))
                for (a, s, b), ks in sorted(hucre.items())]
    toplam = [_planlayici_satir(a, "*", "*", ks, usd(ks, isci), usd(ks, den), min_n, satirlari(ks, isci_s), satirlari(ks, den_s))
              for a, ks in sorted(pl.items())]
    return {"olcum": L.simdi(), "min_n": min_n, "satirlar": satirlar, "toplam": toplam}


def planlayici_md(p: dict) -> str:
    """maliyet rapor için MD tablo (toplam satırları önce, sonra hücreler)."""
    f = lambda v, n=2: "–" if v is None else f"{v:.{n}f}"  # noqa: E731
    satir = [f"### Planlayıcı modeli × sınıf × basamak (ölçüm {p['olcum'][:16].replace('T', ' ')}, min_n {p['min_n']})", "",
             "| planlayıcı | sınıf | basamak | n | ilk geçiş | alt sınır (Beta %20) | ret | denetlenen | işçi/kart | işçi $/kart | kabul başına $ | işçi token/kart | kabul başına token | dk medyan | dk p90 | not |",
             "|" + "---|" * 16]
    for r in p["toplam"] + p["satirlar"]:
        satir.append(f"| {'**' + r['planlayici'] + '**' if r['sinif'] == '*' else r['planlayici']} | "
                     f"{'toplam' if r['sinif'] == '*' else r['sinif']} | {'–' if r['baslangic_basamak'] == '*' else r['baslangic_basamak']} | "
                     f"{r['n']} | {f(r['ilk_gecis'])} | {f(r['alt_sinir'])} | {r['ret']} | {r['denetlenen']} | {f(r['isci_kart'])} | {f(r['isci_usd_kart'])} | "
                     f"{f(r['kabul_usd'])} | {f(r['isci_token_kart'], 0)} | {f(r['kabul_token'], 0)} | {f(r['dk_medyan'], 1)} | {f(r['dk_p90'], 1)} | {r['etiket'] or ''} |")
    return "\n".join(satir) + "\n"


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
        "ders": _ders(kartlar, kayitlar), "planlayici": _planlayici(kartlar, kayitlar),
        "baglam": baglam_kirilim(baglam_coz(sd, kayitlar)),
        "hedef_panosu": hedef_panosu(kartlar, kayitlar),
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
    alan = next((a for a in alanlar if a["id"] == alan_id), None)
    if alan is None and alan_id:  # istenen alanda orkestra yok: başka alanın verisine düşme
        return {"acik": False, "mesaj": "Bu çalışma alanında orkestra açık değil.", "alan": {"id": alan_id, "ad": alan_id}}
    alan = alan or (alanlar[0] if alanlar else None)
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
