"""orkestra komutları: onay (orkestra.py bölünmesinden)."""
from __future__ import annotations

import argparse
import collections
import csv
import datetime
import io
import json
import hashlib
import os
import re
import subprocess
import sys
import time

import ork_lib as L  # noqa: E402
import ret_nedeni as RN  # noqa: E402
import soru_sinif as SS  # noqa: E402
from komutlar._ortak import BETIK_DIZINI, hata, sd_gerekli  # noqa: E402


def cmd_perspektif(a):
    if getattr(a, "komut", None) == "ruya":  # eski ad: takma ad olarak çalışır
        print("uyarı: `orkestra ruya` eski addır; `orkestra perspektif` kullan.", file=sys.stderr)
    sd = sd_gerekli()
    sys.path.insert(0, BETIK_DIZINI)
    import perspektif
    if a.islem == "durum":
        print(json.dumps(perspektif.durum(sd), ensure_ascii=False, indent=2))
    elif a.islem == "basla":
        print(perspektif.baslat(sd, L.proje_dizini(), zorla=True))
    elif a.islem == "bitti":
        perspektif.bitti_isaretle(sd)
        print("perspektif raporu okundu olarak işaretlendi")
    elif a.islem == "basladi":
        perspektif.basladi_isaretle(sd)
        print("perspektif başladı")
    elif a.islem == "kaydet":
        if not a.yol or not os.path.exists(a.yol):
            hata("rapor yolu gerekli ve var olmalı: orkestra perspektif kaydet <yol>")
        perspektif.kaydet(sd, a.yol)
        print(f"perspektif raporu kaydedildi: {a.yol}")
    elif a.islem == "hafiza":
        print(perspektif.hafiza_dizini(L.proje_dizini()))
    elif a.islem == "girdi":
        proje = L.proje_dizini()
        g = perspektif.girdi_yaz(sd, proje, a.yol or perspektif.hafiza_dizini(proje))
        print(f"{os.path.join(sd, 'perspektif', 'girdi.json')} · imza {g['imza']} · anomali {g['anomali']['sayim']} · "
              f"ölü yol {g['hafiza']['olu_yol_sayisi']}")


def _onay_oturumu(a) -> str:
    o = getattr(a, "oturum", None) or os.environ.get("CLAUDE_SESSION_ID") or os.environ.get("CLAUDE_CODE_SESSION_ID")
    return o or "cli"


def _onay_calistir(f, *args, **kw):
    import onay
    try:
        return f(onay, *args, **kw)
    except ValueError as e:
        hata(str(e))


def _onay_satir(k: dict) -> str:
    return f"{k['id']}  {k['durum']:<11} {k['tur']:<10} {k['baslik']}"


def cmd_onay(a):
    sd = sd_gerekli()
    import onay
    i = a.alt
    if i == "liste":
        onay.esitle(sd)
        kayitlar = onay.liste(sd, durum=a.durum, tur=a.tur)
        if a.json:
            print(json.dumps(kayitlar, ensure_ascii=False, indent=2))
        else:
            for k in kayitlar:
                print(_onay_satir(k))
            if not kayitlar:
                print("kayıt yok")
    elif i == "goster":
        k = onay.goster(sd, a.id)
        if not k:
            hata(f"onay kaydı bulunamadı: {a.id}")
        print(json.dumps(k, ensure_ascii=False, indent=2))
    elif i == "iste":
        k = _onay_calistir(lambda m: m.iste(sd, a.baslik, a.metin, secenekler=a.secenek, oturum=a.oturum))
        print(k["id"])
    elif i == "karar":
        k = _onay_calistir(lambda m: m.karar_ver(sd, a.id, "onay" if a.onay else "ret", secim=a.secim,
                                                 not_=a.not_, kim="cli"))
        print(f"{k['id']} → {k['durum']}")
    elif i == "al":
        k = _onay_calistir(lambda m: m.al(sd, a.id, _onay_oturumu(a)))
        print(f"{k['id']} → {k['durum']}")
    elif i == "uygulandi":
        k = _onay_calistir(lambda m: m.uygulandi(sd, a.id, a.ozet, oturum=_onay_oturumu(a)))
        print(f"{k['id']} → {k['durum']}")
    elif i == "iptal":
        k = _onay_calistir(lambda m: m.iptal(sd, a.id, a.not_))
        print(f"{k['id']} → {k['durum']}")
    elif i == "esitle":
        onay.esitle(sd)
        s = onay.sayac(sd)
        print(f"eşitlendi: {s['bekliyor']} bekliyor, {s['uygulanacak']} uygulanacak")
    elif i == "vaat" or i.startswith("etki-"):
        _onay_etki(sd, a)


