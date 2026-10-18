"""Verimlilik metrikleri: kpi.olcum() çıktısındaki `verim` bölümü (I-067).

Saf hesap, dosya yazmaz. kpi.olcum kartları, defter ve zaman satırlarını süzüp buraya verir.
Yedi ana metrik ve beş tanı metriği burada tanımlıdır; her ölçü {deger, pay, payda} ya da
açıkça adlandırılmış alanlarla döner. Pay ya da payda 0 ise deger None.

Ana: basari_orani, tam_maliyet (başarılı iş başına, başarısız denemeler dahil), gecikme (p50/p95),
goodput, ilk_deneme, insan_mudahale, tam_token.
Tanı: cagri (araç çağrısı ve retry), model_kirilim, rol_kirilim, sure_kirilim, onbellek_isabet, yukseltme.
"""
from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analitik as A  # noqa: E402
import ork_lib as L  # noqa: E402

ONAYLI = ("onaylandi", "teslim")
# Kartın insan beklediğini ya da elle devreye girildiğini gösteren geçmiş olayları. Alt sınırdır:
# kullanıcının sohbette verdiği talimat kart geçmişine yazılmadığı için sayılmaz.
INSAN_OLAYLARI = ("beklemede", "politika-onay-engeli", "test-kilit-ac")
GOODPUT_SURE_SN = 3600

TANIMLAR = {
    "tam_maliyet_usd": "kart-bağlı bütün defter maliyeti (reddedilen ve iptal kart dahil) / onaylı kart",
    "tam_token": "kart-bağlı bütün token (dört kalem) / onaylı kart",
    "gecikme": "oluşturma → teslim/onay süresi, saniye; p50 medyan, p95 nearest-rank",
    "goodput_saat": "onaylı ve süresi eşik içinde kalan kart sayısı / pencere süresi (saat)",
    "ilk_deneme": "ilk denetim kararı onay olan kart / karar verilmiş kart",
    "insan_mudahale": "geçmişinde " + ", ".join(INSAN_OLAYLARI) + " olayı olan kart / kart (alt sınır)",
    "mudahale_sure_sn": "müdahale olayı → kartın bir sonraki olayı, saniye (medyan, p95)",
    "cagri": "zaman.jsonl'daki araç çağrısı satırı sayısı; işçi çağrısı/kart; reddedilen turdan sonraki ek işçi çağrısı",
    "sure_kirilim": "orkestrasyon (ana ajan), işçi toplamı ve duvar saati (aralık birleşimi), araç, insan bekleme",
}


def _oran(pay, payda, ondalik=4):
    return {"deger": round(pay / payda, ondalik) if payda else None, "pay": pay, "payda": payda}


def _sirali(x):
    return sorted(v for v in x if v is not None)


def _medyan(x):
    s = _sirali(x)
    if not s:
        return None
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def _p95(x):
    s = _sirali(x)
    return s[max(0, math.ceil(0.95 * len(s)) - 1)] if s else None


def _tok(r):
    return sum(int(r.get(a) or 0) for a in L._TOKEN_ALANLARI)


def _sure_sn(kart):
    """Oluşturma → teslim (yoksa onay) süresi, saniye; bitiş yoksa None. kpi._sure_sn ile aynı tanım."""
    gecmis = kart.get("gecmis") or []
    bit = None
    for olay in ("teslim", "onaylandi"):
        zs = [z for z in (A._zaman(e.get("zaman")) for e in gecmis if e.get("olay") == olay) if z]
        if zs:
            bit = max(zs)
            break
    bas = A._zaman(kart.get("olusturma"))
    return (bit - bas).total_seconds() if bit and bas else None


def mudahale_sureleri(kart):
    """Kartın insan müdahalesi olaylarının süreleri (sn): olay → kartın bir sonraki olayı. Sonraki olay yoksa atlanır."""
    g = sorted(kart.get("gecmis") or [], key=lambda e: e.get("zaman") or "")
    out = []
    for i, e in enumerate(g[:-1]):
        if e.get("olay") in INSAN_OLAYLARI:
            a, b = A._zaman(e.get("zaman")), A._zaman(g[i + 1].get("zaman"))
            if a and b and b >= a:
                out.append((b - a).total_seconds())
    return out


def _yukseltildi(kart):
    """Kart daha pahalı basamağa taşındı mı: `yukseltme` olayı ya da son basamak başlangıçtan farklı (analitik._basamak ile aynı ölçüt)."""
    bas, son = kart.get("baslangic_basamak"), kart.get("basamak")
    return any(e.get("olay") == "yukseltme" for e in kart.get("gecmis") or []) or bool(bas and son and bas != son)


