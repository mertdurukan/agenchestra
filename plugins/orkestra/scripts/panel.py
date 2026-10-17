"""Orkestra HTML canlı paneli: bu bilgisayardaki TÜM Claude çalışma alanları için tek yerel sunucu (yalnız 127.0.0.1).

GET /                          → Son olaylar sayfası (assets/simdi.html); /index.html aynı
GET /maliyet                   → Maliyet sayfası (assets/maliyet.html; yoksa "hazırlanıyor")
GET /verim                     → Maliyet ve verim sayfası (maliyet.html ile birleşik)
GET /ortak.css, /ortak.js      → üç sayfanın ortak tasarım sistemi
GET /alanlar.json              → çalışma alanları (ad, yol, orkestra kurulu mu, son etkinlik)
GET /ozet.json?alan=<id>       → seçili alanın anlık görüntüsü (orkestra varsa tam, yoksa sohbet maliyetleri)
GET /analitik, /analitik.html  → 301 /verim (sorgu dizesi korunur)
GET /analitik.json?alan=<id>   → seçili orkestralı alanın analitiği (analitik.alan_analitigi)
GET /analitik-tum.json         → bütün alanların toplamı ve karşılaştırması
GET /simdi.json                → her sohbet: ne yapılıyor, neye yarayacak, kimi bekliyor (niyet.gorunum)
POST /ac?oturum=<id>           → sohbeti Claude uygulamasında aç (X-Orkestra: 1 başlığı zorunlu)
GET /onaylar, /onaylar.html    → Onay merkezi sayfası (assets/onaylar.html; yoksa "hazırlanıyor")
GET /kurallar, /kurallar.html  → Onaylar, etki ve kurallar sayfası (onaylar.html ile birleşik)
GET /onaylar.json?alan=<id>    → onay kuyruğu: sayaç, kayıtlar, perspektif (rapor, durum)
GET /kurallar.json?alan=<id>   → etkin kurallar, öneriler, geçmiş, kural kaynakları
GET /isler, /isler.html        → Dashboard sayfası (sohbetler + işler; assets/isler.html; yoksa "hazırlanıyor")
GET /isler.json?alan=<id>      → işler: kovalar (yapıldı/şimdi/sırada/planda kart yok/iptal), maliyet, kartsız açık kartlar
GET /teknik, /teknik.html      → Teknik detay sayfası (iş seç, kartlar yapılma sırasıyla, tıklayınca 7 blok; assets/teknik.html)
GET /teknik.json?alan=<id>[&is=<I-NNN>[&kart=<G-NNN>]] → iş listesi | işin kart özetleri (oluşturma sırası) | tek kartın 7 bloğu (teknik.derle); salt okunur; bilinmeyen alan/iş/kart → 404 + hata JSON'u
GET /etki, /etki.html          → Etki sayfası (uygulanan kararların etkisi; assets/etki.html)
GET /api/etki?alan=<id>        → etki listesi + gün gün seri + doğru karar oranı (yalnız kapatılmış izlemeler); salt okuma
GET /onay-sayac.json           → {alan_id: onay sayacı} (sekme rozeti)
GET /yapilacaklar              → Yapılacaklar sayfası (assets/yapilacaklar.html)
GET /api/todo?alan=<id>[&is=<id>] → işin açık/biten maddeleri + açık iş listesi (salt okunur; POST 405)
GET /api/kullanici-todo?alan=<id> → kullanıcının kendi yapılacakları
POST /perspektif-calistir?alan=<id> → Claude uygulamasında yeni sohbet açıp /orkestra:perspektif şimdi çalıştırır (X-Orkestra: 1, yerel Host)
POST /api/isler-sifirla?alan=<id> → {onay: true}: Dashboard iş verisini yedeğe alıp sıfırlar (X-Orkestra: 1, yerel Host)
POST /api/kullanici-todo?alan=<id> → {eylem: ekle|sil, metin | id} (X-Orkestra: 1, yerel Host, ≤64 KB)
POST /onay?alan=<id>           → karar / simdi-uygula / kural-ekle / kural-duzenle / kural-kaldir (X-Orkestra: 1, yerel Host, ≤64 KB)
GET /saglik                    → "ok"
Sunucu durumu ~/.claude/orkestra-panel/panel.json'da; `orkestra panel` çalışan sunucuyu yeniden kullanır.
Test sunucusu: `panel.py _kos <port> --test` panel.json'u YAZMAZ (gerçek panelin durum dosyasını ezmez; G-096).
"""
from __future__ import annotations

import http.server
import glob
import json
import os
import re
import select
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cfg  # noqa: E402
import ork_lib as L  # noqa: E402
import ozet  # noqa: E402
import analitik  # noqa: E402
import niyet  # noqa: E402
import onay  # noqa: E402
import kural_dosya  # noqa: E402
import kullanici_todo as KT  # noqa: E402

POST_MAX = 64 * 1024
DOSYA_POST_MAX = 2 * kural_dosya.DOSYA_MAX  # JSON kaçışları için pay
POST_ATIM_MAX = 4 * 1024 * 1024  # bunun altındaki aşırı gövde okunup atılır

ASSETS = os.path.join(L.PLUGIN_ROOT, "assets")
# yol → (dosya, içerik türü); sayfa dosyası henüz yoksa "hazırlanıyor" sayfası döner
SAYFALAR = {"/": "simdi.html", "/index.html": "simdi.html", "/simdi.html": "simdi.html",
            "/maliyet": "maliyet.html", "/maliyet.html": "maliyet.html",
            "/verim": "maliyet.html", "/verim.html": "maliyet.html",
            "/onaylar": "onaylar.html", "/onaylar.html": "onaylar.html",
            "/kurallar": "onaylar.html", "/kurallar.html": "onaylar.html",
            "/isler": "isler.html", "/isler.html": "isler.html",
            "/teknik": "teknik.html", "/teknik.html": "teknik.html",
            "/etki": "onaylar.html", "/etki.html": "onaylar.html",
            "/yapilacaklar": "yapilacaklar.html", "/yapilacaklar.html": "yapilacaklar.html"}