def _etki_satir(k: dict) -> dict:
    """etki-liste için tek kaydın özeti (salt okuma)."""
    e = k.get("etki") if isinstance(k.get("etki"), dict) else {}
    v = k.get("vaat") if isinstance(k.get("vaat"), dict) else {}
    iz = e.get("izleme") if isinstance(e.get("izleme"), dict) else {}
    gunluk = e.get("gunluk") if isinstance(e.get("gunluk"), list) else []
    son = gunluk[-1] if gunluk and isinstance(gunluk[-1], dict) else {}
    return {"id": k.get("id"), "baslik": k.get("baslik"), "metrik": v.get("metrik"), "yon": v.get("yon"),
            "olculebilir": bool(v.get("olculebilir")), "uygulama_tarihi": e.get("uygulama_tarihi"),
            "gun": len(gunluk), "taban": (e.get("taban") or {}).get("deger") if isinstance(e.get("taban"), dict) else None,
            "birikim": son.get("birikim_deger"), "ornek": son.get("birikim_ornek"),
            "gidisat": iz.get("son_gidisat") or e.get("durum"), "ayni_gidisat_gun": iz.get("ayni_gidisat_gun"),
            "izleme": iz.get("durum"), "soru_bekliyor": bool(e.get("soru_bekliyor")),
            "karar": (e.get("karar") or {}).get("sonuc") if isinstance(e.get("karar"), dict) else None}


def _etki_izleme_tamamla(sd: str):
    """Eksik `izleme.durum` olan (yarım yazılmış) izleme alanını 'suruyor' ile tamamlar; etki.py durumsuz izlemeyi
    durmuş sayar. Yalnız uygulanmış ve kapanışı olmayan kayıtlara dokunur."""
    import etki
    import onay
    with etki._islem(sd):
        for k in onay._hepsi(sd):
            e = k.get("etki")
            iz = e.get("izleme") if isinstance(e, dict) else None
            if isinstance(iz, dict) and not iz.get("durum") and e.get("uygulama_tarihi") and not iz.get("kapanis"):
                iz["durum"] = "suruyor"
                iz.setdefault("kapanis", None)
                onay._kayit_yaz(sd, k)


def _onay_etki(sd: str, a):
    """Etki ölçümü alt komutları (vaat, etki-izle, etki-liste, etki-kapat, etki-geri-al); mantık etki.py'dedir."""
    import etki
    i = a.alt
    try:
        if i in ("etki-izle", "etki-kapat", "etki-geri-al"):
            _etki_izleme_tamamla(sd)
        if i == "vaat":
            if not a.olculemez and not a.metrik:
                hata("ölçülebilir vaatte --metrik zorunlu (ölçülemezse --olculemez).")
            if a.olculemez and (a.metrik or a.yon):
                hata("--olculemez ile --metrik/--yon birlikte verilmez.")
            vaat = {"metin": a.metin, "olculebilir": not a.olculemez, "metrik": None if a.olculemez else a.metrik,
                    "yon": None if a.olculemez else a.yon, "kapsam": a.kapsam or "genel"}
            k = etki.vaat_ayarla(sd, a.id, vaat)
            print(f"{k['id']} vaat yazıldı ({'ölçülemez' if a.olculemez else a.metrik + ' ' + a.yon})")
        elif i == "etki-izle":
            guncel = etki.izle(sd, a.id)
            print(f"izlendi: {len(guncel)} kayıt güncellendi" + (f" ({', '.join(guncel)})" if guncel else ""))
        elif i == "etki-liste":
            satirlar = [_etki_satir(k) for k in etki.liste(sd)
                        if isinstance(k.get("etki"), dict) and k["etki"].get("uygulama_tarihi")]
            if a.json:
                print(json.dumps(satirlar, ensure_ascii=False, indent=2))
            else:
                for s in satirlar:
                    print(f"{s['id']}  {s['uygulama_tarihi']}  gün {s['gun']:<3} {s['gidisat'] or '-':<14} "
                          f"{s['izleme'] or '-':<13} {s['metrik'] or 'ölçülemez'}  {s['baslik']}")
                if not satirlar:
                    print("kayıt yok")
        elif i in ("etki-kapat", "etki-geri-al"):
            k = etki._gerekli(sd, a.id)
            if not (isinstance(k.get("etki"), dict) and k["etki"].get("uygulama_tarihi")):
                hata(f"{a.id} henüz uygulanmamış; izleme yok.")
            if i == "etki-kapat":
                k = etki.kapat(sd, a.id, a.sonuc, a.not_ or "")
                print(f"{k['id']} izleme kapandı ({a.sonuc})")
            else:
                k = etki.geri_al(sd, a.id, a.neden)
                print(f"{k['id']} geri alındı; izleme durdu")
    except ValueError as e:
        hata(str(e))