def _birlesim_sn(araliklar):
    """Aralıkların birleşiminin uzunluğu (sn): paralel çalışan ajanlar çifte sayılmaz."""
    toplam, son_bit = 0.0, None
    for bas, bit in sorted(araliklar):
        if son_bit is None or bas > son_bit:
            toplam += (bit - bas).total_seconds()
            son_bit = bit
        elif bit > son_bit:
            toplam += (bit - son_bit).total_seconds()
            son_bit = bit
    return toplam


def _aralik(r):
    bit = A._zaman(r.get("zaman"))
    ms = r.get("sure_ms")
    if not bit or not ms:
        return None
    import datetime
    return bit - datetime.timedelta(milliseconds=ms), bit


def _kirilim(satirlar, anahtar):
    gruplar: dict = {}
    for r in satirlar:
        gruplar.setdefault(anahtar(r) or "-", []).append(r)
    out = {}
    for ad, rs in sorted(gruplar.items(), key=lambda kv: -sum(r.get("maliyet_usd") or 0 for r in kv[1])):
        k = L.kalemler(rs)
        out[ad] = {"satir": len(rs), "usd": k["usd"], "token": k["token"]}
    return out


def pencere_saat(tum_kartlar, gun_esik=None, aralik=None, simdi=None):
    """Goodput paydası. Öncelik: aralık, sonra 'son N gün' başlangıcı, yoksa ilk kart → son bitiş."""
    import datetime
    if aralik is not None:
        return (aralik[1] - aralik[0]).total_seconds() / 3600
    simdi = simdi or datetime.datetime.now().astimezone()
    if gun_esik is not None:
        return max((simdi - gun_esik).total_seconds(), 0) / 3600
    bas = [z for z in (A._zaman(k.get("olusturma")) for k in tum_kartlar) if z]
    bit = []
    for k in tum_kartlar:
        for e in k.get("gecmis") or []:
            if e.get("olay") in ("teslim", "onaylandi"):
                z = A._zaman(e.get("zaman"))
                if z:
                    bit.append(z)
    return (max(bit) - min(bas)).total_seconds() / 3600 if bas and bit else 0.0


def hesapla(tum_kartlar, satirlar, zaman_satirlari, onay_bekleme_sn, saat, esik_sn=GOODPUT_SURE_SN):
    """tum_kartlar: pencere içindeki bütün kartlar (iptal dahil). satirlar: pencere içindeki tekilleştirilmiş defter satırları.
    zaman_satirlari: pencere içindeki zaman.jsonl satırları. onay_bekleme_sn: karar süreleri listesi."""
    kartlar = [k for k in tum_kartlar if k.get("durum") != "iptal"]
    onayli = [k for k in kartlar if k.get("durum") in ONAYLI]
    idler = {k["id"] for k in tum_kartlar}
    karta = [r for r in satirlar if r.get("gorev") in idler]
    ana = [r for r in satirlar if L.ana_ajan_satiri_mi(r)]

    # ana metrikler
    tam_usd = sum(float(r.get("maliyet_usd") or 0) for r in karta)
    tam_tok = sum(_tok(r) for r in karta)
    sureler = [_sure_sn(k) for k in kartlar]
    sureler = [s for s in sureler if s is not None]
    iyi = [k for k in onayli if (_sure_sn(k) is not None and _sure_sn(k) <= esik_sn)]
    ilk = []
    for k in kartlar:
        kararlar = [d.get("karar") for d in k.get("denetimler") or [] if isinstance(d, dict) and d.get("karar") in ("onay", "ret")]
        if kararlar:
            ilk.append(kararlar[0])
    musteri = [k for k in kartlar if any(e.get("olay") in INSAN_OLAYLARI for e in k.get("gecmis") or [])]
    msure = [s for k in kartlar for s in mudahale_sureleri(k)]

    # tanı
    isci = sum(len(k.get("isciler") or []) for k in kartlar)
    ek_isci = sum(max(0, len(k.get("isciler") or []) - 1) for k in kartlar)
    isci_satir = [r for r in karta if r.get("agent_id")]
    araclar = [z for z in zaman_satirlari if z.get("tur") == "arac"]
    aralik = [a for a in (_aralik(r) for r in isci_satir) if a]
    insan_sn = sum(onay_bekleme_sn) + sum(msure)

    return {
        "tanimlar": TANIMLAR,
        "basari_orani": _oran(len(onayli), len(kartlar)),
        "tam_maliyet_usd": {"deger": round(tam_usd / len(onayli), 6) if onayli else None, "pay": round(tam_usd, 6), "payda": len(onayli)},
        "tam_token": {"deger": round(tam_tok / len(onayli), 1) if onayli else None, "pay": tam_tok, "payda": len(onayli)},
        "gecikme": {"p50_sn": _medyan(sureler), "p95_sn": _p95(sureler), "n": len(sureler)},
        "goodput_saat": {"deger": round(len(iyi) / saat, 4) if saat else None, "pay": len(iyi), "pencere_saat": round(saat, 2), "esik_sn": esik_sn},
        "ilk_deneme": _oran(ilk.count("onay"), len(ilk)),
        "insan_mudahale": dict(_oran(len(musteri), len(kartlar)), olaylar=list(INSAN_OLAYLARI),
                               sure_sn={"medyan": _medyan(msure), "p95": _p95(msure), "n": len(msure)}),
        "cagri": {"arac_cagrisi": len(araclar),
                  "isci_cagrisi_kart": _oran(isci, len(kartlar)),
                  "ek_isci_cagrisi": ek_isci},
        "onbellek_isabet": _oran(sum(int(r.get("onbellek_okuma") or 0) for r in satirlar),
                                 sum(int(r.get(a) or 0) for r in satirlar for a in ("giris", "onbellek_okuma", "onbellek_yazma"))),
        "yukseltme": _oran(sum(1 for k in kartlar if _yukseltildi(k)), len(kartlar)),
        "model_kirilim": _kirilim(satirlar, lambda r: A._kisa_model(r.get("model"))),
        "rol_kirilim": _kirilim(satirlar, lambda r: A._rol(r.get("ajan"))),
        "sure_kirilim": {
            "orkestrasyon_sn": round(sum(float(r.get("sure_ms") or 0) for r in ana) / 1000, 1),
            "isci_toplam_sn": round(sum(float(r.get("sure_ms") or 0) for r in isci_satir) / 1000, 1),
            "isci_duvar_sn": round(_birlesim_sn(aralik), 1),
            "arac_sn": round(sum(float(z.get("sure_ms") or 0) for z in araclar) / 1000, 1),
            "insan_bekleme_sn": round(insan_sn, 1),
        },
    }


