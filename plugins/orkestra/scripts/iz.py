"""İşlem izi: istek / iş / oturum için süre ve token ağacı ile kapsama ölçer (salt okuma).

Veri kaynağı: ork_lib.maliyet_kayitlari (tekilleştirilmiş, düzeltme uygulanmış), zaman.jsonl (tur=ana/alt/arac),
gunluk.jsonl (istek). Ağaç kökü ile `toplam` aynı `toplam()` fonksiyonundan çıkar; is_rapor.py da onu çağırır.
Araç düğümleri tahmindir (mesaj usage'ından paylaştırılmış) ve defter toplamına katılmaz.
`kapsama` ölçer kök çözümün yerine geçmez: yalnız geçmiş veri, Cursor kayıtları ve atlanan hook satırları içindir.
"""
from __future__ import annotations

import csv
import datetime
import io
import json
import os
import re

import ork_lib as L

KALEMLER = ("giris", "cikis", "onbellek_okuma", "onbellek_yazma")
KOVA = "I-000"
AYAR_YOLU = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ayarlar", "iz_kapsama.json")
VARSAYILAN_ESIK = 10
CSV_BASLIK = ["tip", "ad", "span_id", "ust_span_id", "sure_ms", "giris", "cikis", "onbellek_okuma",
              "onbellek_yazma", "usd", "model", "tahmin"]
YOK_AD = "(istek kimliği yok)"


