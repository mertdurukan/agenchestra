"""Deterministik maliyet anomali denetimi (TOK-11).

Perspektif ajanı maliyeti toplu tablodan okuduğu için kart × koşu × zaman örüntülerini kaçırıyordu (15.10:
teslim edilmiş kartta T4 + opus denetim, aynı kartta eşzamanlı iki koşu). Bu modül o örüntüleri kuralla bulur;
LLM yorumu gerekmez. Girdi: tekilleştirilmiş maliyet defteri (L.maliyet_kayitlari; 'tur' parçaları ve birikimli
'hook' satırları ajan kimliğine göre birleştirilir) ve görev kartları.

Kurallar (kimlik → açıklama):
  K1 kart-pahali       kart toplam maliyeti >= kartın bütçe tavanı (butce.kart_tavani: kart > geçmiş taban 2×p90 >
                       basamak varsayılanı); tavan bilinmiyorsa esik_kart_usd
  K2 kart-ajan-cok     karttaki ayrı ajan sayısı > esik_kart_ajan (workflow'un kart ajan tavanı; politika eşiği —
                       geçmiş p90 israflı dönemi taban alacağı için kullanılmaz)
  K3 teslim-sonrasi    kart teslim/iptal olduktan sonra karta ajan koştu
  K4 es-zamanli-isci   aynı kartta zaman aralıkları kesişen iki işçi ajanı (iş/düzeltme/yükseltme)
  K5 kapi-ajani        test-kapisi / on-kontrol süreci ajanla koştu (kapılar CLI'de olmalı)
  K6 ana-ajan-payi     ana ajan (orkestrasyon) maliyet payı >= esik_ana_pay (kart harcaması olan günlerde); kart
                       harcaması olmayan günde pay yerine günlük ana ajan maliyeti >= esik_ana_gun_usd
  K7 t4-yukseltme      T4 basamağında ajan koştu (yükseltme zinciri pahalı uca ulaştı)

Kullanım: `orkestra maliyet anomali [--gun N] [--json]`.
"""
from __future__ import annotations

import collections
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ork_lib as L  # noqa: E402

ESIKLER = {"esik_kart_usd": 2.0, "esik_kart_ajan": 8, "esik_ana_pay": 0.5, "esik_ana_gun_usd": 100.0}
ISCI_SURECLERI = ("is", "duzeltme", "yukseltme")
KAPI_SURECLERI = ("test-kapisi", "on-kontrol")


def _zaman(z):
    try:
        t = datetime.datetime.fromisoformat(str(z))
        return t if t.tzinfo else t.astimezone()
    except (ValueError, TypeError):
        return None


def ajanlari_birlestir(satirlar: list[dict]) -> list[dict]:
    """Aynı (oturum, agent_id) satırlarını tek ajana indirger: usd ve süre toplanır, bitiş en geç zaman."""
    gruplar: dict = {}
    for d in satirlar:
        if not d.get("agent_id") or d.get("ajan") in (None, "ana-ajan"):
            continue
        g = gruplar.get((d.get("oturum"), d["agent_id"]))
        if g is None:
            gruplar[(d.get("oturum"), d["agent_id"])] = dict(d)
            continue
        g["maliyet_usd"] = (g.get("maliyet_usd") or 0) + (d.get("maliyet_usd") or 0)
        g["sure_ms"] = (g.get("sure_ms") or 0) + (d.get("sure_ms") or 0)
        if d["_z"] > g["_z"]:
            g["_z"] = d["_z"]
    return list(gruplar.values())