STATIK = {"/gorsel.css": ("gorsel.css", "text/css; charset=utf-8"),
          "/gorsel.js": ("gorsel.js", "application/javascript; charset=utf-8"),
          "/ortak.css": ("ortak.css", "text/css; charset=utf-8"),
          "/ortak.js": ("ortak.js", "application/javascript; charset=utf-8"),
          "/logo.png": ("logo.png", "image/png")}
# sayfa başına ayrı betik (<sayfa>.js) ve büyük sayfa için stil (<sayfa>.css); yalnız bu liste sunulur
SAYFA_JS = ("simdi", "isler", "maliyet", "verim", "onaylar", "kurallar", "etki", "yapilacaklar", "teknik")
SAYFA_CSS = ("simdi", "isler", "maliyet", "verim", "etki", "yapilacaklar", "teknik")
STATIK.update({f"/{ad}.js": (f"{ad}.js", "application/javascript; charset=utf-8") for ad in SAYFA_JS})
STATIK.update({f"/{ad}.css": (f"{ad}.css", "text/css; charset=utf-8") for ad in SAYFA_CSS})
YONLENDIR = {"/analitik": "/verim", "/analitik.html": "/verim"}
DURUM = os.path.join(L.GENEL_DIZIN, "panel.json")
SURUM = "15"  # sayfa/sunucu sözleşmesi; değişince eski sunucu yeniden başlatılır


def _alan(alan_id, kesin: bool):
    """Alan sözlüğü ya da None. kesin=False: ozet.alan_ozeti ile aynı geri düşüş (ilk orkestralı alan)."""
    alanlar = L.calisma_alanlari()
    a = next((x for x in alanlar if x["id"] == alan_id), None)
    if kesin:
        return a
    return a or next((x for x in alanlar if x["orkestra"]), None) or (alanlar[0] if alanlar else None)


def _alan_sd(alan_id, kesin: bool = False):
    """(alan, sd) ya da (None, hata sözlüğü)."""
    a = _alan(alan_id, kesin)
    if not a or not a.get("orkestra"):
        return None, {"acik": False, "hata": "Bu çalışma alanında orkestra açık değil."}
    return a, os.path.join(a["yol"], ".claude", "orkestra")


def _alan_kisa(a: dict) -> dict:
    return {"id": a["id"], "ad": a["ad"], "yol": a["yol"]}


def _simdi_json(alan_id: str | None) -> dict:
    """Sohbet görünümü; alan verilirse yalnız o çalışma alanının sohbetleri (bilinmeyen alan → boş liste)."""
    if not alan_id:
        return niyet.gorunum()
    a = next((x for x in L.calisma_alanlari() if x["id"] == alan_id), None)
    if a is None:
        return {"uretim": L.simdi(), "oturumlar": [], "akis": [], "sayac": {}, "alan": {"id": alan_id}}
    g = niyet.gorunum(alan_yol=a["yol"])
    g["alan"] = _alan_kisa(a)
    return g


def _perspektif(sd: str) -> dict:
    """En yeni rapor (sd/perspektif/ ve sd/ruya/ içinden tarih damgasına göre) ve perspektif durumu; modül yoksa durum None."""
    rapor = None
    try:
        rapor = onay.en_yeni_rapor(sd)
    except Exception:  # noqa: BLE001
        rapor = None
    try:
        import perspektif  # noqa: PLC0415
        d = perspektif.durum(sd)
        son = d.get("son_perspektif")
        return {"rapor": rapor, "durum": {"son_perspektif": son, "son_ruya": son,  # son_ruya: eski anahtar (geriye uyum)
                                          "calisiyor": d.get("calisiyor"), "okunmamis_rapor": d.get("okunmamis_rapor")}}
    except Exception:  # noqa: BLE001
        return {"rapor": rapor, "durum": None}


def _arka_plan(perspektif_durum: dict | None, uygulama: dict | None) -> list[dict]:
    """Onaylarla ilgili süren arka plan görevleri: perspektif koşusu ve onaylı kararların uygulanması.
    Boş liste = süren yok (Onaylar sayfası satır göstermez). Sohbet türü için _sohbet_arka_plan (İşler sayfası)."""
    out = []
    calisiyor = (perspektif_durum or {}).get("calisiyor")
    if calisiyor:
        out.append({"tur": "perspektif", "ad": "Perspektif koşusu", "baslangic": calisiyor})
    if uygulama:
        out.append({"tur": "uygulama", "ad": "Onaylı kararlar uygulanıyor", "baslangic": uygulama.get("baslangic")})
    return out


def _sohbet_arka_plan(a: dict) -> list[dict]:
    """Arka plan işi süren sohbetler (İşler sayfası); yalnız Claude'un çalıştığı olanlar."""
    out = []
    try:
        for r in niyet.gorunum(alan_yol=a["yol"]).get("oturumlar", []):
            if r.get("arka_plan") and r.get("bekleyen") == "claude":
                out.append({"tur": "sohbet", "ad": r.get("ne") or r.get("sohbet") or r.get("kisa"),
                            "baslangic": r.get("son_zaman")})
    except Exception:  # noqa: BLE001
        pass
    return out


def _todo_sayac(sd: str) -> dict:
    """Açık işlerin todo sayımı (IK.todo_ozet): {biten, kalan, toplam, isler: [{id, ad, biten, kalan}]}; todo'su olmayan iş atlanır."""
    import is_kaydi as IK  # noqa: PLC0415
    isler, biten, kalan = [], 0, 0
    try:
        for g in IK.is_liste(sd, "acik"):
            t = IK.todo_ozet(g["klasor"])
            if not t["toplam"]:
                continue
            k = len(t["acik_maddeler"])
            isler.append({"id": g["id"], "ad": IK.is_adi(g.get("baslik", "")), "biten": t["biten"], "kalan": k})
            biten += t["biten"]
            kalan += k
    except Exception:  # noqa: BLE001
        pass
    return {"biten": biten, "kalan": kalan, "toplam": biten + kalan, "isler": isler}


