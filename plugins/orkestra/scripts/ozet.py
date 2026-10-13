"""Orkestra anlık görüntüsü: arayüzlerin (Claude içi panel, HTML panel) tek veri kaynağı.

`olustur(sd, proje)` durumu tek sözlükte toplar; `yaz(sd, proje)` onu `<durum>/ozet.json`a atomik yazar.
Hook'lar ve durumu değiştiren CLI komutları her değişiklikte `yaz` çağırır; arayüzler yalnız dosyayı okur
(süreç başlatmaz). Oturuma özgü değerler `maliyet.oturumlar[<oturum id>]` altındadır; arayüz kendi oturumunu seçer.
"""
from __future__ import annotations

import collections
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ork_lib as L  # noqa: E402

SURUM = 2


def _yuvarla(d: dict, n: int = 4) -> dict:
    return {k: round(v, n) for k, v in d.items()}


def olustur(sd: str, proje: str) -> dict:
    kayitlar = L.maliyet_kayitlari(sd)
    bugun = datetime.date.today().isoformat()

    # --- kartlar
    kart_usd = collections.Counter()
    for r in kayitlar:
        if r.get("gorev") not in (None, "-"):
            kart_usd[r["gorev"]] += r.get("maliyet_usd", 0) or 0
    ks = []
    for k in L.kartlar(sd):
        d = L.kart_durumu_hesapla(k)
        son = (k.get("denetimler") or [{}])[-1]
        ks.append({"id": k["id"], "baslik": k["baslik"][:80], "durum": d, "basamak": k["basamak"],
                   "oturum": k.get("oturum"), "isci": len(k.get("isciler", [])), "denetim": son.get("karar", "-"),
                   "bagimli": k.get("bagimliliklar", []), "usd": round(kart_usd.get(k["id"], 0.0), 4),
                   "guncelleme": k.get("guncelleme")})
    acik = [k for k in ks if k["durum"] in L.ACIK_DURUMLAR or k["durum"] in ("beklemede", "planlandi")]
    kapali = sorted([k for k in ks if k not in acik], key=lambda x: x.get("guncelleme") or "", reverse=True)[:10]
    kartlar = sorted(acik, key=lambda x: x["id"]) + kapali

    # --- maliyet
    bugunku = [r for r in kayitlar if (r.get("zaman") or "").startswith(bugun)]
    surec, model = collections.Counter(), collections.Counter()
    ajan_surec: dict = {}
    for r in bugunku:
        usd = r.get("maliyet_usd", 0) or 0
        surec[r.get("surec", "-")] += usd
        model[(r.get("model") or "-").replace("claude-", "")] += usd
        a = ajan_surec.setdefault((r.get("ajan", "-"), r.get("surec", "-")), {"kosu": 0, "usd": 0.0, "cikis": 0, "giris": 0})
        a["kosu"] += 1
        a["usd"] += usd
        a["cikis"] += r.get("cikis", 0) or 0
        a["giris"] += (r.get("giris", 0) or 0) + (r.get("onbellek_okuma", 0) or 0) + (r.get("onbellek_yazma", 0) or 0)

    sohbet_listesi = L.sohbetler(sd, proje, limit=15)
    oturum_ids = {s["oturum"] for s in sohbet_listesi}
    oturumlar: dict = {}
    for r in kayitlar:
        oid = r.get("oturum")
        if oid not in oturum_ids:
            continue
        o = oturumlar.setdefault(oid, {"usd": 0.0, "surec": collections.Counter(), "model": collections.Counter(), "ajan_surec": {}})
        usd = r.get("maliyet_usd", 0) or 0
        o["usd"] += usd
        o["surec"][r.get("surec", "-")] += usd
        o["model"][(r.get("model") or "-").replace("claude-", "")] += usd
        a = o["ajan_surec"].setdefault((r.get("ajan", "-"), r.get("surec", "-")), {"kosu": 0, "usd": 0.0, "cikis": 0, "giris": 0})
        a["kosu"] += 1
        a["usd"] += usd
        a["cikis"] += r.get("cikis", 0) or 0
        a["giris"] += (r.get("giris", 0) or 0) + (r.get("onbellek_okuma", 0) or 0) + (r.get("onbellek_yazma", 0) or 0)
    for o in oturumlar.values():
        o["usd"] = round(o["usd"], 4)
        o["surec"] = _yuvarla(dict(o["surec"].most_common(8)))
        o["model"] = _yuvarla(dict(o["model"].most_common(6)))
        o["ajan_surec"] = sorted([{"ajan": a, "surec": su, **{k: (round(v, 4) if k == "usd" else v) for k, v in d.items()}}
                                  for (a, su), d in o["ajan_surec"].items()], key=lambda x: -x["usd"])[:15]

    sohbetler = []
    for s in sohbet_listesi:
        usd = s["motor_usd"] if s["motor_usd"] is not None else s["defter_usd"]
        if not usd:
            continue
        sohbetler.append({"oturum": s["oturum"], "baslik": s["baslik"], "usd": round(usd, 4),
                          "kaynak": "motor" if s["motor_usd"] is not None else "defter",
                          "motor_usd": s["motor_usd"], "defter_usd": s["defter_usd"], "son": s["son"],
                          "modeller": s["modeller"]})

    # --- defter ve rüya
    defter = []
    for r in L.defter_kayitlari(sd)[-12:]:
        defter.append({"zaman": r.get("zaman"), "gorev": r.get("gorev", "-"), "surec": r.get("surec", "-"),
                       "ajan": r.get("ajan", "-"), "metin": str(r.get("sonuc") or r.get("yaptim") or "")[:160]})
    import ruya
    rd = ruya.durum(sd)

    return {
        "surum": SURUM, "acik": True, "uretim": L.simdi(), "proje": os.path.basename(os.path.abspath(proje)),
        "kartlar": kartlar,
        "sayac": dict(collections.Counter(k["durum"] for k in acik)),
        "maliyet": {
            "bugun": round(sum(r.get("maliyet_usd", 0) or 0 for r in bugunku), 4),
            "toplam": round(sum(r.get("maliyet_usd", 0) or 0 for r in kayitlar), 4),
            "surec": _yuvarla(dict(surec.most_common(10))),
            "model": _yuvarla(dict(model.most_common(6))),
            "ajan_surec": sorted([{"ajan": a, "surec": s, **{k: (round(v, 4) if k == "usd" else v) for k, v in d.items()}}
                                  for (a, s), d in ajan_surec.items()], key=lambda x: -x["usd"])[:20],
            "oturumlar": oturumlar,
        },
        "sohbetler": sohbetler,
        "defter": defter,
        "ruya": {"zamani_geldi": rd["zamani_geldi"], "rapor": bool(rd["okunmamis_rapor"]), "calisiyor": bool(rd["calisiyor"]),
                 "son_ruya": rd["son_ruya"]},
    }


def yaz(sd: str, proje: str) -> dict | None:
    """Anlık görüntüyü yazar; hata arayüzü bozmasın diye ozet_hata.txt'ye düşer, istisna fırlatmaz."""
    try:
        o = olustur(sd, proje)
        L.atomik_yaz(os.path.join(sd, "ozet.json"), json.dumps(o, ensure_ascii=False))
        return o
    except Exception as e:  # noqa: BLE001
        try:
            L.atomik_yaz(os.path.join(sd, "ozet_hata.txt"), f"{L.simdi()} {type(e).__name__}: {e}\n")
        except Exception:
            pass
        return None
