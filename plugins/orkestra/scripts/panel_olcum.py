"""Panel veri doğruluğu ve hız ölçümü (I-315, S2-S4, S6): salt okuma, çalışan panele HTTP isteği atar.

    python panel_olcum.py [--alan ID] [--tekrar 20] [--json]

- S2: panelin 5 pencere toplamı, tekilleştirilmiş defterin aynı pencere toplamıyla eşit mi (tolerans 0,05 USD: defter canlı büyür).
- S3: ağır uç noktalar (ozet, analitik, isler) `--tekrar` kez istenir; medyan ve p95 (ısınmış önbellek).
- S4: ağır istekler arka planda sürerken /saglik yanıt süresi (p95).
- S6: defterde 'tip-okunamadi' ve 'bilinmiyor' kalan satırlar (ay kırılımı) ve son 24 saatte yenisi var mı.
Eşik gerekçesi: 1 sn algı sınırı (arayüz tepkisinin kesintisiz sayıldığı eşik), 500 ms sağlık yanıtı (hafif uç nokta, GIL'e bağlı değil)."""
from __future__ import annotations

import argparse
import collections
import datetime
import json
import os
import statistics
import sys
import threading
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ork_lib as L  # noqa: E402
import panel  # noqa: E402

ESIK_AGIR_S, ESIK_SAGLIK_S, TOLERANS_USD = 1.0, 0.5, 0.05


def _port() -> int:
    with open(panel.DURUM, encoding="utf-8") as f:
        return int(json.load(f)["port"])


def _al(port, yol, zaman_asimi=120):
    t = time.perf_counter()
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{yol}", timeout=zaman_asimi) as r:
        veri = r.read()
    return time.perf_counter() - t, veri


def _yuzdelik(a, p):
    a = sorted(a)
    return a[min(len(a) - 1, int(round(p * (len(a) - 1))))]


def _ozet(sureler):
    return {"n": len(sureler), "medyan_s": round(statistics.median(sureler), 3), "p95_s": round(_yuzdelik(sureler, 0.95), 3),
            "en_yavas_s": round(max(sureler), 3)}


def toplam_dogrulugu(port, alan_id, sd):
    """S2: panel pencere toplamı == tekilleştirilmiş defter toplamı (aynı pencere tanımı, ork_lib.pencere_icinde)."""
    panel_p = json.loads(_al(port, f"/analitik.json?alan={urllib.parse.quote(alan_id)}")[1])["pencere"]
    bugun = datetime.date.today()
    toplam = collections.defaultdict(float)
    for r in L.maliyet_kayitlari(sd):
        z = L.yerel_zaman(r.get("zaman"))
        if z is None:
            continue
        for p in L.PENCERELER:
            if L.pencere_icinde(p, z.date(), bugun):
                toplam[p] += r.get("maliyet_usd") or 0.0
    sonuc = {}
    for p in L.PENCERELER:
        fark = round((panel_p.get(p) or {}).get("usd", 0.0) - toplam[p], 4)
        sonuc[p] = {"panel_usd": (panel_p.get(p) or {}).get("usd"), "defter_usd": round(toplam[p], 4), "fark": fark,
                    "tamam": abs(fark) <= TOLERANS_USD}
    return sonuc


def hiz(port, alan_id, tekrar):
    """S3: ısınmış önbellekte ağır uç noktalar."""
    sonuc = {}
    for ad in ("ozet", "analitik", "isler"):
        yol = f"/{ad}.json?alan={urllib.parse.quote(alan_id)}"
        _al(port, yol)   # ısıt
        sonuc[ad] = _ozet([_al(port, yol)[0] for _ in range(tekrar)])
        sonuc[ad]["tamam"] = sonuc[ad]["medyan_s"] < ESIK_AGIR_S and sonuc[ad]["p95_s"] < ESIK_AGIR_S
    return sonuc


def saglik_yuku_altinda(port, alan_id, tekrar, sure_s=12.0):
    """S4: ağır istekler (soğuk anahtarlar dahil) arka planda sürerken /saglik gecikmesi."""
    dur = threading.Event()

    def yuk():
        i = 0
        while not dur.is_set():
            i += 1
            for ad in ("ozet", "analitik", "isler", "teknik"):   # teknik: kart başına anahtar, önbelleği sık düşürür
                try:
                    _al(port, f"/{ad}.json?alan={urllib.parse.quote(alan_id)}&_={i}", 60)
                except Exception:  # noqa: BLE001
                    pass
    isci = [threading.Thread(target=yuk, daemon=True) for _ in range(3)]
    for t in isci:
        t.start()
    sureler = []
    bitis = time.time() + sure_s
    while time.time() < bitis and len(sureler) < max(tekrar, 20):
        try:
            sureler.append(_al(port, "/saglik", 10)[0])
        except Exception:  # noqa: BLE001
            sureler.append(10.0)
        time.sleep(0.25)
    dur.set()
    o = _ozet(sureler)
    o["tamam"] = o["p95_s"] < ESIK_SAGLIK_S
    return o


def etiket_kalani(sd):
    """S6: defterde etiketsiz kalan satırlar."""
    ay, son24 = collections.Counter(), 0
    simdi = datetime.datetime.now().astimezone()
    for r in L.maliyet_kayitlari(sd):
        if r.get("surec") == "tip-okunamadi" or r.get("ajan") in ("?", "bilinmiyor") or r.get("surec") == "bilinmiyor":
            z = L.yerel_zaman(r.get("zaman"))
            ay[z.strftime("%Y-%m") if z else "zamansiz"] += 1
            if z and simdi - z < datetime.timedelta(hours=24):
                son24 += 1
    return {"ay_kirilimi": dict(sorted(ay.items())), "toplam": sum(ay.values()), "son_24_saat": son24, "tamam": son24 == 0}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--alan", default=None)
    ap.add_argument("--tekrar", type=int, default=20)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    alanlar = [x for x in L.calisma_alanlari() if x.get("orkestra")]
    alan = next((x for x in alanlar if x["id"] == a.alan), None) if a.alan else (alanlar[0] if alanlar else None)
    if alan is None:
        print("orkestralı çalışma alanı yok", file=sys.stderr)
        return 2
    sd = os.path.join(alan["yol"], ".claude", "orkestra")
    port = _port()
    rapor = {"zaman": L.simdi(), "alan": alan["id"], "S2_toplam": toplam_dogrulugu(port, alan["id"], sd),
             "S3_hiz": hiz(port, alan["id"], a.tekrar), "S4_saglik": saglik_yuku_altinda(port, alan["id"], a.tekrar),
             "S6_etiket": etiket_kalani(sd)}
    rapor["tamam"] = (all(v["tamam"] for v in rapor["S2_toplam"].values()) and all(v["tamam"] for v in rapor["S3_hiz"].values())
                      and rapor["S4_saglik"]["tamam"] and rapor["S6_etiket"]["tamam"])
    print(json.dumps(rapor, ensure_ascii=False, indent=1))
    return 0 if rapor["tamam"] else 1


if __name__ == "__main__":
    sys.exit(main())