def satirlar(v: dict) -> list[str]:
    """Okunur tablo satırları (kpi.tablo ekler)."""
    f = lambda x: "-" if x is None else (f"{x:.4g}" if isinstance(x, float) else str(x))  # noqa: E731
    s = ["", "Verimlilik (I-067)"]
    s.append(f"  basari_orani             {f(v['basari_orani']['deger'])} ({v['basari_orani']['pay']}/{v['basari_orani']['payda']})")
    s.append(f"  tam_maliyet_usd          {f(v['tam_maliyet_usd']['deger'])} = {TANIMLAR['tam_maliyet_usd']}")
    s.append(f"  tam_token                {f(v['tam_token']['deger'])}")
    g = v["gecikme"]
    s.append(f"  gecikme                  p50 {f(g['p50_sn'])} sn / p95 {f(g['p95_sn'])} sn (n={g['n']})")
    gp = v["goodput_saat"]
    s.append(f"  goodput_saat             {f(gp['deger'])} kart/saat ({gp['pay']} kart, {gp['pencere_saat']} saat, eşik {gp['esik_sn']} sn)")
    s.append(f"  ilk_deneme               {f(v['ilk_deneme']['deger'])} ({v['ilk_deneme']['pay']}/{v['ilk_deneme']['payda']})")
    im = v["insan_mudahale"]
    s.append(f"  insan_mudahale           {f(im['deger'])} ({im['pay']}/{im['payda']}); süre medyan {f(im['sure_sn']['medyan'])} sn / p95 {f(im['sure_sn']['p95'])} sn")
    c = v["cagri"]
    s.append(f"  cagri                    araç {c['arac_cagrisi']}; işçi/kart {f(c['isci_cagrisi_kart']['deger'])}; ek işçi {c['ek_isci_cagrisi']}")
    s.append(f"  onbellek_isabet          {f(v['onbellek_isabet']['deger'])}; yukseltme {f(v['yukseltme']['deger'])} ({v['yukseltme']['pay']}/{v['yukseltme']['payda']})")
    k = v["sure_kirilim"]
    s.append(f"  sure_kirilim             orkestrasyon {k['orkestrasyon_sn']} sn, işçi toplam {k['isci_toplam_sn']} sn (duvar {k['isci_duvar_sn']} sn), "
             f"araç {k['arac_sn']} sn, insan bekleme {k['insan_bekleme_sn']} sn")
    for baslik, grup in (("model", v["model_kirilim"]), ("rol", v["rol_kirilim"])):
        for ad, e in grup.items():
            s.append(f"  {baslik}: {ad:<14} usd {e['usd']['toplam']:.4f} token {e['token']['toplam']} (satır {e['satir']})")
    return s