def _sayi(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def toplam(kayitlar) -> dict:
    """Defter satırı listesinin tek toplama fonksiyonu; token = dört kalemin toplamı."""
    t = {f: int(sum(_sayi(r.get(f)) for r in kayitlar)) for f in KALEMLER}
    return {"usd": sum(_sayi(r.get("maliyet_usd")) for r in kayitlar), "token": sum(t.values()), **t}


def is_id(v) -> str:
    v = v.strip() if isinstance(v, str) else ""
    return KOVA if v in ("", "-") else v


def _satir_is(sd: str, kayitlar: list[dict]) -> list[str]:
    kart_is = {k["id"]: k.get("is") for k in L.kartlar(sd) if k.get("id") and k.get("is")}
    return [is_id(L.satir_isi(r, kart_is)) for r in kayitlar]


def _tur(secici: str) -> str:
    if re.fullmatch(r"I-\d+", secici):
        return "is"
    if re.fullmatch(r"\w{8}-\d{4}", secici):
        return "istek"
    return "oturum"


def _dugum(tip, ad, span_id, sure_ms, kalemler, model, tahmin=False, cocuklar=None) -> dict:
    return {"tip": tip, "ad": ad, "span_id": span_id, "sure_ms": int(sure_ms),
            "giris": kalemler["giris"], "cikis": kalemler["cikis"], "onbellek_okuma": kalemler["onbellek_okuma"],
            "onbellek_yazma": kalemler["onbellek_yazma"], "usd": kalemler["usd"], "model": model,
            "tahmin": tahmin, "cocuklar": cocuklar or []}


def _modeller(satirlar) -> str:
    gorulen = []
    for r in satirlar:
        m = r.get("model")
        if m and m not in gorulen:
            gorulen.append(m)
    return ", ".join(gorulen)


def _istek_metni(gunluk, istek_id) -> str:
    for g in gunluk:
        if g.get("tur") == "istek" and g.get("istek_id") == istek_id:
            return str(g.get("ne") or g.get("metin") or "")[:120]
    return ""


def _istek_dugumu(istek_id, satirlar, zaman, gunluk) -> dict:
    ad = YOK_AD if istek_id is None else (_istek_metni(gunluk, istek_id) or istek_id)
    gruplar: dict = {}
    for r in satirlar:
        tip = "alt" if r.get("agent_id") else "tur"
        gruplar.setdefault((tip, r.get("span_id")), []).append(r)
    cocuklar = []
    for (tip, span), rs in gruplar.items():
        sure = sum(_sayi(z.get("sure_ms")) for z in zaman
                   if z.get("tur") in ("ana", "alt") and span is not None and z.get("span_id") == span)
        model = _modeller(rs)
        aracs = [_dugum("arac", z.get("arac") or "?", z.get("span_id"), _sayi(z.get("sure_ms")),
                        {**{f: int(_sayi(z.get(f))) for f in KALEMLER}, "usd": 0.0}, model, True)
                 for z in zaman if z.get("tur") == "arac" and span is not None and z.get("ust_span_id") == span]
        ad_ = f"alt:{rs[0].get('agent_id')}" if tip == "alt" else f"tur:{span or '-'}"
        cocuklar.append(_dugum(tip, ad_, span, sure, toplam(rs), model, False, aracs))
    sure_k = sum(c["sure_ms"] for c in cocuklar)
    return _dugum("istek", ad, istek_id, sure_k, toplam(satirlar), _modeller(satirlar), False, cocuklar)


def agac(sd: str, secici: str):
    tur = _tur(secici)
    tum = L.maliyet_kayitlari(sd)
    if tur == "is":
        iss = _satir_is(sd, tum)
        satirlar = [r for r, i in zip(tum, iss) if i == secici]
    elif tur == "istek":
        satirlar = [r for r in tum if r.get("istek_id") == secici]
    else:
        satirlar = [r for r in tum if r.get("oturum") == secici]
    if not satirlar:
        return None
    zaman = L.zaman_kayitlari(sd)
    gunluk = L.jsonl_oku(os.path.join(sd, "gunluk.jsonl"))
    top = toplam(satirlar)
    if tur == "istek":
        kok = _istek_dugumu(secici, satirlar, zaman, gunluk)
    else:
        gruplar: dict = {}
        for r in satirlar:
            gruplar.setdefault(r.get("istek_id") or None, []).append(r)
        cocuklar = [_istek_dugumu(i, rs, zaman, gunluk) for i, rs in gruplar.items()]
        kok = _dugum(tur, secici, None, sum(c["sure_ms"] for c in cocuklar), top, _modeller(satirlar), False, cocuklar)
    return {"secici": secici, "tur": tur, "kok": kok, "toplam": top}


def _satirlar(d, ust=None, derinlik=0):
    yield d, ust, derinlik
    for c in d["cocuklar"]:
        yield from _satirlar(c, d.get("span_id") or ust, derinlik + 1)


def metin(a: dict) -> str:
    cikti = []
    for d, _ust, der in _satirlar(a["kok"]):
        s = (f"{'  ' * der}{d['tip']} {d['ad']}  {d['sure_ms'] / 1000:.1f}s  giris={d['giris']} cikis={d['cikis']} "
             f"okuma={d['onbellek_okuma']} yazma={d['onbellek_yazma']}  ${d['usd']:.6f}  {d['model']}")
        cikti.append(s + ("  tahmin" if d["tahmin"] else ""))
    return "\n".join(cikti)


def json_metni(a: dict) -> str:
    return json.dumps(a, ensure_ascii=False, indent=2)


def csv_metni(a: dict) -> str:
    cikti = io.StringIO()
    w = csv.writer(cikti, lineterminator="\n")
    w.writerow(CSV_BASLIK)
    for d, ust, _ in _satirlar(a["kok"]):
        w.writerow([d["tip"], d["ad"], d["span_id"] or "", ust or "", d["sure_ms"], d["giris"], d["cikis"],
                    d["onbellek_okuma"], d["onbellek_yazma"], f"{d['usd']:.6f}", d["model"], d["tahmin"]])
    return cikti.getvalue()


def _esik():
    try:
        with open(AYAR_YOLU, encoding="utf-8") as f:
            v = json.load(f).get("is_bos_esik_yuzde")
        return v if isinstance(v, (int, float)) and not isinstance(v, bool) else VARSAYILAN_ESIK
    except (OSError, ValueError, AttributeError):
        return VARSAYILAN_ESIK


def _yuzde(n: int, toplam_: int):
    return round(100 * n / toplam_, 1) if toplam_ else 0


def kapsama(sd: str) -> dict:
    kayitlar = L.maliyet_kayitlari(sd)
    n = len(kayitlar)
    bos_mask = [i == KOVA for i in _satir_is(sd, kayitlar)]
    is_bos = sum(bos_mask)
    # Oturumu hiç olmayan satır (atif_nedeni=oturum-isiz) hiçbir yoldan işe bağlanamaz; eşik, düzeltilebilir
    # boşluğu (bu satırlar paydadan ve paydaştan çıkarılarak) ölçer. Ham oran ayrıca raporlanır.
    oturum_isiz = sum(1 for r in kayitlar if r.get("atif_nedeni") == "oturum-isiz")
    oturum_isiz_bos = sum(1 for r, b in zip(kayitlar, bos_mask) if b and r.get("atif_nedeni") == "oturum-isiz")
    istek_bos = sum(1 for r in kayitlar if not r.get("istek_id"))
    nedenler: dict = {}
    for r in kayitlar:
        if r.get("atif_nedeni"):
            nedenler[r["atif_nedeni"]] = nedenler.get(r["atif_nedeni"], 0) + 1
    istekler = [g for g in L.jsonl_oku(os.path.join(sd, "gunluk.jsonl")) if g.get("tur") == "istek"]
    ne_bos = sum(1 for g in istekler if not g.get("ne"))
    esik = _esik()
    is_y = _yuzde(is_bos, n)
    atf_y = _yuzde(is_bos - oturum_isiz_bos, n - oturum_isiz)
    return {"olcum_saati": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
            "satir_sayisi": n, "is_bos_yuzde": is_y, "istek_id_bos_yuzde": _yuzde(istek_bos, n),
            "ne_bos_yuzde": _yuzde(ne_bos, len(istekler)), "atif_nedeni": nedenler,
            "oturum_isiz_satir": oturum_isiz, "is_bos_atfedilebilir_yuzde": atf_y,
            "esik_yuzde": esik, "asildi": atf_y > esik}


def kapsama_satiri(sd: str) -> str:
    k = kapsama(sd)
    if not k["asildi"]:
        return ""
    return (f"İZ KAPSAMA: işe bağlanabilir ama bağlanmamış defter satırı %{k['is_bos_atfedilebilir_yuzde']} "
            f"(eşik %{k['esik_yuzde']}; ham işsiz oran %{k['is_bos_yuzde']}, oturumsuz {k['oturum_isiz_satir']} satır "
            f"hariç; {k['satir_sayisi']} satır, ölçüm {k['olcum_saati']}); ayrıntı `orkestra iz kapsama`.")


def kapsama_metni(k: dict) -> str:
    nedenler = ", ".join(f"{n}: {c}" for n, c in k["atif_nedeni"].items()) or "-"
    return "\n".join([
        f"ölçüm saati: {k['olcum_saati']}  (defter satırı: {k['satir_sayisi']})",
        f"is boş (atfedilebilir, oturum-isiz hariç): {k['is_bos_atfedilebilir_yuzde']:.1f}%  "
        f"(eşik {k['esik_yuzde']}%, aşıldı: {'evet' if k['asildi'] else 'hayır'})",
        f"is boş (ham): {k['is_bos_yuzde']:.1f}%  (oturum-isiz satır: {k['oturum_isiz_satir']})",
        f"istek_id boş: {k['istek_id_bos_yuzde']:.1f}%",
        f"ne boş: {k['ne_bos_yuzde']:.1f}%",
        f"atif_nedeni: {nedenler}",
    ])
