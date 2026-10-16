"""orkestra kpi: hazır 8 KPI için SALT OKUMA ölçüm (G-025).

`olcum(sd, gun=None)` durum klasöründen KPI sözlüğü döner; hiçbir şey yazmaz. Kart ve maliyet okuyucuları
ork_lib'den (kartlar, maliyet_kayitlari: tekilleştirilmiş), zaman çözümü analitik'ten gelir.
Pay ya da payda 0 ise değer None. Sır ve istem metni çıktıya girmez (yalnız sayılar).
"""
from __future__ import annotations

import datetime
import glob
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analitik as A  # noqa: E402
import ork_lib as L  # noqa: E402

ONAYLI = ("onaylandi", "teslim")
KPILER = ("dogrulanmis_basari", "basari_basina_maliyet", "basari_basina_token", "onbellek_isabet",
          "ret_orani", "onkontrol_ret_orani", "yeniden_deneme_carpani", "p95_sure_sn")

TANIMLAR = {
    "dogrulanmis_basari": {"pay": "denetçi onaylı kart sayısı (durum onaylandi|teslim)",
                           "payda": "toplam kart − iptal kartı"},
    "basari_basina_maliyet": {"pay": "onaylı kartların maliyet_usd toplamı (ana ajan gorev='-' hariç; reddedilen/iptal kartın maliyeti dahil DEĞİL)",
                              "payda": "onaylı kart sayısı"},
    "basari_basina_token": {"pay": "onaylı kartların giris+cikis+onbellek_okuma+onbellek_yazma toplamı",
                            "payda": "onaylı kart sayısı"},
    "onbellek_isabet": {"pay": "onbellek_okuma toplamı",
                        "payda": "giris + onbellek_okuma + onbellek_yazma toplamı (iptal kartlar dışarıda)"},
    "ret_orani": {"pay": "denetçi ret kararı sayısı", "payda": "toplam denetim kararı (onay+ret); iptal kartlar dışarıda"},
    "onkontrol_ret_orani": {"pay": "geçmeyen ön kontrol koşusu (kart.onkontrol_kosulari)", "payda": "toplam ön kontrol koşusu"},
    "yeniden_deneme_carpani": {"pay": "toplam işçi çağrısı (kartların isciler sayısı)",
                               "payda": "kart sayısı (iptal hariç)"},
    "p95_sure_sn": {"pay": "olusturma → teslim (yoksa onaylandi) süreleri, saniye; nearest-rank %95",
                    "payda": "tamamlanan kart sayısı"},
    "onay_bekleme_sn": {"pay": "karar.zaman − olusturma, saniye; medyan ve nearest-rank p95",
                        "payda": "karar verilmiş onay sayısı"},
    # Hedef panosu (analitik.hedef_panosu, ayarlar/hedef.json): pencere son 3 gün ve tüm zaman
    "ana_ajan_payi": {"pay": "ana ajan payı = karta bağlı olmayan (gorev boş ya da '-') defter maliyeti; kartsız alt ajan satırları dahil", "payda": "pencere içindeki tüm defter maliyeti"},
    "isci_cagrisi_kart": {"pay": "kartların isciler sayısı toplamı", "payda": "kart sayısı (iptal hariç)"},
    "onayli_kart_usd": {"pay": "onaylı kartlara bağlı defter maliyeti", "payda": "onaylı kart sayısı"},
    "teknik_not_kapsama": {"pay": "teknik alanı dolu onaylı/teslim kart (teknik_kapi_baslangic sonrası)",
                           "payda": "teknik_kapi_baslangic sonrası oluşan onaylı/teslim kart"},
}


def _bol(pay, payda, sifir_olcum=False):
    """Payda 0 -> None. Pay 0 -> None (eski davranış); sifir_olcum=True (aralık ölçümü) ise 0.0:
    etki izlemede 'ölçüldü, sıfır' ile 'veri yok' ayrışmalı."""
    if not payda or (not pay and not sifir_olcum):
        return None
    return pay / payda


def _p95(x: list):
    if not x:
        return None
    s = sorted(x)
    return s[max(0, math.ceil(0.95 * len(s)) - 1)]


