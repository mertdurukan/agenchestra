"""Panel: "Tüm çalışma alanları" (alan=*) birleştirmesi. ADR-0030.

Her işlev [(alan_kisa, tek_alan_yaniti)] alır (yalnız orkestra açık alanlar) ve tek alan yanıtıyla aynı biçimde
birleşik yanıt döner: kayıtlara `alan: {id, ad}` eklenir, sayaçlar toplanır. Toplanamayan veri (oran, medyan, hedef panosu,
perspektif durumu) toplanmaz; yanıtta `birlesmeyen` altında adıyla anılır, arayüz "tek çalışma alanı seçin" der.
Saf işlevler: dosya, ağ ve panel durumu yok; panel.py tek alan işlevlerini çağırıp sonucu buraya verir.
"""
from __future__ import annotations

import ork_lib as L

TUM_AD = "Tüm çalışma alanları"
ETIKET = {"id": "*", "ad": TUM_AD}
_MAKS = frozenset({"gun", "gecen_gun", "ay_gun", "veri_gun"})   # toplanınca anlamını yitiren gün sayaçları: en büyüğü alınır
ONAY_AZAMI = 200


def alan_etiketi(a: dict) -> dict:
    return {"id": a["id"], "ad": a["ad"]}


def _etiketle(kayit, a: dict):
    return {**kayit, "alan": alan_etiketi(a)} if isinstance(kayit, dict) else kayit


def _hepsi(sonuclar, anahtar: str) -> list:
    """Her alanın `anahtar` listesi, kayıtlar alan etiketli, art arda."""
    out = []
    for a, v in sonuclar:
        out += [_etiketle(k, a) for k in (v.get(anahtar) or [])]
    return out


def _topla(a, b):
    """Sayılar toplanır, mantıksallar VEYA'lanır, sözlükler anahtar anahtar birleşir, listeler art arda eklenir, metin ilk değerdir."""
    if a is None:
        return b
    if b is None:
        return a
    if isinstance(a, bool) or isinstance(b, bool):
        return bool(a) or bool(b)
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a + b
    if isinstance(a, dict) and isinstance(b, dict):
        out = dict(a)
        for k, v in b.items():
            if k not in out:
                out[k] = v
            elif k in _MAKS and isinstance(v, (int, float)) and isinstance(out[k], (int, float)):
                out[k] = max(out[k], v)
            else:
                out[k] = _topla(out[k], v)
        return out
    if isinstance(a, list) and isinstance(b, list):
        return a + b
    return a


