"""akis: kart asama sureleri, acik kart yasi ve darbogaz olcumu (G-082). Salt okuma.

Kaynak: <sd>/gorevler/G-*.json kartlarinin 'gecmis' olay akisi. Her kartin olaylari zamana gore
siralanip bir durum makinesinden gecirilir; tamamlanan asama sureleri kart basina toplanir.

Kullanim: python akis.py --sd <orkestra_durum_dizini> [--gun N] [--simdi ISO] [--json]
"""
from __future__ import annotations

import argparse
import datetime
import glob
import json
import os
import statistics
import sys

ASAMALAR = ["alinma_bekleme", "iscide_ilk", "iscide_duzeltme",
            "denetimde", "toplama_bekleme", "karar_bekleme"]
ANLAMLI = {"olusturuldu", "isleniyor", "is-bitti", "denetim:onay", "denetim:ret",
           "beklemede", "birlestirme-ret", "teslim", "beklemeden-teslim", "iptal"}
ATLANAN_SONEKLER = (".denetim.json", ".onkontrol.json")


def _zaman(s):
    if not isinstance(s, str):
        return None
    try:
        t = datetime.datetime.fromisoformat(s.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.astimezone()
    return t


def _dk(sn):
    return round(sn / 60.0, 1)


def kartlari_oku(sd):
    """Gecerli kart sozluklerini dondurur (iptal haric)."""
    kartlar = []
    for yol in sorted(glob.glob(os.path.join(sd, "gorevler", "G-*.json"))):
        ad = os.path.basename(yol)
        if ad.endswith(ATLANAN_SONEKLER):
            continue
        try:
            with open(yol, encoding="utf-8-sig") as f:
                veri = json.load(f)
        except (OSError, ValueError):
            continue
        if not isinstance(veri, dict) or not isinstance(veri.get("gecmis"), list):
            continue
        if veri.get("durum") == "iptal":
            continue
        kartlar.append(veri)
    return kartlar


def olaylar(kart):
    """(zaman, olay) listesi, zamana gore sirali; bozuk ogeler atlanir."""
    cikti = []
    for o in kart["gecmis"]:
        if not isinstance(o, dict):
            continue
        t = _zaman(o.get("zaman"))
        ad = o.get("olay")
        if t is None or not isinstance(ad, str):
            continue
        cikti.append((t, ad))
    cikti.sort(key=lambda x: x[0])
    return cikti


def kart_analiz(kart, simdi):
    """-> (tamamlanan {asama: saniye}, acik (asama, yas_sn) | None, ilk_zaman | None)."""
    ev = olaylar(kart)
    if not ev:
        return {}, None, None
    toplam = {}

    def ekle(asama, sn):
        toplam[asama] = toplam.get(asama, 0.0) + max(sn, 0.0)

    olus = None          # olusturuldu zamani (alinma bekleme)
    is_basi = None       # aktif isleniyor zamani
    is_asama = None      # aktif isleniyor'un asamasi
    ilk_bitti = False    # ilk is-bitti goruldu mu
    ilk_isleniyor = False
    den_basi = None
    bek_basi = None
    onay_t = None
    son = None           # son anlamli (zaman, olay)
    bek_son = None       # son beklemede / birlestirme-ret zamani
    for t, o in ev:
        if o not in ANLAMLI:
            continue
        son = (t, o)
        if o == "olusturuldu":
            if olus is None:
                olus = t
        elif o == "isleniyor":
            if bek_basi is not None:
                ekle("karar_bekleme", (t - bek_basi).total_seconds())
                bek_basi = None
            if not ilk_isleniyor:
                ilk_isleniyor = True
                if olus is not None:
                    ekle("alinma_bekleme", (t - olus).total_seconds())
                is_basi, is_asama = t, "iscide_ilk"
            elif not ilk_bitti:
                pass  # ilk tur suruyor (beklemeden donus); pencere ilk isleniyor'dan baslar
            else:
                is_basi, is_asama = t, "iscide_duzeltme"
            onay_t = None
        elif o == "is-bitti":
            if is_basi is not None:
                ekle(is_asama, (t - is_basi).total_seconds())
                is_basi = None
            ilk_bitti = True
            den_basi = t
            onay_t = None
        elif o in ("denetim:onay", "denetim:ret"):
            if den_basi is not None:
                ekle("denetimde", (t - den_basi).total_seconds())
                den_basi = None
            onay_t = t if o == "denetim:onay" else None
        elif o in ("beklemede", "birlestirme-ret"):
            if bek_basi is None:
                bek_basi = t
            bek_son = t
            if o == "birlestirme-ret":
                onay_t = None  # toplama beklemesi sayilmaz; karar bekleme baslar
        elif o in ("teslim", "beklemeden-teslim"):
            if bek_basi is not None:
                ekle("karar_bekleme", (t - bek_basi).total_seconds())
                bek_basi = None
            if o == "teslim" and onay_t is not None:
                ekle("toplama_bekleme", (t - onay_t).total_seconds())
                onay_t = None
        elif o == "iptal":
            if bek_basi is not None:
                ekle("karar_bekleme", (t - bek_basi).total_seconds())
                bek_basi = None

    acik = None
    if kart.get("durum") not in ("teslim", "iptal") and son is not None:
        t, o = son
        asama = None
        if kart.get("durum") == "beklemede":
            asama = "karar_bekleme"
            t = bek_son or t
        elif o == "olusturuldu" or o == "denetim:ret":
            asama = "alinma_bekleme"
        elif o == "isleniyor":
            asama = "iscide_duzeltme" if (ilk_bitti and is_asama == "iscide_duzeltme") else "iscide_ilk"
        elif o == "is-bitti":
            asama = "denetimde"
        elif o == "denetim:onay":
            asama = "toplama_bekleme"
        if asama is not None:
            acik = (asama, max((simdi - t).total_seconds(), 0.0))
    return toplam, acik, ev[0][0]


def _istatistik(degerler):
    n = len(degerler)
    if n == 0:
        return {"n": 0, "medyan_dk": None, "p90_dk": None, "toplam_dk": 0}
    s = sorted(degerler)
    sira = (9 * n + 9) // 10  # ceil(0.9*n)
    return {"n": n,
            "medyan_dk": _dk(statistics.median(s)),
            "p90_dk": _dk(s[sira - 1]),
            "toplam_dk": _dk(sum(s))}


def hesapla(sd, gun=None, simdi=None):
    import ork_lib as L
    simdi = simdi or datetime.datetime.now().astimezone()
    sinir = L.gun_baslangici(gun, simdi) if gun is not None else None
    dagilim = {a: [] for a in ASAMALAR}
    acikler = []
    sayi = 0
    for kart in kartlari_oku(sd):
        toplam, acik, ilk = kart_analiz(kart, simdi)
        if sinir is not None and (ilk is None or ilk < sinir):
            continue
        sayi += 1
        for a, sn in toplam.items():
            dagilim[a].append(sn)
        if acik is not None:
            baslik = kart.get("baslik")
            acikler.append({"id": str(kart.get("id", "")),
                            "baslik": baslik if isinstance(baslik, str) else "",
                            "asama": acik[0], "yas_dk": _dk(acik[1])})
    acikler.sort(key=lambda k: -k["yas_dk"])
    asamalar = {a: _istatistik(dagilim[a]) for a in ASAMALAR}
    yas = {}
    for k in acikler:
        yas[k["asama"]] = yas.get(k["asama"], 0.0) + k["yas_dk"]
    canli = max(ASAMALAR, key=lambda a: yas.get(a, 0.0)) if yas else None
    dolu = [a for a in ASAMALAR if asamalar[a]["n"] > 0]
    gecmis = max(dolu, key=lambda a: asamalar[a]["toplam_dk"]) if dolu else None
    return {"asamalar": asamalar, "acik": acikler,
            "darbogaz": {"canli": canli, "gecmis": gecmis}, "kart_sayisi": sayi}


def metin(sonuc):
    satir = [f"Kart sayısı: {sonuc['kart_sayisi']}", ""]
    bas = f"{'aşama':<18}{'n':>5}{'medyan':>10}{'p90':>10}{'toplam':>11}{'açık':>6}  en yaşlı açık kart"
    satir.append(bas)
    satir.append("-" * len(bas))
    for a in ASAMALAR:
        s = sonuc["asamalar"][a]
        ac = [k for k in sonuc["acik"] if k["asama"] == a]
        yasli = f"{ac[0]['id']} ({ac[0]['yas_dk']} dk)" if ac else "-"
        med = "-" if s["medyan_dk"] is None else f"{s['medyan_dk']:.1f}"
        p90 = "-" if s["p90_dk"] is None else f"{s['p90_dk']:.1f}"
        satir.append(f"{a:<18}{s['n']:>5}{med:>10}{p90:>10}{s['toplam_dk']:>11.1f}{len(ac):>6}  {yasli}")
    d = sonuc["darbogaz"]
    satir.append("")
    satir.append(f"Darboğaz: canlı={d['canli'] or 'yok'}, geçmiş={d['gecmis'] or 'yok'}")
    return "\n".join(satir)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Kart aşama süreleri ve darboğaz (salt okuma)")
    ap.add_argument("--sd", required=True, help="orkestra durum dizini")
    ap.add_argument("--gun", type=int, default=None, help="yalnız son N günde oluşan kartlar")
    ap.add_argument("--simdi", default=None, help="şimdiki zamanı sabitle (ISO)")
    ap.add_argument("--json", action="store_true", dest="json_cikti")
    a = ap.parse_args(argv)
    simdi = None
    if a.simdi:
        simdi = _zaman(a.simdi)
        if simdi is None:
            ap.error("--simdi geçerli ISO zaman değil")
    sonuc = hesapla(a.sd, a.gun, simdi)
    try:
        sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    except (AttributeError, ValueError):
        pass
    if a.json_cikti:
        print(json.dumps(sonuc, ensure_ascii=False))
    else:
        print(metin(sonuc))
    return 0


if __name__ == "__main__":
    sys.exit(main())
