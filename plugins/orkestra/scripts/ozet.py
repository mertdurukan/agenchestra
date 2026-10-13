"""Orkestra anlık görüntüsü: arayüzlerin (Claude içi panel, HTML panel) tek veri kaynağı.

`olustur(sd, proje)` durumu tek sözlükte toplar; `yaz(sd, proje)` onu `<durum>/ozet.json`a atomik yazar.
Hook'lar ve durumu değiştiren CLI komutları her değişiklikte `yaz` çağırır; arayüzler yalnız dosyayı okur
(süreç başlatmaz). Oturuma özgü değerler `maliyet.oturumlar[<oturum id>]` altındadır; arayüz kendi oturumunu seçer.
"""
from __future__ import annotations

import collections
import datetime
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ork_lib as L  # noqa: E402
import analitik as A  # noqa: E402  (bugün hesabı ve ajan adı eşlemesi tek yerde)

SURUM = 2
ASILI_AJAN_DK = 30
ASILI_AJAN_TEMIZLE_SAAT = 24


def _yuvarla(d: dict, n: int = 4) -> dict:
    return {k: round(v, n) for k, v in d.items()}


_MD_BAGLANTI = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_MD_ISARET = re.compile(r"(\*{1,3}|_{2,3}|`+)")
_KART_KIMLIK = re.compile(r"\b[A-Z]{1,3}-\d+\b")