def _onaylar_json(alan_id) -> dict:
    a, sd = _alan_sd(alan_id)
    if a is None:
        return sd
    onay.esitle(sd)
    kayitlar = onay.liste(sd)
    bekleyen = [k for k in kayitlar if k.get("durum") == "bekliyor"]
    diger = [k for k in kayitlar if k.get("durum") != "bekliyor"]
    persp = _perspektif(sd)
    uygulama = onay.uygulama_durumu(sd)
    return {"acik": True, "alan": _alan_kisa(a), "sayac": onay.sayac(sd),
            "kayitlar": bekleyen + diger[:max(0, 200 - len(bekleyen))],
            "perspektif": persp, "uygulama": uygulama, "uretim": L.simdi(),
            "arka_plan": _arka_plan(persp.get("durum"), uygulama)}


def _etki_kayit(k: dict, hepsi: list) -> dict:
    """Etki sekmesi için tek kayıt: liste satırı + gün gün seri + aynı dönemde uygulanan diğer kayıtlar."""
    import etki  # noqa: PLC0415
    e = k["etki"]
    vaat = k.get("vaat") if isinstance(k.get("vaat"), dict) else {}
    olculebilir = bool(vaat.get("olculebilir"))
    seri = [dict(s) for s in (e.get("gunluk") or []) if isinstance(s, dict)] if olculebilir else []
    iz = e.get("izleme") if isinstance(e.get("izleme"), dict) else {}
    taban = e.get("taban") if isinstance(e.get("taban"), dict) else None
    son = seri[-1] if seri else None
    if not olculebilir:
        gidisat = "olculemez"
    else:
        gidisat = (son or {}).get("gidisat") or iz.get("son_gidisat") or "yetersiz-veri"
    ayni = int(iz.get("ayni_gidisat_gun") or 0)
    durum = iz.get("durum") or ("olculemez" if not olculebilir else "suruyor")
    soru = bool(olculebilir and durum == "suruyor" and gidisat == "kotu" and ayni >= etki.SORU_GUN)
    bas = e.get("uygulama_tarihi")
    bitis = None if durum in ("suruyor", "olculemez") else (str(iz.get("kapanis") or "")[:10] or None)
    diger = []
    for o in hepsi:
        oe = o.get("etki")
        if o.get("id") == k.get("id") or not isinstance(oe, dict) or not oe.get("uygulama_tarihi"):
            continue
        oiz = oe.get("izleme") if isinstance(oe.get("izleme"), dict) else {}
        o_bitis = None if (oiz.get("durum") or "suruyor") in ("suruyor", "olculemez") else (str(oiz.get("kapanis") or "")[:10] or None)
        # dönemler kesişiyorsa (bitişi olmayan izleme hâlâ sürüyor sayılır) diğer kayıt işaretlenir
        if (bitis is None or oe["uygulama_tarihi"] <= bitis) and (o_bitis is None or o_bitis >= bas):
            diger.append({"id": o["id"], "tarih": oe["uygulama_tarihi"]})
    diger.sort(key=lambda d: (d["tarih"], d["id"]))
    return {"id": k.get("id"), "baslik": k.get("baslik"), "olculebilir": olculebilir, "metin": vaat.get("metin") or "",
            "metrik": vaat.get("metrik"), "yon": vaat.get("yon"), "esik": vaat.get("esik"),
            "uygulama_tarihi": bas, "gun": int((son or {}).get("gun") or 0),
            "taban": {"deger": taban.get("deger"), "ornek": taban.get("ornek")} if taban else None,
            "birikim": {"deger": son.get("birikim_deger"), "ornek": son.get("birikim_ornek")} if son else None,
            "gidisat": gidisat, "ayni_gidisat_gun": ayni, "soru_bekliyor": soru, "izleme_durum": durum,
            "karar": e.get("karar"), "seri": seri, "diger_uygulamalar": diger}


def _etki_json(alan_id) -> dict:
    import etki  # noqa: PLC0415
    a, sd = _alan_sd(alan_id)
    if a is None:
        return sd
    hepsi = [k for k in etki.liste(sd) if isinstance(k.get("etki"), dict) and k["etki"].get("uygulama_tarihi")]
    kayitlar = [_etki_kayit(k, hepsi) for k in hepsi]
    # sıra: soru bekleyenler önce, sonra yeni uygulanan üstte (kararlı sıralama iki geçişle)
    kayitlar.sort(key=lambda r: str(r["id"]))
    kayitlar.sort(key=lambda r: str(r["uygulama_tarihi"]), reverse=True)
    kayitlar.sort(key=lambda r: not r["soru_bekliyor"])
    o = etki.dogru_karar_orani(sd)
    return {"acik": True, "alan": _alan_kisa(a),
            "ozet": {"dogru_karar_orani": o["oran"], "dogru": o["dogru"], "yanlis": o["yanlis"],
                     "belirsiz": o["belirsiz"], "kapali": o["kapatilan"]},
            "kayitlar": kayitlar, "uretim": L.simdi()}


def _kurallar_json(alan_id) -> dict:
    a, sd = _alan_sd(alan_id)
    if a is None:
        return sd
    onay.esitle(sd)
    return {"acik": True, "alan": _alan_kisa(a), **onay.kural_gorunum(sd, a["yol"]), "uretim": L.simdi()}


