# -*- coding: utf-8 -*-
"""Toplu etiketleme, adım 3 (T0): işçi çıktılarını birleştirir, sayım denetimi yapar,
denetçi için örneklem çıkarır.

Kullanım:
  python -X utf8 -I birlestir.py --klasor <parcala.py klasörü> [--orneklem 30] [--tohum 42]

Denetimler (parça başına): çıktı dosyası var mı; başlık id,etiket,guven,gerekce mi;
eksik / fazla / tekrarlayan id; izinli dışı etiket; geçersiz güven.
Çıktılar (--klasor altında):
  denetim_sayim.json   her zaman yazılır: parça durumları, hatalar, etiket ve güven dağılımı,
                       yeniden koşulacak parçalar
  birlesik.csv         YALNIZ tüm parçalar temizse: kaynak satırları (kaynak sırası) + etiket, guven, gerekce
  orneklem.csv         YALNIZ tüm parçalar temizse: orkestra:denetci için örneklem
                       (Düşük güvenliler öncelikli, sonra etiket başına orantılı; sabit tohum)
Çıkış kodu: 0 tutarlı, 2 tutarsız (yeniden koşulacak parçalar denetim_sayim.json'da).
"""
import argparse
import collections
import csv
import json
import os
import random
import sys

sys.dont_write_bytecode = True  # skill klasörüne __pycache__ bırakma
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parcala import oku  # noqa: E402


def parca_oku(yol, m):
    hata = []
    with open(yol, encoding="utf-8-sig", newline="") as f:
        r = csv.reader(f)
        satirlar = [x for x in r if any(c.strip() for c in x)]
    if not satirlar:
        return {}, ["boş dosya"]
    baslik = [b.strip().lower() for b in satirlar[0]]
    if baslik != m["cikti_baslik"]:
        return {}, [f"başlık {satirlar[0]} != {m['cikti_baslik']}"]
    kayit, gorulen = {}, collections.Counter()
    for i, x in enumerate(satirlar[1:], 2):
        if len(x) != len(baslik):
            hata.append(f"satır {i}: {len(x)} alan")
            continue
        d = dict(zip(baslik, (c.strip() for c in x)))
        gorulen[d["id"]] += 1
        if d["etiket"] not in m["etiketler"]:
            hata.append(f"{d['id']}: izinsiz etiket {d['etiket']!r}")
        if d["guven"] not in m["guven"]:
            hata.append(f"{d['id']}: geçersiz güven {d['guven']!r}")
        kayit[d["id"]] = d
    tekrar = [i for i, n in gorulen.items() if n > 1]
    if tekrar:
        hata.append(f"tekrarlayan id: {tekrar[:10]}")
    return kayit, hata