def temiz_metin(s, sinir: int = 160) -> str:
    """Markdown işaretlerini soyar (**, __, `, [a](b) -> a, satır başı #/-/>), boşlukları sadeleştirir, sınırlar."""
    s = _MD_BAGLANTI.sub(r"\1", str(s or ""))
    s = re.sub(r"(?m)^\s*(#{1,6}\s+|[-*+]\s+|>\s*)", "", s)
    s = _MD_ISARET.sub("", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= sinir else s[:sinir - 1].rstrip() + "…"


def _olay_mi(metin: str, gorev=None) -> bool:
    """Metin yalnız bir durum işareti mi: kayıt bir karta bağlı (gorev kart kimliği) ve metin en çok 4 kelime,
    kart kimliği / 'teslim' / 'denetim' içeriyor. Karta bağlı olmayan (gorev '-') kayıtlar olay sayılmaz."""
    if not isinstance(gorev, str) or not _KART_KIMLIK.fullmatch(gorev):
        return False
    if not metin or len(metin.split()) > 4:
        return False
    return bool(_KART_KIMLIK.search(metin) or re.search(r"(?i)teslim|denetim", metin))


_DEFTER_METIN_ALANLARI = ("sonuc", "yaptim", "not", "sonraki", "ozet", "aciklama", "mesaj", "metin")
_DEFTER_METIN_DISI = {"zaman", "gorev", "surec", "ajan", "agent_id", "oturum", "model", "kaynak", "dokunulan", "token"}


GERI_DOLDUR_SN = 2


def _geri_doldur(sd: str, satirlar: list, kart_oturum: dict) -> list:
    """Her defter satırı için oturum kimliği (yalnız okurken türetilir, dosya değişmez).

    Sıra: satırın kendi alanı, kart oturumu, maliyet.jsonl'de aynı ajan ve ±GERI_DOLDUR_SN sn içinde en yakın kaydın oturumu
    (en yakında farklı oturumlar eşitse None), yoksa None.
    """
    maliyet = None
    out = []
    for r in satirlar:
        o = r.get("oturum") or kart_oturum.get(r.get("gorev", "-"))
        if not o:
            if maliyet is None:
                maliyet = [(m, A._zaman(m.get("zaman"))) for m in L.jsonl_oku(os.path.join(sd, "maliyet.jsonl")) if m.get("oturum")]
            z = A._zaman(r.get("zaman"))
            if z is not None:
                # pencere içinde |dt| en küçük kayıt; en küçük mesafede farklı oturumlar eşitse belirsiz → None
                adaylar = [(abs((mz - z).total_seconds()), m["oturum"]) for m, mz in maliyet
                           if mz is not None and m.get("ajan") == r.get("ajan")]
                adaylar = [x for x in adaylar if x[0] <= GERI_DOLDUR_SN]
                if adaylar:
                    en_az = min(d for d, _ in adaylar)
                    ids = {oid for d, oid in adaylar if d == en_az}
                    o = ids.pop() if len(ids) == 1 else None
        out.append(o or None)
    return out


def defter_metni(r: dict) -> str:
    """Defter kaydının gösterilecek metni: sonuc/yaptim boşsa not/sonraki ve kayıttaki diğer metin alanlarına düşer."""
    adaylar = [r.get(k) for k in _DEFTER_METIN_ALANLARI]
    adaylar += [v for k, v in r.items() if k not in _DEFTER_METIN_ALANLARI and k not in _DEFTER_METIN_DISI]
    for v in adaylar:
        if isinstance(v, str):
            t = temiz_metin(v)
            if t:
                return t
    return ""


def kisalt_baslik(s, sinir: int = 80) -> str:
    """Kart başlığını sınırlar; kesilirse sonuna '…' ekler (toplam uzunluk sinir)."""
    s = str(s or "")
    return s if len(s) <= sinir else s[:sinir - 1].rstrip() + "…"


def asili_ajanlar(sd: str, simdi=None) -> list:
    """`oturumlar/acik_ajan_*.json` kayıtlarından başlangıcı ASILI_AJAN_DK'dan eski olanları döner;
    ASILI_AJAN_TEMIZLE_SAAT'ten eski kayıtları siler (bitişi hiç gelmeyen ajanların kalıntısı)."""
    simdi = simdi or datetime.datetime.now().astimezone()
    out = []
    try:
        adlar = sorted(os.listdir(os.path.join(sd, "oturumlar")))
    except OSError:
        return out
    for ad in adlar:
        if not (ad.startswith("acik_ajan_") and ad.endswith(".json")):
            continue
        yol = os.path.join(sd, "oturumlar", ad)
        try:
            with open(yol, encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            continue
        z = A._zaman(d.get("zaman"))
        if not z:
            continue
        dk = (simdi - z).total_seconds() / 60
        if dk > ASILI_AJAN_TEMIZLE_SAAT * 60:
            try:
                os.remove(yol)
            except OSError:
                pass
        elif dk >= ASILI_AJAN_DK:
            out.append({"agent_id": d.get("agent_id"), "ajan": d.get("ajan"), "gorev": d.get("gorev", "-"),
                        "surec": d.get("surec"), "oturum": d.get("oturum"), "dakika": int(dk)})
    return out


def olustur(sd: str, proje: str) -> dict:
    kayitlar = L.maliyet_kayitlari(sd)
    bugun = datetime.date.today()  # yerel gün sınırı; analitik.py ile aynı (UTC 'Z' damgaları yerel güne çevrilir)

    # --- kartlar
    kart_usd = collections.Counter()
    for r in kayitlar:
        if r.get("gorev") not in (None, "-"):
            kart_usd[r["gorev"]] += r.get("maliyet_usd", 0) or 0
    ks = []
    for k in L.kartlar(sd):
        d = L.kart_durumu_hesapla(k)
        son = (k.get("denetimler") or [{}])[-1]
        ks.append({"id": k["id"], "baslik": kisalt_baslik(k["baslik"]), "durum": d, "basamak": k["basamak"],
                   "oturum": k.get("oturum"), "isci": len(k.get("isciler", [])), "denetim": son.get("karar", "-"),
                   "bagimli": k.get("bagimliliklar", []), "usd": round(kart_usd.get(k["id"], 0.0), 4),
                   "guncelleme": k.get("guncelleme")})
    acik = [k for k in ks if k["durum"] in L.ACIK_DURUMLAR or k["durum"] in ("beklemede", "planlandi")]
    kapali = sorted([k for k in ks if k not in acik], key=lambda x: x.get("guncelleme") or "", reverse=True)[:10]
    kartlar = sorted(acik, key=lambda x: x["id"]) + kapali

    # --- maliyet
    bugunku = [r for r in kayitlar if (z := A._zaman(r.get("zaman"))) and z.date() == bugun]
    surec, model = collections.Counter(), collections.Counter()
    ajan_surec: dict = {}
    for r in bugunku:
        usd = r.get("maliyet_usd", 0) or 0
        surec[r.get("surec", "-")] += usd
        model[(r.get("model") or "-").replace("claude-", "")] += usd
        a = ajan_surec.setdefault((r.get("ajan", "-"), r.get("surec", "-")), {"kosu": 0, "usd": 0.0, "cikis": 0, "giris": 0})
        a["kosu"] += 1
        a["usd"] += usd
        a["cikis"] += r.get("cikis", 0) or 0
        a["giris"] += (r.get("giris", 0) or 0) + (r.get("onbellek_okuma", 0) or 0) + (r.get("onbellek_yazma", 0) or 0)

    sohbet_listesi = L.sohbetler(sd, proje, limit=15, tahmin=True)
    oturum_ids = {s["oturum"] for s in sohbet_listesi}
    oturumlar: dict = {}
    for r in kayitlar:
        oid = r.get("oturum")
        if oid not in oturum_ids:
            continue
        o = oturumlar.setdefault(oid, {"usd": 0.0, "surec": collections.Counter(), "model": collections.Counter(), "ajan_surec": {}})
        usd = r.get("maliyet_usd", 0) or 0
        o["usd"] += usd
        o["surec"][r.get("surec", "-")] += usd
        o["model"][(r.get("model") or "-").replace("claude-", "")] += usd
        a = o["ajan_surec"].setdefault((r.get("ajan", "-"), r.get("surec", "-")), {"kosu": 0, "usd": 0.0, "cikis": 0, "giris": 0})
        a["kosu"] += 1
        a["usd"] += usd
        a["cikis"] += r.get("cikis", 0) or 0
        a["giris"] += (r.get("giris", 0) or 0) + (r.get("onbellek_okuma", 0) or 0) + (r.get("onbellek_yazma", 0) or 0)
    for o in oturumlar.values():
        o["usd"] = round(o["usd"], 4)
        o["surec"] = _yuvarla(dict(o["surec"].most_common(8)))
        o["model"] = _yuvarla(dict(o["model"].most_common(6)))
        o["ajan_surec"] = sorted([{"ajan": a, "surec": su, **{k: (round(v, 4) if k == "usd" else v) for k, v in d.items()}}
                                  for (a, su), d in o["ajan_surec"].items()], key=lambda x: -x["usd"])[:15]

    sohbetler = []
    for s in sohbet_listesi:
        if s["motor_usd"]:
            usd, kaynak = s["motor_usd"], "motor"
        elif s["defter_usd"]:
            usd, kaynak = s["defter_usd"], "defter"
        else:
            usd, kaynak = s.get("tahmin_usd") or 0.0, "tahmin"
        if not usd:
            continue
        sohbetler.append({"oturum": s["oturum"], "baslik": s["baslik"], "usd": round(usd, 4),
                          "kaynak": kaynak,
                          "motor_usd": s["motor_usd"], "defter_usd": s["defter_usd"], "son": s["son"],
                          "modeller": s["modeller"]})

    # --- defter ve rüya
    kart_oturum = {k["id"]: k.get("oturum") for k in ks}
    defter = []
    kayitlar_d = L.defter_kayitlari(sd)
    bf = _geri_doldur(sd, kayitlar_d[-20:], kart_oturum)
    for r, bo in zip(kayitlar_d[-20:], bf):
        metin = defter_metni(r)
        gorev = r.get("gorev", "-")
        defter.append({"zaman": r.get("zaman"), "gorev": gorev, "surec": r.get("surec", "-"),
                       "ajan": r.get("ajan", "-"), "oturum": bo,
                       "metin": metin, "olay": _olay_mi(metin, gorev)})
    import ruya
    rd = ruya.durum(sd)
    try:
        import onay
        onaylar = onay.sayac(sd)
    except Exception:
        onaylar = None

    return {
        "surum": SURUM, "acik": True, "orkestra": True, "uretim": L.simdi(), "proje": os.path.basename(os.path.abspath(proje)),
        "kartlar": kartlar,
        "sayac": dict(collections.Counter(k["durum"] for k in acik)),
        "maliyet": {
            "bugun": round(A.bugun_usd(kayitlar, bugun), 4),
            "toplam": round(sum(r.get("maliyet_usd", 0) or 0 for r in kayitlar), 4),
            "surec": _yuvarla(dict(surec.most_common(10))),
            "model": _yuvarla(dict(model.most_common(6))),
            "ajan_surec": sorted([{"ajan": a, "surec": s, **{k: (round(v, 4) if k == "usd" else v) for k, v in d.items()}}
                                  for (a, s), d in ajan_surec.items()], key=lambda x: -x["usd"])[:20],
            "oturumlar": oturumlar,
        },
        "sohbetler": sohbetler,
        "asili_ajanlar": asili_ajanlar(sd),
        "defter": defter,
        "ruya": {"zamani_geldi": rd["zamani_geldi"], "rapor": bool(rd["okunmamis_rapor"]), "calisiyor": bool(rd["calisiyor"]),
                 "son_ruya": rd["son_ruya"]},
        "onaylar": onaylar,
    }


def yaz(sd: str, proje: str) -> dict | None:
    """Anlık görüntüyü yazar; hata arayüzü bozmasın diye ozet_hata.txt'ye düşer, istisna fırlatmaz."""
    try:
        o = olustur(sd, proje)
        L.atomik_yaz(os.path.join(sd, "ozet.json"), json.dumps(o, ensure_ascii=False))
        return o
    except Exception as e:  # noqa: BLE001
        try:
            L.atomik_yaz(os.path.join(sd, "ozet_hata.txt"), f"{L.simdi()} {type(e).__name__}: {e}\n")
        except Exception:
            pass
        return None


# ---------------------------------------------------------------- çoklu çalışma alanı

def _hafif(alan: dict) -> dict:
    """Orkestra kurulu olmayan çalışma alanı: yalnız sohbet maliyetleri (Claude'un hesabı ya da transkript tahmini)."""
    sohbet_listesi = L.sohbetler(None, alan["yol"], limit=15, tahmin=True,
                                 oturum_dizini=os.path.join(os.path.expanduser("~"), ".claude", "projects", alan["id"]))
    sohbetler, model, oturumlar = [], collections.Counter(), {}
    bugun = datetime.date.today()
    bugun_usd = 0.0
    for s in sohbet_listesi:
        usd = s["motor_usd"] if s["motor_usd"] else (s.get("tahmin_usd") or 0.0)
        if not usd:
            continue
        kaynak = "motor" if s["motor_usd"] else "tahmin"
        sohbetler.append({"oturum": s["oturum"], "baslik": s["baslik"], "usd": round(usd, 4), "kaynak": kaynak,
                          "motor_usd": s["motor_usd"], "defter_usd": 0.0, "son": s["son"], "modeller": s["modeller"]})
        for m, v in (s["modeller"] or {}).items():
            model[m.replace("claude-", "")] += v
        oturumlar[s["oturum"]] = {"usd": round(usd, 4), "surec": {},
                                  "model": _yuvarla({m.replace("claude-", ""): v for m, v in (s["modeller"] or {}).items()}),
                                  "ajan_surec": []}
        z = A._zaman(s["son"])
        if z and z.date() == bugun:
            bugun_usd += usd
    return {
        "surum": SURUM, "acik": True, "orkestra": False, "uretim": L.simdi(), "proje": alan["ad"],
        "kartlar": [], "sayac": {},
        "maliyet": {"bugun": round(bugun_usd, 4), "toplam": round(sum(s["usd"] for s in sohbetler), 4), "surec": {},
                    "model": _yuvarla(dict(model.most_common(6))), "ajan_surec": [], "oturumlar": oturumlar},
        "sohbetler": sohbetler, "defter": [], "ruya": None,
    }


def alan_ozeti(alan_id: str | None) -> dict:
    """Panel için seçili çalışma alanının anlık görüntüsü (orkestra varsa tam, yoksa hafif)."""
    alanlar = L.calisma_alanlari()
    alan = next((a for a in alanlar if a["id"] == alan_id), None) or next((a for a in alanlar if a["orkestra"]), None) \
        or (alanlar[0] if alanlar else None)
    if alan is None:
        return {"acik": False, "hata": "Bu bilgisayarda Claude çalışma alanı bulunamadı."}
    sd = os.path.join(alan["yol"], ".claude", "orkestra")
    o = olustur(sd, alan["yol"]) if alan["orkestra"] else _hafif(alan)
    o["alan"] = {"id": alan["id"], "ad": alan["ad"], "yol": alan["yol"], "orkestra": alan["orkestra"]}
    return o