def _isler_json(alan_id) -> dict:
    import collections  # noqa: PLC0415
    import is_kaydi as IK  # noqa: PLC0415
    a, sd = _alan_sd(alan_id)
    if a is None:
        return sd
    usd = collections.Counter()
    is_usd = collections.Counter()   # iş toplamı: is_rapor ile aynı atama kuralı (L.satir_isi)
    kartlar = L.kartlar(sd)
    kart_is = {k["id"]: k.get("is") for k in kartlar if k.get("id") and k.get("is")}
    for r in L.maliyet_kayitlari(sd):
        if r.get("gorev") not in (None, "-"):
            usd[r["gorev"]] += r.get("maliyet_usd", 0) or 0
        is_usd[L.satir_isi(r, kart_is)] += r.get("maliyet_usd", 0) or 0
    adlar = ("yapildi", "simdi", "sirada", "planda_kart_yok", "iptal")
    kart_by = {k.get("id"): k for k in kartlar}
    isler = []
    for g in IK.is_liste(sd):
        ks = [k for k in kartlar if k.get("is") == g["id"]]
        son = max([k.get("guncelleme") or "" for k in ks] + [""]) or g.get("olusturma") or ""
        o = {"id": g["id"], "baslik": g.get("baslik", ""), "ad": IK.is_adi(g.get("baslik", "")),
             "durum": "kapandi" if g.get("durum") == "kapandi" else "acik", "klasor": g.get("klasor", ""),
             "ilerleme": {"biten": 0, "toplam": 0},
             "usd": round(is_usd.get(g["id"], 0.0), 4), "son": son,
             "kovalar": {x: [] for x in adlar}}
        try:
            s = IK.is_serit(sd, g["id"], alt=True)
            kov = {x: [] for x in adlar}
            for ad in adlar:
                for e in s[ad]:
                    if e["tur"] == "kart":
                        k = kart_by.get(e["kart"]) or {}
                        e = {**e, "basamak": k.get("basamak"), "usd": round(usd.get(e["kart"], 0.0), 4)}
                    kov[ad].append(e)
            o["ilerleme"] = s["ilerleme"]
            o["kovalar"] = kov
        except Exception as e:  # noqa: BLE001
            o["hata"] = f"{type(e).__name__}: {e}"
        isler.append(o)
    isler.sort(key=lambda i: i["son"], reverse=True)
    isler.sort(key=lambda i: i["durum"] != "acik")
    sifirlama = IK.sifirlama_zamani(sd)
    siz = [k for k in kartlar if not k.get("is") and not (sifirlama and str(k.get("olusturma") or "") < sifirlama)]
    acik = [{"kart": k["id"], "baslik": k.get("baslik", ""), "durum": k.get("durum"),
             "basamak": k.get("basamak"), "usd": round(usd.get(k["id"], 0.0), 4)}
            for k in sorted(siz, key=IK._kart_no) if k.get("durum") not in ("teslim", "iptal")]
    return {"acik": True, "alan": _alan_kisa(a), "uretim": L.simdi(), "isler": isler,
            "kartsiz": {"sayi": len(siz), "acik": acik},
            "arka_plan": _sohbet_arka_plan(a), "todo": _todo_sayac(sd)}


_KART_KIMLIK = re.compile(r"^[A-Za-z]+-\d+$")


def _teknik_hata(kod: int, metin: str) -> dict:
    return {"acik": False, "hata": metin, "kod": kod}


def _teknik_kart_ozet(sd: str, k: dict, usd: float, proje_kok: str) -> dict:
    """Kart satırı için hafif özet (git çağrısı yok): kütüphaneler çıktı dosyalarının importlarından."""
    import teknik as T  # noqa: PLC0415
    kut: list = []
    dosyalar = T._dosyalar(k, proje_kok)
    for yol in dosyalar:
        if os.path.splitext(yol)[1].lower() not in T._PY + T._JS:
            continue
        kaynak = T._oku(yol)
        if kaynak is None:
            continue
        r = T.import_coz(yol, kaynak, proje_kok)
        if not r["uyari"]:
            kut += r["stdlib"] + r["ucuncu_taraf"] + r["yerel"]
    sure = T._sureler(k)
    son = next((d.get("karar") for d in reversed(k.get("denetimler") or []) if isinstance(d, dict)), None)
    return {"id": k.get("id"), "baslik": k.get("baslik"), "sinif": k.get("sinif"), "basamak": k.get("basamak"),
            "durum": k.get("durum"), "usd": round(usd, 4),
            "sure": round(sum(sure.values()), 1) if sure else None,
            "teknik_var": isinstance(k.get("teknik"), dict) and bool(k.get("teknik")),
            "dosya_sayisi": len(dosyalar), "dosyalar": [os.path.basename(d) for d in dosyalar],
            "kutuphaneler": list(dict.fromkeys(kut)), "denetim": son}


def _teknik_json(alan_id, is_id, kart_id) -> dict:
    """Üç kip: yalnız alan → iş listesi; +is → işin kartları (artan oluşturma); +kart → 7 blok (teknik.derle).
    Hata: {"acik": False, "hata", "kod"} (kod 404/400)."""
    import collections  # noqa: PLC0415
    import is_kaydi as IK  # noqa: PLC0415
    import teknik as T  # noqa: PLC0415
    a, sd = _alan_sd(alan_id, True)
    if a is None:
        return _teknik_hata(404, "Bilinmeyen çalışma alanı ya da orkestra açık değil.")
    usd = collections.Counter()
    for r in L.maliyet_kayitlari(sd):
        if r.get("gorev") not in (None, "-"):
            usd[r["gorev"]] += r.get("maliyet_usd", 0) or 0
    if kart_id:
        if not _KART_KIMLIK.match(kart_id):
            return _teknik_hata(404, f"Kart bulunamadı: {kart_id}")
        d = T.derle(sd, kart_id)
        if d.get("hata"):
            return _teknik_hata(404, str(d["hata"]))
        return {"acik": True, "alan": _alan_kisa(a), "kart": kart_id, "uretim": L.simdi(), **d}
    kartlar = L.kartlar(sd)
    if is_id:
        kayit = IK.is_al(sd, is_id) if _KART_KIMLIK.match(is_id) else None
        if not kayit:
            return _teknik_hata(404, f"İş bulunamadı: {is_id}")
        ks = sorted((k for k in kartlar if k.get("is") == is_id), key=T._sira_anahtari)
        kok = T._proje(sd)
        return T._mask({"acik": True, "alan": _alan_kisa(a), "is": {"id": is_id, "ad": IK.is_adi(kayit.get("baslik", "")), "durum": kayit.get("durum")},
                        "kartlar": [_teknik_kart_ozet(sd, k, usd.get(k["id"], 0.0), kok) for k in ks], "uretim": L.simdi()})
    isler = []
    for g in IK.is_liste(sd):
        ks = [k for k in kartlar if k.get("is") == g["id"]]
        isler.append({"id": g["id"], "ad": IK.is_adi(g.get("baslik", "")), "durum": "kapandi" if g.get("durum") == "kapandi" else "acik",
                      "kart_sayisi": len(ks), "usd": round(sum(usd.get(k["id"], 0.0) for k in ks), 4),
                      "son": max([k.get("guncelleme") or "" for k in ks] + [""]) or g.get("olusturma") or ""})
    isler.sort(key=lambda i: i["son"], reverse=True)
    isler.sort(key=lambda i: i["durum"] != "acik")
    return T._mask({"acik": True, "alan": _alan_kisa(a), "isler": isler, "uretim": L.simdi()})