def _medyan(x: list):
    if not x:
        return None
    s = sorted(x)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def _json(yol):
    try:
        with open(yol, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _tok(r: dict) -> int:
    return sum(int(r.get(a) or 0) for a in ("giris", "cikis", "onbellek_okuma", "onbellek_yazma"))


def _sure_sn(kart: dict):
    gecmis = kart.get("gecmis") or []
    bit = None
    for olay in ("teslim", "onaylandi"):
        zs = [A._zaman(e.get("zaman")) for e in gecmis if e.get("olay") == olay]
        zs = [z for z in zs if z]
        if zs:
            bit = max(zs)
            break
    bas = A._zaman(kart.get("olusturma"))
    if not bit or not bas:
        return None
    return (bit - bas).total_seconds()


def _hesapla(kartlar: list[dict], mal_kart: dict, tum_mal: list[dict], sifir_olcum: bool = False) -> dict:
    """kartlar: iptal hariç. mal_kart: gid -> satırlar. tum_mal: onbellek paydası için satırlar."""
    onayli = [k for k in kartlar if k.get("durum") in ONAYLI]
    onayli_mal = [r for k in onayli for r in mal_kart.get(k["id"], [])]
    usd = sum(float(r.get("maliyet_usd") or 0) for r in onayli_mal)
    tok = sum(_tok(r) for r in onayli_mal)
    okuma = sum(int(r.get("onbellek_okuma") or 0) for r in tum_mal)
    payda_o = sum(int(r.get(a) or 0) for r in tum_mal for a in ("giris", "onbellek_okuma", "onbellek_yazma"))
    ret = sum(k["_ret"] for k in kartlar)
    karar = sum(k["_karar"] for k in kartlar)
    okret = sum(k["_ok_ret"] for k in kartlar)
    oktop = sum(k["_ok_top"] for k in kartlar)
    cagri = sum(len(k.get("isciler") or []) for k in kartlar)
    sureler = [s for s in (k["_sure"] for k in kartlar) if s is not None]
    return {
        "dogrulanmis_basari": _bol(len(onayli), len(kartlar), sifir_olcum),
        "basari_basina_maliyet": _bol(usd, len(onayli), sifir_olcum),
        "basari_basina_token": _bol(tok, len(onayli), sifir_olcum),
        "onbellek_isabet": _bol(okuma, payda_o, sifir_olcum),
        "ret_orani": _bol(ret, karar, sifir_olcum),
        "onkontrol_ret_orani": _bol(okret, oktop, sifir_olcum),
        "yeniden_deneme_carpani": _bol(cagri, len(kartlar), sifir_olcum),
        "p95_sure_sn": _p95(sureler),
    }


def _ornekler(kartlar: list[dict], tum_mal: list[dict]) -> dict:
    """Her KPI'nın paydasındaki örnek sayısı (etki ölçümü 'yeterli örnek mi' diye bakar)."""
    onayli = [k for k in kartlar if k.get("durum") in ONAYLI]
    return {
        "dogrulanmis_basari": len(kartlar),
        "basari_basina_maliyet": len(onayli),
        "basari_basina_token": len(onayli),
        "onbellek_isabet": len(tum_mal),
        "ret_orani": sum(k["_karar"] for k in kartlar),
        "onkontrol_ret_orani": sum(k["_ok_top"] for k in kartlar),
        "yeniden_deneme_carpani": len(kartlar),
        "p95_sure_sn": sum(1 for k in kartlar if k["_sure"] is not None),
    }


def olcum(sd: str, gun: float | None = None, aralik: tuple | None = None) -> dict:
    """aralik=(bas, bit): tz'li datetime çifti, yarı açık [bas, bit); verilmezse davranış değişmez.
    Çıktıda 'ornek' (KPI başına payda sayısı) da döner."""
    esik = None
    if gun is not None:
        esik = L.gun_baslangici(gun)

    def icinde(zaman) -> bool:
        if esik is None and aralik is None:
            return True
        z = A._zaman(zaman)
        if not z:
            return False
        if esik is not None and z < esik:
            return False
        if aralik is not None and not (aralik[0] <= z < aralik[1]):
            return False
        return True

    tum = [k for k in L.kartlar(sd) if icinde(k.get("olusturma"))]
    kartlar = []
    for k in tum:
        if k.get("durum") == "iptal":
            continue
        gid = k["id"]
        den = _json(os.path.join(sd, "gorevler", gid + ".denetim.json"))
        if not isinstance(den, list):
            den = k.get("denetimler") or []
        kararlar = [d.get("karar") for d in den if isinstance(d, dict) and d.get("karar") in ("onay", "ret")]
        # Ön kontrol koşuları kartın kendisinde tutulur (on_kontrol._kosu_kaydet); .onkontrol.json yalnız taban/dosya özeti taşır.
        kont = [c for c in (k.get("onkontrol_kosulari") or []) if isinstance(c, dict) and "gecti" in c]
        k = dict(k)
        k["_karar"] = len(kararlar)
        k["_ret"] = kararlar.count("ret")
        k["_ok_top"] = len(kont)
        k["_ok_ret"] = sum(1 for c in kont if not c["gecti"])
        k["_sure"] = _sure_sn(k)
        kartlar.append(k)

    idler = {k["id"] for k in kartlar}
    mal_kart: dict = {}
    ana = []
    for r in L.maliyet_kayitlari(sd):
        if not icinde(r.get("zaman")):
            continue
        g = r.get("gorev")
        if L.ana_ajan_satiri_mi(r):
            ana.append(r)
        elif g in idler:
            mal_kart.setdefault(g, []).append(r)
    tum_mal = [r for rs in mal_kart.values() for r in rs] + ana

    out = {
        "tanimlar": TANIMLAR,
        "genel": _hesapla(kartlar, mal_kart, tum_mal, aralik is not None),
        "ornek": _ornekler(kartlar, tum_mal),
        "ana_ajan_payi": {"maliyet_usd": sum(float(r.get("maliyet_usd") or 0) for r in ana),
                          "token": sum(_tok(r) for r in ana)},
        "sinif": {},
        "basamak": {},
    }
    for anahtar, alan in (("sinif", "sinif"), ("basamak", "basamak")):
        gruplar: dict = {}
        for k in kartlar:
            gruplar.setdefault(k.get(alan) or "-", []).append(k)
        for ad, ks in sorted(gruplar.items()):
            mk = {k["id"]: mal_kart.get(k["id"], []) for k in ks}
            out[anahtar][ad] = _hesapla(ks, mk, [r for rs in mk.values() for r in rs], aralik is not None)

    bekleme = []
    for yol in sorted(glob.glob(os.path.join(sd, "onaylar", "O-*.json"))):
        o = _json(yol)
        if not isinstance(o, dict) or not icinde(o.get("olusturma")):
            continue
        kz = A._zaman((o.get("karar") or {}).get("zaman")) if isinstance(o.get("karar"), dict) else None
        ol = A._zaman(o.get("olusturma"))
        if kz and ol:
            bekleme.append((kz - ol).total_seconds())
    out["genel"]["onay_bekleme_sn"] = {"medyan": _medyan(bekleme), "p95": _p95(bekleme)}
    return out


def _f(v) -> str:
    if v is None:
        return "-"
    if isinstance(v, dict):
        return f"medyan {_f(v.get('medyan'))} / p95 {_f(v.get('p95'))}"
    return f"{v:.4g}" if isinstance(v, float) else str(v)


def tablo(s: dict) -> str:
    satir = ["KPI (genel)"]
    for ad in (*KPILER, "onay_bekleme_sn"):
        satir.append(f"  {ad:<24} {_f(s['genel'].get(ad)):<28} = {TANIMLAR[ad]['pay']} / {TANIMLAR[ad]['payda']}")
    a = s["ana_ajan_payi"]
    satir.append(f"  ana_ajan_payi            maliyet_usd {a['maliyet_usd']:.4f}, token {a['token']} (kartlara dağıtılmaz)")
    for baslik, grup in (("sinif", s["sinif"]), ("basamak", s["basamak"])):
        for ad, v in grup.items():
            satir.append(f"\n{baslik}: {ad}")
            for k in KPILER:
                satir.append(f"  {k:<24} {_f(v.get(k))}")
    return "\n".join(satir)
