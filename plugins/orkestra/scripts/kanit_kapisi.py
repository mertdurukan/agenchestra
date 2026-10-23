"""Kayıtlı ön kontroller: K-001 (K<n>: kanıt satırı) ve K-002 (etiketli sayı tutarlılığı). Model çağırmaz.

Ayar: ayarlar/on_kontrol.json (varsayılan) + <sd>/on_kontrol.json (alan alan ezme). Salt okuma.
"""
from __future__ import annotations

import copy
import fnmatch
import json
import os
import re
import sys

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VARSAYILAN_YOL = os.path.join(KOK, "ayarlar", "on_kontrol.json")


def _oku_json(yol):
    try:
        with open(yol, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _birlestir(taban, ek):
    if not isinstance(ek, dict):
        return taban
    kont = ek.get("kontroller")
    if not isinstance(kont, dict):
        return taban
    for kimlik, alanlar in kont.items():
        if kimlik in taban["kontroller"] and isinstance(alanlar, dict):
            taban["kontroller"][kimlik].update(copy.deepcopy(alanlar))
    return taban


def ayar_yukle(sd=None) -> dict:
    taban = _oku_json(VARSAYILAN_YOL)
    if not isinstance(taban, dict) or not isinstance(taban.get("kontroller"), dict):
        taban = {"surum": 1, "kontroller": {}}
    if sd:
        taban = _birlestir(taban, _oku_json(os.path.join(sd, "on_kontrol.json")))
    return taban


def kontrol_kimlikleri() -> list:
    return list(ayar_yukle()["kontroller"].keys())


def neden_kontrol(neden):
    for kimlik, c in ayar_yukle()["kontroller"].items():
        if neden in (c.get("neden_kodlari") or []):
            return kimlik
    return None


def etkin_kontroller(sd) -> dict:
    ayar = ayar_yukle(sd)["kontroller"]
    sonuc = {}
    veri = _oku_json(os.path.join(sd, "kurallar", "kurallar.json")) if sd else None
    kurallar = veri.get("kurallar") if isinstance(veri, dict) else veri
    if not isinstance(kurallar, list):
        kurallar = []
    if sd:  # eklenti katmanı: bu projede kapatılmamış etkin kurallar da kontrol bağlayabilir
        try:
            import onay
            kurallar = list(kurallar) + [r for r in onay.etkin_kurallar(sd) if r.get("katman") == "plugin"]
        except Exception:
            pass
    for kimlik, c in ayar.items():
        kaynak = None
        for k in kurallar:
            if isinstance(k, dict) and k.get("durum") == "etkin" and k.get("kontrol") == kimlik:
                kaynak = "kural " + str(k.get("id", "?"))
                break
        if kaynak is None and c.get("her_zaman") is True:
            kaynak = "her_zaman"
        if kaynak:
            sonuc[kimlik] = {"mod": c.get("mod", "golge"), "kaynak": kaynak}
    return sonuc


def _etiketler(kart):
    krit = kart.get("kabul_kriterleri") if isinstance(kart, dict) else None
    if not isinstance(krit, list):
        raise TypeError("kabul_kriterleri liste degil")
    out = []
    for i, k in enumerate(krit, 1):
        m = re.match(r"\s*K(\d+)\b", str(k))
        out.append(int(m.group(1)) if m else i)
    return out


def kanit_kontrol(kart, ozet, kanitlar, cfg) -> dict:
    etiketler = _etiketler(kart)
    sonuc = {"n": len(etiketler), "eksik": [], "kisa": [], "gecti": True}
    if str(kart.get("sinif", "")) in (cfg.get("sinif_haric") or []):
        return sonuc
    metin = str(ozet or "")
    if isinstance(kanitlar, (list, tuple)):
        metin += "\n" + "\n".join(str(x) for x in kanitlar)
    elif kanitlar:
        metin += "\n" + str(kanitlar)
    satirlar = metin.splitlines()
    minc = int(cfg.get("min_icerik_karakter", 8))
    kism = cfg.get("kisman_belirteci") or "KISMEN"
    for e in etiketler:
        kalip = re.compile(str(cfg["satir_kalibi"]).replace("{n}", str(e)))
        bulundu = False
        gecerli = False
        for s in satirlar:
            m = kalip.match(s)
            if not m:
                continue
            bulundu = True
            icerik = m.group("icerik").strip()
            if kism in icerik or len(icerik) >= minc:
                gecerli = True
                break
        etiket = "K%d" % e
        if not bulundu:
            sonuc["eksik"].append(etiket)
        elif not gecerli:
            sonuc["kisa"].append(etiket)
    sonuc["gecti"] = not sonuc["eksik"] and not sonuc["kisa"]
    return sonuc


def _norm_sayi(s):
    return re.sub(r"[.,](?=\d{3}\b)", "", s)


def sayi_tutarlilik(yollar, proje, cfg) -> list:
    uzn = tuple(x.lower() for x in (cfg.get("uzantilar") or []))
    azami = int(cfg.get("azami_bayt", 400000))
    anahtar = [a.lower() for a in (cfg.get("etiket_anahtarlari") or [])]
    birim = [b.lower() for b in (cfg.get("birimler") or [])]
    yoksay = {y.lower() for y in (cfg.get("yoksay_etiketler") or [])}
    haric = list(cfg.get("haric_yollar") or [])
    sayi = r"\d+(?:[.,]\d{3})*"
    k1 = re.compile(r"([^\W\d_][\w ]*?)\s*:\s*\**\s*(" + sayi + r")\b(?![:/.]\d)")
    k2 = (re.compile(r"(?<![\w.,])(" + sayi + r")\s+(" + "|".join(re.escape(b) for b in birim) + r")\w*", re.I)
          if birim else None)
    out = []
    for y in yollar or []:
        try:
            yol = y if os.path.isabs(y) else os.path.join(proje or "", y)
            if not uzn or not yol.lower().endswith(uzn) or not os.path.isfile(yol) or os.path.getsize(yol) > azami:
                continue
            if any(fnmatch.fnmatch(yol.replace("\\", "/"), h) for h in haric):
                continue  # kural/yönerge belgeleri rapor değildir: "madde 3", "madde 5" gibi atıflar sayı çelişkisi sayılmaz
            with open(yol, encoding="utf-8", errors="replace") as f:
                metin = f.read()
        except Exception:
            continue
        deg: dict = {}
        cit = False
        for s in metin.splitlines():
            if s.lstrip().startswith("```"):
                cit = not cit
                continue
            if cit:
                continue
            for m in k1.finditer(s):
                et = " ".join(m.group(1).lower().split())
                if any(a in et for a in anahtar):
                    deg.setdefault(et, []).append(_norm_sayi(m.group(2)))
            if k2:
                for m in k2.finditer(s):
                    deg.setdefault(m.group(2).lower(), []).append(_norm_sayi(m.group(1)))
        # "toplam kart" ve "kart" aynı birim köküne indirilir
        grup: dict = {}
        for et, v in deg.items():
            kok = et
            for b in birim:
                if et == b or et.endswith(" " + b) or et.startswith(b + " "):
                    kok = b
                    break
            grup.setdefault(kok, []).extend(v)
        for et, v in grup.items():
            if et in yoksay:
                continue
            ayri = sorted(set(v), key=lambda z: (len(z), z))
            if len(ayri) >= 2:
                out.append({"dosya": yol, "etiket": et, "degerler": ayri})
    return out


def kapi(sd, proje, kart, ozet, kanitlar, ciktilar) -> dict:
    try:
        etkin = etkin_kontroller(sd)
        ayar = ayar_yukle(sd)["kontroller"]
        ihlal = False
        mesajlar = []
        kayit = {}
        sonuclar = {}
        if "kanit-satiri" in etkin:
            mod = etkin["kanit-satiri"]["mod"]
            r = kanit_kontrol(kart, ozet, kanitlar, ayar["kanit-satiri"])
            sonuclar["kanit-satiri"] = r
            kayit["kanit_mod"] = mod
            if r["gecti"]:
                kayit["kanit"] = "gecti"
            else:
                parca = []
                if r["eksik"]:
                    parca.append("eksik:" + ",".join(r["eksik"]))
                if r["kisa"]:
                    parca.append("kisa:" + ",".join(r["kisa"]))
                kayit["kanit"] = ";".join(parca)
                ilk = (r["eksik"] or r["kisa"])[0]
                m = "K-001 kanıt satırı " + "; ".join(parca) + '. Örnek: --kanit "%s: <kanıt>"' % ilk
                mesajlar.append(("UYARI (gölge): " if mod != "ihlal" else "") + m)
                if mod == "ihlal":
                    ihlal = True
        if "sayi-tutarli" in etkin:
            mod = etkin["sayi-tutarli"]["mod"]
            r = sayi_tutarlilik(ciktilar, proje, ayar["sayi-tutarli"])
            sonuclar["sayi-tutarli"] = r
            kayit["sayi_mod"] = mod
            if not r:
                kayit["sayi_tutarli"] = "gecti"
            else:
                kayit["sayi_tutarli"] = "tutarsiz:%d" % len(r)
                det = "; ".join("%s %s=%s" % (os.path.basename(x["dosya"]), x["etiket"], "/".join(x["degerler"]))
                                for x in r)
                mesajlar.append(("UYARI (gölge): " if mod != "ihlal" else "") + "K-002 sayı tutarsız: " + det)
                if mod == "ihlal":
                    ihlal = True
        return {"sonuclar": sonuclar, "ihlal": ihlal, "mesajlar": mesajlar, "kayit": kayit}
    except Exception as e:
        return {"sonuclar": {}, "ihlal": False, "mesajlar": [], "kayit": {"hata": type(e).__name__}}


def main(argv=None):
    import argparse
    for ak in (sys.stdout, sys.stderr):
        try:
            ak.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="komut", required=True)
    d = sp.add_parser("durum")
    d.add_argument("--sd")
    a = ap.parse_args(argv)
    etkin = etkin_kontroller(a.sd) if a.sd else {}
    ayar = ayar_yukle(a.sd)["kontroller"]
    cikti = {}
    for kimlik, c in ayar.items():
        e = etkin.get(kimlik)
        cikti[kimlik] = {"etkin": bool(e), "mod": c.get("mod"), "kaynak": e["kaynak"] if e else None}
    print(json.dumps(cikti, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