def _sayac_tum() -> dict:
    out = {}
    for a in L.calisma_alanlari():
        if a.get("orkestra"):
            sd = os.path.join(a["yol"], ".claude", "orkestra")
            onay.esitle(sd)
            out[a["id"]] = onay.sayac(sd)
    return out


def _govde_denetle(g: dict) -> str | None:
    """Gövde alan türlerini denetler; sorun varsa Türkçe hata metni, yoksa None."""
    if not isinstance(g.get("islem"), str):
        return "islem metin olmalı."
    for ad in ("id", "metin", "sonuc", "neden", "not"):
        if ad in g and not isinstance(g[ad], str):
            return f"{ad} metin olmalı."
    if g.get("secim") is not None and not isinstance(g["secim"], str):
        return "secim metin olmalı."
    return None


def _todo_json(alan_id, is_id) -> dict:
    import is_kaydi as IK  # noqa: PLC0415
    a, sd = _alan_sd(alan_id)
    if a is None:
        return sd
    isler = [{"id": g["id"], "baslik": g.get("baslik", ""), "ad": IK.is_adi(g.get("baslik", ""))}
             for g in IK.is_liste(sd, "acik")]
    secili = is_id or IK.todo_varsayilan_is(sd)
    kayit = IK.is_al(sd, secili) if secili else None
    liste = IK.todo_liste(kayit["klasor"]) if kayit else {"acik_maddeler": [], "biten_maddeler": []}
    return {"acik": True, "alan": _alan_kisa(a), "is": secili, "isler": isler, **liste}


def _kullanici_todo_json(alan_id) -> dict:
    a, sd = _alan_sd(alan_id)
    if a is None:
        return sd
    return {"acik": True, "alan": _alan_kisa(a), "maddeler": KT.liste(sd)}


def _todo_govde_denetle(g: dict) -> str | None:
    """Kullanıcı yapılacakları: yalnız ekle (metin) ve sil (id)."""
    if g.get("eylem") not in ("ekle", "sil"):
        return "eylem ekle ya da sil olmalı."
    for ad in ("metin", "id"):
        if g.get(ad) is not None and not isinstance(g[ad], str):
            return f"{ad} metin olmalı."
    return None


def _todo_islemi(sd: str, g: dict):
    """Yazım yalnız kullanıcı listesine yapılır; iş todo dosyalarına dokunulmaz. Dönüş: (kod, sonuç ya da hata)."""
    if g["eylem"] == "ekle":
        return 200, KT.ekle(sd, g.get("metin") or "")
    if not (g.get("id") or "").strip():
        return 400, "Madde kimliği boş."
    try:
        return 200, KT.sil(sd, g["id"].strip())
    except LookupError as e:
        return 404, str(e)


def _onay_islemi(sd: str, g: dict):
    islem = g.get("islem")
    if islem == "karar":
        return onay.karar_ver(sd, g.get("id"), g.get("sonuc"), g.get("secim"), g.get("not"), kim="panel")
    if islem == "kural-ekle":
        return onay.kural_ekle(sd, g.get("metin") or "", g.get("neden") or "", katman=g.get("katman") or "proje")
    if islem == "kural-tasi":
        return onay.kural_tasi(sd, g.get("id"), g.get("katman") or "")
    if islem == "kural-duzenle":
        return onay.kural_duzenle(sd, g.get("id"), g.get("metin") or "", g.get("neden"))
    if islem == "kural-kaldir":
        return onay.kural_kaldir(sd, g.get("id"), g.get("not") or "")
    if islem == "simdi-uygula":
        return onay.simdi_uygula(sd)
    raise ValueError("bilinmeyen işlem.")