def _yuvarla(v):
    if isinstance(v, float):
        return round(v, 4)
    if isinstance(v, dict):
        return {k: _yuvarla(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_yuvarla(x) for x in v]
    return v


def _topla_hepsi(degerler) -> object:
    out = None
    for d in degerler:
        out = _topla(out, d)
    return _yuvarla(out)


def _zarf(sonuclar, atlanan: list, **eklenen) -> dict:
    """Ortak üst alanlar; hiç alan yoksa acik=False."""
    alanlar = [alan_etiketi(a) for a, _ in sonuclar]
    uretim = max((str(v.get("uretim") or "") for _, v in sonuclar), default="") or L.simdi()
    z = {"acik": bool(sonuclar), "alan": ETIKET, "alanlar": alanlar, "birlesik": True, "atlanan": atlanan, "uretim": uretim, **eklenen}
    if not sonuclar:
        z["hata"] = "Orkestra açık çalışma alanı yok."
    return z


def ayir(ham) -> tuple[list, list]:
    """[(alan, yanit | istisna)] → (geçerli [(alan, yanit)], atlanan [{alan, hata}]). Yanıtı `acik: False` olan ya da hata veren alan atlanır."""
    ok, atlanan = [], []
    for a, v in ham:
        if isinstance(v, BaseException):
            atlanan.append({"alan": alan_etiketi(a), "hata": f"{type(v).__name__}: {v}"})
        elif not isinstance(v, dict) or v.get("acik") is False:
            atlanan.append({"alan": alan_etiketi(a), "hata": (v or {}).get("hata", "yanıt yok") if isinstance(v, dict) else "yanıt yok"})
        else:
            ok.append((a, v))
    return ok, atlanan


# ------------------------------------------------------------------ onaylar, kurallar, yapılacaklar

def onaylar(ok, atlanan) -> dict:
    kayitlar = _hepsi(ok, "kayitlar")
    bekleyen = [k for k in kayitlar if k.get("durum") == "bekliyor"]
    diger = [k for k in kayitlar if k.get("durum") != "bekliyor"]
    return _zarf(ok, atlanan,
                 sayac=_topla_hepsi(v.get("sayac") for _, v in ok) or {},
                 kayitlar=bekleyen + diger[:max(0, ONAY_AZAMI - len(bekleyen))],
                 perspektif={"rapor": None, "durum": None}, uygulama=None,   # alan başına koşu durumu toplanmaz
                 arka_plan=_hepsi(ok, "arka_plan"),
                 birlesmeyen=["perspektif", "uygulama"])


def _tekil_kural(liste: list) -> list:
    """Eklenti katmanı kuralı her alanda aynıdır: (katman, id, metin) ile bir kez; ortak=True, alan etiketi yok. Proje kuralı alan etiketli kalır."""
    gorulen, out = set(), []
    for k in liste:
        if k.get("katman") == "plugin":
            anahtar = ("plugin", k.get("id"), k.get("metin"), k.get("durum"))
            if anahtar in gorulen:
                continue
            gorulen.add(anahtar)
            k = {x: y for x, y in k.items() if x != "alan"}
            k["ortak"] = True
        out.append(k)
    return out


def kurallar(ok, atlanan) -> dict:
    kaynaklar, gorulen = [], set()
    for a, v in ok:
        for s in v.get("kaynaklar") or []:
            anahtar = (s.get("yol"), s.get("baslik"))
            if anahtar not in gorulen:
                gorulen.add(anahtar)
                kaynaklar.append(_etiketle(s, a))
    return _zarf(ok, atlanan, etkin=_tekil_kural(_hepsi(ok, "etkin")), oneriler=_tekil_kural(_hepsi(ok, "oneriler")),
                 gecmis=_tekil_kural(_hepsi(ok, "gecmis")), kaynaklar=kaynaklar)


def kullanici_todo(ok, atlanan) -> dict:
    maddeler = _hepsi(ok, "maddeler")
    maddeler.sort(key=lambda m: str(m.get("zaman") or ""), reverse=True)
    return _zarf(ok, atlanan, maddeler=maddeler)


# ------------------------------------------------------------------ işler, teknik

def isler(ok, atlanan) -> dict:
    liste = _hepsi(ok, "isler")
    liste.sort(key=lambda i: str(i.get("son") or ""), reverse=True)
    liste.sort(key=lambda i: i.get("durum") != "acik")
    kartsiz = {"sayi": sum(int((v.get("kartsiz") or {}).get("sayi") or 0) for _, v in ok),
               "acik": [_etiketle(k, a) for a, v in ok for k in (v.get("kartsiz") or {}).get("acik", [])]}
    return _zarf(ok, atlanan, isler=liste, kartsiz=kartsiz, arka_plan=_hepsi(ok, "arka_plan"))


def teknik_liste(ok, atlanan) -> dict:
    liste = _hepsi(ok, "isler")
    liste.sort(key=lambda i: str(i.get("son") or ""), reverse=True)
    liste.sort(key=lambda i: i.get("durum") != "acik")
    return _zarf(ok, atlanan, isler=liste)


# ------------------------------------------------------------------ özet (sohbet, kart, maliyet)

def _ajan_surec(listeler, sinir: int) -> list:
    """(ajan, süreç) başına koşu, USD ve token toplamı; en pahalı `sinir` satır (tek alandaki sınırla aynı)."""
    toplam = {}
    for liste in listeler:
        for r in liste or []:
            k = (r.get("ajan"), r.get("surec"))
            toplam[k] = _topla(toplam.get(k), {x: y for x, y in r.items() if x not in ("ajan", "surec")})
    out = [{"ajan": k[0], "surec": k[1], **r} for k, r in toplam.items()]
    return _yuvarla(sorted(out, key=lambda r: -(r.get("usd") or 0))[:sinir])


def _maliyet(ok) -> dict:
    """Alanların maliyet bölümü: sayılar toplanır; (ajan, süreç) listeleri ve oturum listesi ayrıca birleşir (düz ekleme satırı tekrarlar)."""
    def sade(m):
        m = {k: x for k, x in m.items() if k not in ("ajan_surec", "oturumlar")}
        if isinstance(m.get("pencere"), dict):
            m["pencere"] = {w: {k: x for k, x in p.items() if k != "ajan_surec"} for w, p in m["pencere"].items()}
        return m
    ms = [v.get("maliyet") or {} for _, v in ok]
    maliyet = _topla_hepsi(sade(m) for m in ms) or {}
    maliyet["ajan_surec"] = _ajan_surec((m.get("ajan_surec") for m in ms), 20)
    maliyet["oturumlar"] = _hepsi([(a, v.get("maliyet") or {}) for a, v in ok], "oturumlar")
    for w in list(maliyet.get("pencere") or {}):
        ps = [((m.get("pencere") or {}).get(w) or {}) for m in ms]
        if any("ajan_surec" in p for p in ps):
            maliyet["pencere"][w]["ajan_surec"] = _ajan_surec((p.get("ajan_surec") for p in ps), 15)
    return maliyet


def ozet(ok, atlanan) -> dict:
    maliyet = _maliyet(ok)
    defter = _hepsi(ok, "defter")
    defter.sort(key=lambda r: str(r.get("zaman") or ""), reverse=True)
    sohbetler = _hepsi(ok, "sohbetler")
    sohbetler.sort(key=lambda r: str(r.get("son") or ""), reverse=True)
    dokum = {"gun": max((str((v.get("sohbet_dokum") or {}).get("gun") or "") for _, v in ok), default=""),
             "sohbetler": _hepsi([(a, v.get("sohbet_dokum") or {}) for a, v in ok], "sohbetler")}
    return _zarf(ok, atlanan,
                 orkestra=True, isler=_hepsi(ok, "isler"), kartlar=_hepsi(ok, "kartlar"),
                 sayac=_topla_hepsi(v.get("sayac") for _, v in ok) or {},
                 maliyet=maliyet, sohbetler=sohbetler, sohbet_dokum=dokum, asili_ajanlar=_hepsi(ok, "asili_ajanlar"),
                 defter=defter[:20], perspektif=None, onaylar=_topla_hepsi(v.get("onaylar") for _, v in ok),
                 birlesmeyen=["perspektif"])


# ------------------------------------------------------------------ analitik (maliyet, koşular)

def _donem_birlestir(listeler) -> list:
    """Aynı `donem` (gün, saat, hafta, ay) kayıtları toplanır; zaman sırası korunur."""
    toplam = {}
    for liste in listeler:
        for r in liste or []:
            d = r.get("donem")
            toplam[d] = _topla(toplam[d], r) if d in toplam else dict(r)
    return [_yuvarla(toplam[d]) for d in sorted(toplam, key=str)]


def _trend(ok) -> dict:
    ts = [v.get("trend") or {} for _, v in ok]
    out = {ad: _donem_birlestir(t.get(ad) for t in ts) for ad in ("gunluk", "saatlik", "haftalik", "aylik")}
    ay = _topla_hepsi(t.get("ay_sonu") for t in ts) or {}
    # gün sayaçları ve ay adı alanlar arasında aynıdır; toplama yalnız tutarlar içindir
    ilk = [t.get("ay_sonu") for t in ts if t.get("ay_sonu")]
    if ilk:
        ay["ay"] = ilk[0].get("ay")
    out["ay_sonu"] = ay
    out["ilk_kayit"] = min((str(t.get("ilk_kayit")) for t in ts if t.get("ilk_kayit")), default=None)
    return out


def _en_pahali(ok, pencere: str, anahtar: str) -> list:
    """[kart_id, tutar] satırlarına alan kimliği eklenir ([id, tutar, alan_id]); kimlikler alanlar arasında çakışabilir."""
    satirlar, sinir = [], 0
    for a, v in ok:
        l = ((v.get("pencere") or {}).get(pencere) or {}).get(anahtar) or []
        sinir = max(sinir, len(l))
        satirlar += [[s[0], s[1], a["id"]] for s in l if isinstance(s, (list, tuple)) and len(s) >= 2]
    satirlar.sort(key=lambda s: -(s[1] or 0))
    return satirlar[:sinir or 10]


def _pencere(ok, kartlar: list) -> dict:
    import analitik  # noqa: PLC0415
    out = {}
    for w in L.PENCERELER:
        pw = [((v.get("pencere") or {}).get(w) or {}) for _, v in ok]
        birim_ilk = next((p.get("birim") for p in pw if p.get("birim")), {}) or {}
        out[w] = {"kart_sayisi": sum(int(p.get("kart_sayisi") or 0) for p in pw),
                  # kart başı ortalama ve medyan alanlar arasında toplanmaz: boş bırakılır (arayüz "–" gösterir)
                  "birim": {k: (sum(int((p.get("birim") or {}).get("teslim_kart") or 0) for p in pw) if k == "teslim_kart" else None) for k in birim_ilk},
                  "en_pahali": _en_pahali(ok, w, "en_pahali"), "en_pahali_token": _en_pahali(ok, w, "en_pahali_token"),
                  "basamak": [],   # ilk geçiş ve ret oranı satırları toplanamaz
                  "akis_ozet": analitik._akis_ozet([k for k in kartlar if w in (k.get("penceresi") or [])])}
    return out


def _onbellek(ok) -> dict:
    os_ = [v.get("onbellek") for _, v in ok if v.get("onbellek")]
    if not os_:
        return {}
    out = _topla_hepsi({x: y for x, y in o.items() if x not in ("model_olaylari", "bosluk_olaylari", "gun")} for o in os_)
    out["gun"] = max(int(o.get("gun") or 0) for o in os_)
    for ad in ("model_olaylari", "bosluk_olaylari"):
        l = _hepsi([(a, v.get("onbellek") or {}) for a, v in ok], ad)
        l.sort(key=lambda e: -(e.get("usd") or 0))
        out[ad] = l[:max(len((o.get(ad) or [])) for o in os_) or 8]
    return out


def analitik_birlesik(ok, atlanan) -> dict:
    akis_kartlar = _hepsi([(a, v.get("akis") or {}) for a, v in ok], "kartlar")
    akis = {"kartlar": akis_kartlar, "ozet": None, "kosular": [],   # koşu zaman çizelgesi tek alanda
            "gunler": sorted({g for _, v in ok for g in ((v.get("akis") or {}).get("gunler") or [])})}
    import analitik  # noqa: PLC0415
    akis["ozet"] = analitik._akis_ozet(akis_kartlar)
    return _zarf(ok, atlanan, surum=1, trend=_trend(ok), pencere=_pencere(ok, akis_kartlar), akis=akis,
                 onbellek=_onbellek(ok), hedef_panosu=None,
                 birlesmeyen=["hedef_panosu", "basamak", "birim", "skill", "saglik", "ders", "planlayici", "baglam", "kota", "tasarruf", "is_basina"])