def orneklem_sec(kayitlar, n, tohum):
    rnd = random.Random(tohum)
    n = min(n, len(kayitlar))
    dusuk = [k for k in kayitlar if k["guven"] == "Düşük"]
    rnd.shuffle(dusuk)
    secilen = dusuk[: n // 2]
    kalan = [k for k in kayitlar if k not in secilen]
    grup = collections.defaultdict(list)
    for k in kalan:
        grup[k["etiket"]].append(k)
    hedef = n - len(secilen)
    taban = 1 if len(grup) <= hedef else 0  # etiket sayısı örneklemden azsa her etiketten en az 1
    for et, ks in sorted(grup.items()):
        rnd.shuffle(ks)
        pay = max(taban, round(hedef * len(ks) / max(1, len(kalan))))
        secilen += ks[:pay]
    secilen = secilen[:n]
    if len(secilen) < n:  # yuvarlama açığını rastgele tamamla
        sec_id = {k["id"] for k in secilen}
        artan = [k for k in kayitlar if k["id"] not in sec_id]
        rnd.shuffle(artan)
        secilen += artan[: n - len(secilen)]
    return secilen


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--klasor", required=True)
    ap.add_argument("--orneklem", type=int, default=30)
    ap.add_argument("--tohum", type=int, default=42)
    a = ap.parse_args()

    mp = os.path.join(a.klasor, "manifest.json")
    if not os.path.isfile(mp):
        sys.exit(f"HATA: manifest yok: {mp} (önce parcala.py)")
    with open(mp, encoding="utf-8") as f:
        m = json.load(f)

    durum, tum, yeniden = [], {}, []
    for p in m["parcalar"]:
        yol = os.path.join(a.klasor, p["cikti"])
        if not os.path.isfile(yol):
            durum.append({"parca": p["no"], "durum": "çıktı yok", "hatalar": []})
            yeniden.append(p["no"])
            continue
        kayit, hata = parca_oku(yol, m)
        beklenen = set(p["idler"])
        eksik = sorted(beklenen - set(kayit))
        fazla = sorted(set(kayit) - beklenen)
        if eksik:
            hata.append(f"eksik id ({len(eksik)}): {eksik[:10]}")
        if fazla:
            hata.append(f"fazla id ({len(fazla)}): {fazla[:10]}")
        durum.append({"parca": p["no"], "beklenen": len(beklenen), "gelen": len(kayit),
                      "durum": "temiz" if not hata else "hatalı", "hatalar": hata[:30]})
        if hata:
            yeniden.append(p["no"])
        tum.update({k: v for k, v in kayit.items() if k in beklenen})

    etiket_say = collections.Counter(v["etiket"] for v in tum.values())
    guven_say = collections.Counter(v["guven"] for v in tum.values())
    tutarli = not yeniden and len(tum) == m["toplam"]
    rapor = {"toplam_kaynak": m["toplam"], "etiketlenen": len(tum), "tutarli": tutarli,
             "yeniden_kosulacak_parcalar": yeniden, "etiket_dagilimi": dict(etiket_say),
             "guven_dagilimi": dict(guven_say), "parcalar": durum}

    if tutarli:
        kol, satirlar = oku(m["kaynak"], m.get("sayfa"), m.get("baslik_satiri", 1))
        idc = m["id_sutun"]
        with open(os.path.join(a.klasor, "birlesik.csv"), "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(kol + ["etiket", "guven", "gerekce"])
            for x in satirlar:
                e = tum[str(x[idc]).strip()]
                w.writerow([x[c] for c in kol] + [e["etiket"], e["guven"], e["gerekce"]])
        kaynak = {str(x[idc]).strip(): x for x in satirlar}
        orn = orneklem_sec(list(tum.values()), a.orneklem, a.tohum)
        with open(os.path.join(a.klasor, "orneklem.csv"), "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["id"] + m["alanlar"] + ["etiket", "guven", "gerekce"])
            for e in orn:
                w.writerow([e["id"]] + [kaynak[e["id"]][c] for c in m["alanlar"]]
                           + [e["etiket"], e["guven"], e["gerekce"]])
        rapor["orneklem"] = len(orn)

    with open(os.path.join(a.klasor, "denetim_sayim.json"), "w", encoding="utf-8") as f:
        json.dump(rapor, f, ensure_ascii=False, indent=1)
    for d in durum:
        print(f"  parça {d['parca']:02d}: {d['durum']}" + (f" — {d['hatalar'][0]}" if d["hatalar"] else ""))
    print(f"etiket ({len(etiket_say)} çeşit, ilk 10): {dict(etiket_say.most_common(10))}; güven: {dict(guven_say)}")
    if tutarli:
        print(f"TUTARLI: {len(tum)}/{m['toplam']} satır; birlesik.csv ve orneklem.csv ({rapor['orneklem']}) yazıldı")
        sys.exit(0)
    print(f"TUTARSIZ: yeniden koşulacak parçalar {yeniden}; birlesik.csv yazılmadı")
    sys.exit(2)


if __name__ == "__main__":
    main()