def _isleyici():
    kilit = threading.Lock()
    onbellek: dict = {}
    anahtar_kilit: dict = {}

    def onbellekli(anahtar, sure, uret):
        # Genel kilit yalnız sözlük erişimini korur; hesaplama anahtar başına kilitlenir. Yavaş bir uç nokta
        # (ör. ozet.json) başka uç noktaları bekletmez, aynı anahtar ise tek kez hesaplanır.
        with kilit:
            z, v = onbellek.get(anahtar, (0.0, b""))
            if time.time() - z <= sure:
                return v
            ak = anahtar_kilit.setdefault(anahtar, threading.Lock())
        with ak:
            with kilit:
                z, v = onbellek.get(anahtar, (0.0, b""))
            if time.time() - z <= sure:
                return v
            try:
                veri = uret()
            except Exception as e:  # noqa: BLE001
                veri = {"acik": False, "hata": f"{type(e).__name__}: {e}"}
            v = json.dumps(veri, ensure_ascii=False).encode("utf-8")
            with kilit:
                onbellek[anahtar] = (time.time(), v)
            return v

    class Isleyici(http.server.BaseHTTPRequestHandler):
        timeout = 10  # yavaş istemci iş parçacığını süresiz tutmasın

        def log_message(self, *a):
            pass

        def _gonder(self, kod, tip, govde: bytes, kapat=False):
            self.send_response(kod)
            if kapat:
                self.send_header("Connection", "close")
                self.close_connection = True
            self.send_header("Content-Type", tip)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(govde)))
            self.end_headers()
            self.wfile.write(govde)
            if kapat:
                self._temiz_kapat()

        def _temiz_kapat(self):
            # Yanıtı gönder, yazma yönünü kapat, istemcinin kalan baytlarını kısa süre boşalt (Windows RST'sini önler).
            try:
                self.wfile.flush()
                self.connection.shutdown(socket.SHUT_WR)
                self.connection.settimeout(1.0)
                bitis = time.time() + 1.0
                kalan = 256 * 1024
                while kalan > 0 and time.time() < bitis:
                    parca = self.connection.recv(min(65536, kalan))
                    if not parca:
                        break
                    kalan -= len(parca)
            except (OSError, ValueError):
                pass

        def _hazirlaniyor(self, ad: str) -> bytes:
            baslik = {"maliyet.html": "Maliyet ve verim",
                     "onaylar.html": "Onaylar, etki ve kurallar",
                     "isler.html": "Dashboard", "teknik.html": "Teknik detay",
                     "yapilacaklar.html": "Yapılacaklar"}.get(ad, "Sayfa")
            return (f'<!doctype html><html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
                    f'<title>Orkestra · {baslik}</title><link rel="stylesheet" href="ortak.css"></head>'
                    f'<body><main class="hazirlaniyor"><h1>{baslik}</h1><p>Bu sayfa hazırlanıyor.</p>'
                    f'<p><a href="/">Son olaylar sayfasına dön</a></p></main></body></html>').encode("utf-8")

        def _json(self, kod, veri, kapat=False):
            return self._gonder(kod, "application/json; charset=utf-8",
                                json.dumps(veri, ensure_ascii=False).encode("utf-8"), kapat)

        def _yerel_host(self) -> bool:
            port = self.server.server_address[1]
            return (self.headers.get("Host") or "").strip().lower() in (f"127.0.0.1:{port}", f"localhost:{port}")

        def _post_onay(self, q):
            return self._post_yaz(q)

        def _post_yaz(self, q, todo=False, dosya=False):
            if self.headers.get("X-Orkestra") != "1" or not self._yerel_host():
                return self._gonder(403, "text/plain", b"yasak")
            if "application/json" not in (self.headers.get("Content-Type") or "").lower():
                return self._json(400, {"tamam": False, "hata": "Content-Type application/json olmalı."})
            try:
                uzun = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                uzun = -1
            if uzun < 0:
                return self._json(400, {"tamam": False, "hata": "Geçersiz Content-Length."})
            maks = DOSYA_POST_MAX if dosya else POST_MAX
            ad_maks = f"{maks // 1024} KB"
            if uzun > maks:
                # Gövde işlenmez. Makul boyuttaysa istemcinin gönderimi bitsin diye atılır (Windows'ta
                # sunucu okumadan kapatırsa istemci bağlantı sıfırlaması görür); dev ise bağlantı kapatılır.
                if uzun <= POST_ATIM_MAX:
                    kalan = uzun
                    while kalan > 0:
                        parca = self.rfile.read(min(65536, kalan))
                        if not parca:
                            break
                        kalan -= len(parca)
                    return self._json(413, {"tamam": False, "hata": f"Gövde çok büyük (en çok {ad_maks})."})
                return self._json(413, {"tamam": False, "hata": f"Gövde çok büyük (en çok {ad_maks})."}, kapat=True)
            try:
                g = json.loads(self.rfile.read(uzun).decode("utf-8") or "null")
                if not isinstance(g, dict):
                    raise ValueError("Gövde bir JSON nesnesi olmalı.")
            except (ValueError, UnicodeDecodeError) as e:
                return self._json(400, {"tamam": False, "hata": f"Geçersiz JSON: {e}"})
            a, sd = _alan_sd((q.get("alan") or [None])[0], kesin=True)
            if a is None:
                return self._json(400, {"tamam": False, "hata": sd["hata"]})
            if dosya:
                return self._dosya_yaz(a, sd, g)
            hata = _todo_govde_denetle(g) if todo else _govde_denetle(g)
            if hata:
                return self._json(400, {"tamam": False, "hata": hata})
            try:
                if todo:
                    kod, kayit = _todo_islemi(sd, g)
                    if kod != 200:
                        return self._json(kod, {"tamam": False, "hata": kayit})
                else:
                    kayit = _onay_islemi(sd, g)
            except (ValueError, TypeError) as e:
                return self._json(400, {"tamam": False, "hata": str(e)})
            except Exception as e:  # noqa: BLE001
                return self._json(500, {"tamam": False, "hata": f"{type(e).__name__}: {e}"})
            with kilit:
                for k in [k for k in onbellek if (isinstance(k, tuple) and k[0] in ("onay", "kural")) or k == "sayac"]:
                    onbellek.pop(k, None)
            return self._json(200, {"tamam": True, "kayit": kayit})

        def _dosya_yaz(self, a, sd, g):
            for ad in ("id", "metin", "taban"):
                if not isinstance(g.get(ad), str):
                    return self._json(400, {"tamam": False, "hata": f"{ad} metin olmalı."})
            try:
                kayit = kural_dosya.yaz(a["yol"], sd, g["id"], g["metin"], g["taban"])
            except LookupError as e:
                return self._json(404, {"tamam": False, "hata": str(e)})
            except ValueError as e:
                return self._json(409 if str(e).startswith("cakisma:") else 400, {"tamam": False, "hata": str(e)})
            except OSError as e:
                return self._json(500, {"tamam": False, "hata": f"Yazılamadı: {type(e).__name__}"})
            with kilit:
                for k in [k for k in onbellek if isinstance(k, tuple) and k[0] == "kural"]:
                    onbellek.pop(k, None)
            return self._json(200, {"tamam": True, "kayit": kayit})

        def _post_isler_sifirla(self, q):
            """Dashboard iş verisini sıfırlar (is_kaydi.sifirla). Gövde {"onay": true} zorunlu: son onay istemcide alınır."""
            if self.headers.get("X-Orkestra") != "1" or not self._yerel_host():
                return self._gonder(403, "text/plain", b"yasak")
            if "application/json" not in (self.headers.get("Content-Type") or "").lower():
                return self._json(400, {"tamam": False, "hata": "Content-Type application/json olmalı."})
            try:
                uzun = int(self.headers.get("Content-Length") or 0)
                if not 0 <= uzun <= POST_MAX:
                    raise ValueError
                g = json.loads(self.rfile.read(uzun).decode("utf-8") or "null")
            except (ValueError, UnicodeDecodeError):
                return self._json(400, {"tamam": False, "hata": "Geçersiz gövde."})
            if not isinstance(g, dict) or g.get("onay") is not True:
                return self._json(400, {"tamam": False, "hata": "Sıfırlama onayı yok."})
            a, sd = _alan_sd((q.get("alan") or [None])[0], kesin=True)
            if a is None:
                return self._json(400, {"tamam": False, "hata": sd["hata"]})
            import is_kaydi as IK  # noqa: PLC0415
            try:
                sonuc = IK.sifirla(sd)
            except Exception as e:  # noqa: BLE001
                return self._json(500, {"tamam": False, "hata": f"{type(e).__name__}: {e}"})
            with kilit:
                for k in [k for k in onbellek if isinstance(k, tuple) and k[0] in ("isler", "ozet")]:
                    onbellek.pop(k, None)
            return self._json(200, {"tamam": True, **sonuc})

        def do_POST(self):
            # Erken ret (403/400) gövdeyi okumadan döner; okunmamış baytla kapanan bağlantıyı Windows RST ile keser ve
            # istemci yanıtı alamaz (WinError 10053, yük altında aralıklı). Yanıt gittikten sonra kalan gövde boşaltılır.
            try:
                self._post_isle()
            finally:
                self._govdeyi_bosalt()

        def _govdeyi_bosalt(self):
            try:
                if int(self.headers.get("Content-Length") or 0) <= 0:
                    return
                kalan = 1024 * 1024
                while kalan > 0 and select.select([self.connection], [], [], 0.05)[0]:
                    parca = self.connection.recv(min(65536, kalan))
                    if not parca:
                        break
                    kalan -= len(parca)
            except (OSError, ValueError):
                pass

        def _post_isle(self):
            # Sohbeti aç. Özel başlık zorunlu: başka bir sitenin sayfası bu isteği CORS ön denetimi olmadan gönderemez.
            u = urllib.parse.urlparse(self.path)
            if u.path == "/onay":
                return self._post_onay(urllib.parse.parse_qs(u.query))
            if u.path == "/perspektif-calistir":
                # Gövde okunmaz; yanıt sonrası temiz kapatılır (okunmamış baytla kapanan bağlantıyı Windows RST ile keser).
                if self.headers.get("X-Orkestra") != "1" or not self._yerel_host():
                    return self._gonder(403, "text/plain", b"yasak", kapat=True)
                a, sd = _alan_sd((urllib.parse.parse_qs(u.query).get("alan") or [None])[0], kesin=True)
                if a is None:
                    return self._json(400, {"tamam": False, "hata": sd["hata"]}, kapat=True)
                try:
                    return self._json(200, niyet.perspektif_sohbeti_ac(a["yol"]), kapat=True)
                except Exception as e:  # noqa: BLE001
                    return self._json(500, {"tamam": False, "hata": f"{type(e).__name__}: {e}"}, kapat=True)
            if u.path == "/api/isler-sifirla":
                return self._post_isler_sifirla(urllib.parse.parse_qs(u.query))
            if u.path == "/api/todo":  # iş todo listeleri salt okunur
                return self._json(405, {"tamam": False, "hata": "İş todo listeleri salt okunur."})
            if u.path == "/api/kullanici-todo":
                return self._post_yaz(urllib.parse.parse_qs(u.query), todo=True)
            if u.path == "/api/kural-dosya":
                return self._post_yaz(urllib.parse.parse_qs(u.query), dosya=True)
            if u.path != "/ac" or self.headers.get("X-Orkestra") != "1":
                return self._gonder(403, "text/plain", b"yasak")
            oturum = (urllib.parse.parse_qs(u.query).get("oturum") or [""])[0]
            try:
                sonuc = niyet.ac(oturum)
            except Exception as e:  # noqa: BLE001
                sonuc = {"tamam": False, "hata": f"{type(e).__name__}: {e}"}
            return self._gonder(200, "application/json; charset=utf-8", json.dumps(sonuc, ensure_ascii=False).encode("utf-8"))

        def do_GET(self):
            u = urllib.parse.urlparse(self.path)
            q = urllib.parse.parse_qs(u.query)
            if u.path in SAYFALAR:
                ad = SAYFALAR[u.path]
                yol = os.path.join(ASSETS, ad)
                if not os.path.isfile(yol):
                    return self._gonder(200, "text/html; charset=utf-8", self._hazirlaniyor(ad))
                with open(yol, "rb") as f:
                    return self._gonder(200, "text/html; charset=utf-8", f.read())
            if u.path in STATIK:
                ad, tip = STATIK[u.path]
                yol = os.path.join(ASSETS, ad)
                if not os.path.isfile(yol):
                    return self._gonder(404, "text/plain", b"yok")
                with open(yol, "rb") as f:
                    return self._gonder(200, tip, f.read())
            if u.path in YONLENDIR:
                hedef = YONLENDIR[u.path] + (f"?{u.query}" if u.query else "")
                self.send_response(301)
                self.send_header("Location", hedef)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return None
            if u.path == "/alanlar.json":
                return self._gonder(200, "application/json; charset=utf-8",
                                    onbellekli("alanlar", 5.0, L.calisma_alanlari))
            if u.path == "/ozet.json":
                alan = (q.get("alan") or [None])[0]
                return self._gonder(200, "application/json; charset=utf-8",
                                    onbellekli(("ozet", alan), 1.0, lambda: ozet.alan_ozeti(alan)))
            if u.path == "/analitik.json":
                alan = (q.get("alan") or [None])[0]
                return self._gonder(200, "application/json; charset=utf-8",
                                    onbellekli(("analitik", alan), 10.0, lambda: analitik.alan_analitigi(alan)))
            if u.path == "/analitik-tum.json":
                return self._gonder(200, "application/json; charset=utf-8",
                                    onbellekli("analitik-tum", 20.0, analitik.tum_alanlar))
            if u.path == "/simdi.json":
                alan = (q.get("alan") or [None])[0]
                return self._gonder(200, "application/json; charset=utf-8",
                                    onbellekli(("simdi", alan), 3.0, lambda: _simdi_json(alan)))
            if u.path == "/onaylar.json":
                alan = (q.get("alan") or [None])[0]
                return self._gonder(200, "application/json; charset=utf-8",
                                    onbellekli(("onay", alan), 2.0, lambda: _onaylar_json(alan)))
            if u.path == "/kurallar.json":
                alan = (q.get("alan") or [None])[0]
                return self._gonder(200, "application/json; charset=utf-8",
                                    onbellekli(("kural", alan), 2.0, lambda: _kurallar_json(alan)))
            if u.path == "/isler.json":
                alan = (q.get("alan") or [None])[0]
                return self._gonder(200, "application/json; charset=utf-8",
                                    onbellekli(("isler", alan), 2.0, lambda: _isler_json(alan)))
            if u.path == "/teknik.json":
                alan, is_id, kart = ((q.get(x) or [None])[0] for x in ("alan", "is", "kart"))
                v = json.loads(onbellekli(("teknik", alan, is_id, kart), 30.0 if kart else 3.0, lambda: _teknik_json(alan, is_id, kart)))
                kod = 200 if v.get("acik") else (v.get("kod") or 500)
                v.pop("kod", None)
                return self._json(kod, v)
            if u.path == "/api/etki":
                alan = (q.get("alan") or [None])[0]
                return self._gonder(200, "application/json; charset=utf-8",
                                    onbellekli(("etki", alan), 2.0, lambda: _etki_json(alan)))
            if u.path == "/api/kullanici-todo":
                alan = (q.get("alan") or [None])[0]
                try:
                    return self._json(200, _kullanici_todo_json(alan))
                except Exception as e:  # noqa: BLE001
                    return self._json(500, {"tamam": False, "hata": f"{type(e).__name__}: {e}"})
            if u.path == "/api/todo":
                alan = (q.get("alan") or [None])[0]
                is_id = (q.get("is") or [None])[0]
                try:
                    return self._json(200, _todo_json(alan, is_id))
                except Exception as e:  # noqa: BLE001
                    return self._json(500, {"tamam": False, "hata": f"{type(e).__name__}: {e}"})
            if u.path in ("/api/kural-dosyalar", "/api/kural-dosya"):
                a, sd = _alan_sd((q.get("alan") or [None])[0])
                if a is None:
                    return self._json(200, sd)
                try:
                    if u.path == "/api/kural-dosyalar":
                        return self._json(200, {"acik": True, "alan": _alan_kisa(a), "dosyalar": kural_dosya.liste(a["yol"])})
                    return self._json(200, {"acik": True, **kural_dosya.oku(a["yol"], (q.get("id") or [""])[0])})
                except LookupError as e:
                    return self._json(404, {"tamam": False, "hata": str(e)})
                except ValueError as e:
                    return self._json(400, {"tamam": False, "hata": str(e)})
            if u.path == "/onay-sayac.json":
                return self._gonder(200, "application/json; charset=utf-8", onbellekli("sayac", 5.0, _sayac_tum))
            if u.path == "/saglik":
                return self._gonder(200, "text/plain", f"ok {SURUM}".encode())
            return self._gonder(404, "text/plain", b"yok")

    return Isleyici