def cmd_kural(a):
    sd = sd_gerekli()
    import onay
    i = a.alt
    kaynak = _onay_oturumu(a) if os.environ.get("CLAUDE_SESSION_ID") or os.environ.get("CLAUDE_CODE_SESSION_ID") else "cli"
    if i == "liste":
        kayitlar = onay.kurallar(sd)
        if a.json:
            print(json.dumps(kayitlar, ensure_ascii=False, indent=2))
        else:
            for r in kayitlar:
                print(f"{r['id']}  {r['durum']:<11} {r['metin']}")
            if not kayitlar:
                print("kural yok")
    elif i == "oner":
        r = _onay_calistir(lambda m: m.kural_oner(sd, a.metin, a.neden, kaynak))
        k = onay._anahtarli(sd, f"kural:{r['id']}")
        print(f"{r['id']} önerildi" + (f" (onay {k['id']})" if k else ""))
    elif i == "ekle":
        r = _onay_calistir(lambda m: m.kural_ekle(sd, a.metin, a.neden, kaynak="cli"))
        print(f"{r['id']} etkin")
    elif i == "duzenle":
        r = _onay_calistir(lambda m: m.kural_duzenle(sd, a.id, a.metin, a.neden))
        print(f"{r['id']} güncellendi")
    elif i == "kaldir":
        r = _onay_calistir(lambda m: m.kural_kaldir(sd, a.id, a.not_))
        print(f"{r['id']} → {r['durum']}")


def kaydet(alt):
    """Bu modülün alt komutlarını ana ayrıştırıcıya ekler."""
    ru = alt.add_parser("perspektif", aliases=["ruya"])  # "ruya": eski ad, geriye uyumlu takma ad
    ru.add_argument("islem", choices=["durum", "basla", "basladi", "kaydet", "bitti", "hafiza", "girdi"])
    ru.add_argument("yol", nargs="?")
    ru.set_defaults(f=cmd_perspektif)

    on = alt.add_parser("onay").add_subparsers(dest="alt", required=True)
    x = on.add_parser("liste")
    x.add_argument("--durum")
    x.add_argument("--tur")
    x.add_argument("--json", action="store_true")
    x = on.add_parser("goster")
    x.add_argument("id")
    x = on.add_parser("iste")
    x.add_argument("--baslik", required=True)
    x.add_argument("--metin", required=True)
    x.add_argument("--secenek", action="append", default=[])
    x.add_argument("--oturum")
    x = on.add_parser("karar")
    x.add_argument("id")
    g_ = x.add_mutually_exclusive_group(required=True)
    g_.add_argument("--onay", action="store_true")
    g_.add_argument("--ret", action="store_true")
    x.add_argument("--secim")
    x.add_argument("--not", dest="not_")
    x = on.add_parser("al")
    x.add_argument("id")
    x.add_argument("--oturum")
    x = on.add_parser("uygulandi")
    x.add_argument("id")
    x.add_argument("--ozet", required=True)
    x.add_argument("--oturum")
    x = on.add_parser("iptal")
    x.add_argument("id")
    x.add_argument("--not", dest="not_", required=True)
    on.add_parser("esitle")
    x = on.add_parser("vaat", help="onay kaydına ölçülebilir vaat yaz (etki ölçümü)")
    x.add_argument("id")
    x.add_argument("--metin", required=True)
    x.add_argument("--metrik")
    x.add_argument("--yon")
    x.add_argument("--kapsam")
    x.add_argument("--olculemez", action="store_true")
    x = on.add_parser("etki-izle", help="eksik günleri uygulama gününden bugüne doldur (idempotent)")
    x.add_argument("id", nargs="?")
    x = on.add_parser("etki-liste")
    x.add_argument("--json", action="store_true")
    x = on.add_parser("etki-kapat", help="izlemeyi kapat; doğru/yanlış karar kullanıcınındır")
    x.add_argument("id")
    x.add_argument("--sonuc", required=True)
    x.add_argument("--not", dest="not_")
    x = on.add_parser("etki-geri-al", help="değişiklik geri alındı: izleme durur")
    x.add_argument("id")
    x.add_argument("--neden", required=True)
    alt.choices["onay"].set_defaults(f=cmd_onay)

    ku = alt.add_parser("kural").add_subparsers(dest="alt", required=True)
    x = ku.add_parser("liste")
    x.add_argument("--json", action="store_true")
    for ad in ("oner", "ekle"):
        x = ku.add_parser(ad)
        x.add_argument("--metin", required=True)
        x.add_argument("--neden", default="")
    x = ku.add_parser("duzenle")
    x.add_argument("id")
    x.add_argument("--metin", required=True)
    x.add_argument("--neden")
    x = ku.add_parser("kaldir")
    x.add_argument("id")
    x.add_argument("--not", dest="not_", required=True)
    alt.choices["kural"].set_defaults(f=cmd_kural)

    import niyet
    niyet.ekle_ayristirici(alt)
