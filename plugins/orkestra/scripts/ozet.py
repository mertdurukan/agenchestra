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

    sohbet_listesi = L.sohbetler(sd, proje, limit=15, tahmin=True)
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
        if s["motor_usd"]:
            usd, kaynak = s["motor_usd"], "motor"
        elif s["defter_usd"]:
            usd, kaynak = s["defter_usd"], "defter"
        else:
            usd, kaynak = s.get("tahmin_usd") or 0.0, "tahmin"
        if not usd:
            continue
        sohbetler.append({"oturum": s["oturum"], "baslik": s["baslik"], "usd": round(usd, 4),
                          "kaynak": kaynak,
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
        "surum": SURUM, "acik": True, "orkestra": True, "uretim": L.simdi(), "proje": os.path.basename(os.path.abspath(proje)),
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


# ---------------------------------------------------------------- çoklu çalışma alanı

def _hafif(alan: dict) -> dict:
    """Orkestra kurulu olmayan çalışma alanı: yalnız sohbet maliyetleri (Claude'un hesabı ya da transkript tahmini)."""
    sohbet_listesi = L.sohbetler(None, alan["yol"], limit=15, tahmin=True,
                                 oturum_dizini=os.path.join(os.path.expanduser("~"), ".claude", "projects", alan["id"]))
    sohbetler, model, oturumlar = [], collections.Counter(), {}
    bugun = datetime.date.today().isoformat()
    bugun_usd = 0.0
    for s in sohbet_listesi:
        usd = s["motor_usd"] if s["motor_usd"] else (s.get("tahmin_usd") or 0.0)
        if not usd:
            continue
        kaynak = "motor" if s["motor_usd"] else "tahmin"
        sohbetler.append({"oturum": s["oturum"], "baslik": s["baslik"], "usd": round(usd, 4), "kaynak": kaynak,
                          "motor_usd": s["motor_usd"], "defter_usd": 0.0, "son": s["son"], "modeller": s["modeller"]})
        for m, v in (s["modeller"] or {}).items():
            model[m.replace("claude-", "")] += v
        oturumlar[s["oturum"]] = {"usd": round(usd, 4), "surec": {},
                                  "model": _yuvarla({m.replace("claude-", ""): v for m, v in (s["modeller"] or {}).items()}),
                                  "ajan_surec": []}
        if (s["son"] or "").startswith(bugun):
            bugun_usd += usd
    return {
        "surum": SURUM, "acik": True, "orkestra": False, "uretim": L.simdi(), "proje": alan["ad"],
        "kartlar": [], "sayac": {},
        "maliyet": {"bugun": round(bugun_usd, 4), "toplam": round(sum(s["usd"] for s in sohbetler), 4), "surec": {},
                    "model": _yuvarla(dict(model.most_common(6))), "ajan_surec": [], "oturumlar": oturumlar},
        "sohbetler": sohbetler, "defter": [], "ruya": None,
    }


def alan_ozeti(alan_id: str | None) -> dict:
    """Panel için seçili çalışma alanının anlık görüntüsü (orkestra varsa tam, yoksa hafif)."""
    alanlar = L.calisma_alanlari()
    alan = next((a for a in alanlar if a["id"] == alan_id), None) or next((a for a in alanlar if a["orkestra"]), None) \
        or (alanlar[0] if alanlar else None)
    if alan is None:
        return {"acik": False, "hata": "Bu bilgisayarda Claude çalışma alanı bulunamadı."}
    sd = os.path.join(alan["yol"], ".claude", "orkestra")
    o = olustur(sd, alan["yol"]) if alan["orkestra"] else _hafif(alan)
    o["alan"] = {"id": alan["id"], "ad": alan["ad"], "yol": alan["yol"], "orkestra": alan["orkestra"]}
    return o