def denetle(satirlar: list[dict], kartlar: dict[str, dict], esikler: dict | None = None,
            tavanlar: dict[str, float] | None = None) -> list[dict]:
    """Saf denetim: anomali listesi [{kural, kart, ayrinti, usd}] (pahalıdan ucuza). tavanlar: gid -> K1 USD eşiği."""
    e = {**ESIKLER, **(esikler or {})}
    tavanlar = tavanlar or {}
    ajan = ajanlari_birlestir(satirlar)
    # Ana ajan payı: karta bağlı olmayan satırlar (ork_lib.ana_ajan_satiri_mi, KPI ile tek tanım). Satırlar
    # maliyet_kayitlari'ndan gelir; tur/hook çifte sayımı orada çözülür.
    ana = [d for d in satirlar if L.ana_ajan_satiri_mi(d)]
    out = []
    kart_ajan = collections.defaultdict(list)
    for d in ajan:
        if d.get("gorev") and d["gorev"] != "-":
            kart_ajan[d["gorev"]].append(d)
    for gid, liste in kart_ajan.items():
        usd = sum(x.get("maliyet_usd") or 0 for x in liste)
        esik_usd = tavanlar.get(gid, e["esik_kart_usd"])
        if usd >= esik_usd:
            out.append({"kural": "K1", "ad": "kart-pahali", "kart": gid, "usd": round(usd, 2),
                        "ayrinti": f"{len(liste)} ajan, {usd:.2f}$ ≥ tavan {esik_usd:.2f}$"})
        if len(liste) > e["esik_kart_ajan"]:
            out.append({"kural": "K2", "ad": "kart-ajan-cok", "kart": gid, "usd": round(usd, 2),
                        "ayrinti": f"{len(liste)} ajan > {e['esik_kart_ajan']}"})
        k = kartlar.get(gid) or {}
        kapanis = next((_zaman(o.get("zaman")) for o in (k.get("gecmis") or []) if o.get("olay") in ("teslim", "iptal")), None)
        if kapanis:
            sonra = [x for x in liste if x["_z"] - datetime.timedelta(milliseconds=x.get("sure_ms") or 0) > kapanis]
            if sonra:
                out.append({"kural": "K3", "ad": "teslim-sonrasi", "kart": gid,
                            "usd": round(sum(x.get("maliyet_usd") or 0 for x in sonra), 2),
                            "ayrinti": f"kapanıştan ({kapanis.isoformat(timespec='minutes')}) sonra {len(sonra)} ajan: "
                                       + ", ".join(sorted({f"{x.get('surec')}/{str(x.get('model', ''))[7:13]}" for x in sonra}))})
        isciler = sorted(((x["_z"] - datetime.timedelta(milliseconds=x.get("sure_ms") or 0), x["_z"], x)
                          for x in liste if x.get("surec") in ISCI_SURECLERI), key=lambda t: t[0])
        for (b1, s1, x1), (b2, s2, x2) in zip(isciler, isciler[1:]):
            # 2 sn'den az çakışma saat yuvarlaması sayılır (transkript damgası ile süre farkı); gerçek eşzamanlılık değil
            if (s1 - b2).total_seconds() > 2 and x1.get("agent_id") != x2.get("agent_id"):
                out.append({"kural": "K4", "ad": "es-zamanli-isci", "kart": gid,
                            "usd": round((x2.get("maliyet_usd") or 0), 2),
                            "ayrinti": f"{x1.get('surec')} ({b1:%H:%M}-{s1:%H:%M}) ile {x2.get('surec')} ({b2:%H:%M}-{s2:%H:%M}) çakışıyor"})
                break
        if any(x.get("ajan") == "orkestra:isci-t4" for x in liste):
            t4 = [x for x in liste if x.get("ajan") == "orkestra:isci-t4"]
            out.append({"kural": "K7", "ad": "t4-yukseltme", "kart": gid,
                        "usd": round(sum(x.get("maliyet_usd") or 0 for x in t4), 2), "ayrinti": f"{len(t4)} T4 ajanı"})
    kapi = [d for d in ajan if d.get("surec") in KAPI_SURECLERI]
    if kapi:
        out.append({"kural": "K5", "ad": "kapi-ajani", "kart": "-", "usd": round(sum(x.get("maliyet_usd") or 0 for x in kapi), 2),
                    "ayrinti": f"{len(kapi)} kapı/ön kontrol ajanı (kapılar CLI is-bitti'de koşmalı)"})
    # K6: kart harcaması olan günlerde pay kuralı; kart harcaması olmayan günde pay %100'e doyar ve ana ajanın
    # verimini göstermez, o gün mutlak günlük maliyet eşiğine bakılır (esik_ana_gun_usd).
    usd = lambda d: d.get("maliyet_usd") or 0  # noqa: E731
    kartli_gun = {d["_z"].date() for d in satirlar if not L.kartsiz_satir_mi(d) and usd(d) > 0}
    toplam = sum(usd(d) for d in satirlar if d["_z"].date() in kartli_gun)
    ana_usd = sum(usd(d) for d in ana if d["_z"].date() in kartli_gun)
    if toplam > 0 and ana_usd / toplam >= e["esik_ana_pay"]:
        out.append({"kural": "K6", "ad": "ana-ajan-payi", "kart": "-", "usd": round(ana_usd, 2),
                    "ayrinti": f"ana ajan payı %{100 * ana_usd / toplam:.0f} ({ana_usd:.2f}$ / {toplam:.2f}$)"})
    gunluk: dict = collections.defaultdict(float)
    for d in ana:
        if d["_z"].date() not in kartli_gun:
            gunluk[d["_z"].date()] += usd(d)
    for gun, u in sorted(gunluk.items()):
        if u >= e["esik_ana_gun_usd"]:
            out.append({"kural": "K6", "ad": "ana-ajan-gun-maliyeti", "kart": "-", "usd": round(u, 2),
                        "ayrinti": f"{gun:%d.%m}: kart harcaması yok, ana ajan günlük {u:.2f}$ ≥ eşik {e['esik_ana_gun_usd']:.0f}$"})
    out.sort(key=lambda x: -x["usd"])
    return out


def calistir(sd: str, gun: int | None = 1, simdi=None) -> list[dict]:
    import butce
    simdi = simdi or datetime.datetime.now().astimezone()
    sinir = L.gun_baslangici(gun, simdi) if gun else None
    tum = L.maliyet_kayitlari(sd)
    satirlar = []
    for d in tum:
        z = _zaman(d.get("zaman"))
        if z is None or (sinir and z < sinir):
            continue
        satirlar.append({**d, "_z": z})
    kart_listesi = L.kartlar(sd)
    kartlar = {k.get("id"): k for k in kart_listesi}
    taban = butce.taban(kart_listesi, tum)
    tavanlar = {gid: butce.kart_tavani(k, taban)[0] for gid, k in kartlar.items() if gid}
    return denetle(satirlar, kartlar, tavanlar=tavanlar)


def metin(anomaliler: list[dict], en_cok: int = 12) -> str:
    if not anomaliler:
        return "Maliyet anomalisi yok."
    say = collections.Counter(a["kural"] for a in anomaliler)
    bas = "Anomali: " + ", ".join(f"{k} x{v}" for k, v in sorted(say.items()))
    satirlar = [f"{a['kural']} {a['ad']} {a['kart']}: {a['ayrinti']} (~{a['usd']}$)" for a in anomaliler[:en_cok]]
    if len(anomaliler) > en_cok:
        satirlar.append(f"... {len(anomaliler) - en_cok} anomali daha (--json ile tümü)")
    return "\n".join([bas] + satirlar)
