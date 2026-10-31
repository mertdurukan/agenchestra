"""Olay kaydı (I-286, ADR-0109): defterlerdeki olayları ana > alt kategori, bağlam ve sonuçla OKUMA ANINDA birleştirir.

Hiçbir deftere yazmaz. Kaynaklar: gunluk.jsonl (kural_ihlal, kapi_ret, onay-ekran, istek) ve hata.jsonl (kaynak=davranis).
Kategori eşlemesi `ayarlar/olay_esleme.json`, eşikler ve pencere `ayarlar/olay_kaydi.json` dosyasındadır
(durum klasöründeki aynı adlı dosya anahtar bazında ezer). Sonuç yazılmaz, türetilir:
aynı imza pencere (varsayılan 7 gün) içinde yeniden gelirse `tekrarladi`; gelmeden pencere dolarsa `duzeldi`; dolmadıysa `acik`.
Olay: {zaman, tur, ana_kategori, alt_kategori, baglam, imza, sonuc}.
"""
from __future__ import annotations

import datetime
import json
import os

import ork_lib as L
import hata_kayit as HK

SONUCLAR = ("acik", "duzeldi", "tekrarladi")
_KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _json(yol: str) -> dict:
    try:
        with open(yol, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def ayar_yukle(klasor: str | None = None, sd: str | None = None) -> tuple[dict, dict]:
    """(kategoriler, ayar); durum klasöründeki aynı adlı dosya anahtar bazında ezer."""
    sonuc = []
    sd = sd or (L.durum_dizini(klasor) if klasor else None)
    for ad in ("olay_esleme.json", "olay_kaydi.json"):
        d = _json(os.path.join(_KOK, "ayarlar", ad))
        if sd:
            d.update(_json(os.path.join(sd, ad)))
        sonuc.append(d)
    return sonuc[0], sonuc[1]


def an(z):
    try:
        t = datetime.datetime.fromisoformat(str(z or "").replace("Z", "+00:00"))
        return t if t.tzinfo else t.astimezone()
    except ValueError:
        return None


def satirlar(yol: str) -> list[dict]:
    out = []
    try:
        with open(yol, encoding="utf-8", errors="replace") as f:
            for s in f:
                try:
                    o = json.loads(s)
                except ValueError:
                    continue
                if isinstance(o, dict):
                    out.append(o)
    except OSError:
        pass
    return out


def _olay(zaman, esleme: dict, kat: dict, imza: str, baglam: str, kesit: int) -> dict:
    v = kat.get("varsayilan") or {}
    return {"zaman": str(zaman or ""), "tur": esleme.get("tur", "kapi_ret"),
            "ana_kategori": esleme.get("ana", v.get("ana", "diger")),
            "alt_kategori": esleme.get("alt", v.get("alt", "siniflanmamis")),
            "baglam": str(baglam or "")[:kesit], "imza": imza, "sonuc": "acik"}


def olaylari_cikar(gunluk: list[dict], hata: list[dict], kat: dict, ayar: dict, duzeltmeler: list[dict] | None = None) -> list[dict]:
    """Dört türü tek biçime çevirir; sonuç henüz `acik`. `duzeltmeler`: olay_duzeltme.bul çıktısı (P3), boş olabilir."""
    kesit = int(ayar.get("kesit_uzunluk", 120))
    v = kat.get("varsayilan") or {}
    out = []
    for g in gunluk:
        t = g.get("tur")
        if t == "kural_ihlal":
            kural = str(g.get("kural") or "")
            e = (kat.get("kural_ihlal") or {}).get(kural) or {"tur": "yanlis_oneri", "ana": v.get("ana"), "alt": v.get("alt")}
            out.append(_olay(g.get("zaman"), e, kat, "kural:" + kural, g.get("dosya") or kural, kesit))
        elif t == "kapi_ret":
            e = dict(kat.get("kapi_ret") or {})
            kapi = str(g.get("kapi") or "")
            if kapi:
                e["alt"] = kapi
            out.append(_olay(g.get("zaman"), e, kat, "kapi:" + kapi, HK.imza("kapi_ret", g.get("neden")), kesit))
        elif t == "onay-ekran":
            out.append(_olay(g.get("zaman"), kat.get("onay_ekran") or {}, kat, "karar:" + str(g.get("bicim") or ""),
                             g.get("bicim"), kesit))
    for h in hata:
        if h.get("kaynak") != "davranis":
            continue
        e = (kat.get("davranis_sinif") or {}).get(str(h.get("tur") or ""))
        out.append(_olay(h.get("zaman"), e or {}, kat, str(h.get("imza") or h.get("tur") or ""), h.get("imza") or h.get("ileti"), kesit))
    for d in duzeltmeler or []:
        out.append(_olay(d.get("zaman"), kat.get("kullanici_duzeltme") or {}, kat, str(d.get("imza") or ""), d.get("baglam"), kesit))
    return out


def sonuc_turet(olaylar: list[dict], simdi: datetime.datetime, pencere_gun: int = 7) -> list[dict]:
    """Her olaya sonuç yazar (yerinde): sonraki aynı imza pencere içinde (<= pencere) ise tekrarladi, yoksa pencere dolmuşsa duzeldi."""
    w = datetime.timedelta(days=pencere_gun)
    zamanli = [(an(o["zaman"]), o) for o in olaylar]
    gruplar: dict[str, list[tuple]] = {}
    for t, o in zamanli:
        if t is not None:
            gruplar.setdefault(o["imza"], []).append((t, o))
    for liste in gruplar.values():
        liste.sort(key=lambda x: x[0])
        for i, (t, o) in enumerate(liste):
            sonraki = liste[i + 1][0] if i + 1 < len(liste) else None
            if sonraki is not None and sonraki - t <= w:
                o["sonuc"] = "tekrarladi"
            elif simdi - t > w:
                o["sonuc"] = "duzeldi"
            else:
                o["sonuc"] = "acik"
    return olaylar


def oku(klasor: str | None = None, simdi: datetime.datetime | None = None) -> list[dict]:
    """Proje klasöründen durum klasörünü bulup `oku_sd` çağırır."""
    sd = L.durum_dizini(klasor)
    return oku_sd(sd, simdi) if sd else []


def oku_sd(sd: str, simdi: datetime.datetime | None = None) -> list[dict]:
    """Defterlerden olayları okur ve sonucunu türetir. P3 modülü yoksa kullanıcı düzeltmesi boş kalır."""
    kat, ayar = ayar_yukle(sd=sd)
    gunluk = satirlar(os.path.join(sd, "gunluk.jsonl"))
    hata = satirlar(os.path.join(sd, "hata.jsonl"))
    try:
        import olay_duzeltme
        duz = olay_duzeltme.bul(gunluk, ayar)
    except ImportError:
        duz = []
    olaylar = olaylari_cikar(gunluk, hata, kat, ayar, duz)
    simdi = simdi or datetime.datetime.now().astimezone()
    return sonuc_turet(olaylar, simdi, int(ayar.get("pencere_gun", 7)))


def tur_adetleri(olaylar: list[dict]) -> dict:
    d: dict[str, int] = {}
    for o in olaylar:
        d[o["tur"]] = d.get(o["tur"], 0) + 1
    return d