def _bos_port(baslangic: int) -> int:
    for p in range(baslangic, baslangic + 30):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", p)) != 0:
                return p
    raise RuntimeError("boş port bulunamadı")


def _saglik(port: int) -> str | None:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/saglik", timeout=1.5) as r:
            return r.read().decode()
    except Exception:
        return None


def calistir(port: int, durum_yaz: bool = True) -> None:
    """durum_yaz=False (--test): panel.json'a dokunmaz; test sunucusu gerçek paneli ölü porta yönlendirmesin."""
    sunucu = http.server.ThreadingHTTPServer(("127.0.0.1", port), _isleyici())
    if durum_yaz:
        L.atomik_yaz(DURUM, json.dumps({"port": port, "pid": os.getpid(), "surum": SURUM, "zaman": L.simdi()}))
    sunucu.serve_forever()


def _durdur(eski: dict) -> None:
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(eski["pid"]), "/F"], capture_output=True)
        else:
            os.kill(int(eski["pid"]), 15)
    except Exception:
        pass


def baslat(port: int | None = None, alan_id: str | None = None, on_planda: bool = False) -> str:
    port = port or cfg.panel_port()
    sorgu = f"?alan={urllib.parse.quote(alan_id)}" if alan_id else ""
    try:
        with open(DURUM, encoding="utf-8") as f:
            eski = json.load(f)
        durum = _saglik(eski["port"])
        if durum == f"ok {SURUM}":
            return f"http://127.0.0.1:{eski['port']}/{sorgu}"
        if durum is not None:          # eski sürüm sunucu: kapat, yenisini aç
            _durdur(eski)
            time.sleep(0.5)
    except Exception:
        pass
    port = _bos_port(port)
    if on_planda:
        print(f"http://127.0.0.1:{port}/{sorgu}  (Ctrl+C ile durur)", flush=True)
        calistir(port)
        return ""
    subprocess.Popen([sys.executable, os.path.abspath(__file__), "_kos", str(port)], cwd=L.GENEL_DIZIN if os.path.isdir(L.GENEL_DIZIN) else None,
                     creationflags=cfg.ARKA_PLAN_BAYRAK, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, close_fds=True)
    for _ in range(30):
        if _saglik(port):
            return f"http://127.0.0.1:{port}/{sorgu}"
        time.sleep(0.2)
    return f"http://127.0.0.1:{port}/{sorgu}  (başlatıldı; yanıt vermiyorsa `orkestra panel --on-planda` ile hatayı gör)"


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "_kos":
        _test = "--test" in sys.argv[3:]
        if not _test:
            os.makedirs(L.GENEL_DIZIN, exist_ok=True)
        calistir(int(sys.argv[2]), durum_yaz=not _test)
