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
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ork_lib as L  # noqa: E402
import analitik as A  # noqa: E402  (bugün hesabı ve ajan adı eşlemesi tek yerde)

SURUM = 2
ASILI_AJAN_DK = 30
ASILI_AJAN_TEMIZLE_SAAT = 24
ASILI_SESSIZLIK_DK = 15  # son araç çağrısından bu yana geçen süre (PostToolUse `son_arac`) aşılırsa ajan takılı sayılır
ASILI_OTURUM_SESSIZ_SAAT = 2  # oturum bu kadardır hiç olay yazmadıysa kayıtları ölü sayılır

def _sessizlik_esigi_dk() -> int:
    """Araç çağırmadan geçen bu kadar dakika ajanı takılı sayar; ORKESTRA_SESSIZLIK_DK ile ayarlanır."""
    try:
        v = int(os.environ.get("ORKESTRA_SESSIZLIK_DK", ""))
        if v > 0:
            return v
    except ValueError:
        pass
    return ASILI_SESSIZLIK_DK


def _yuvarla(d: dict, n: int = 4) -> dict:
    return {k: round(v, n) for k, v in d.items()}


_MD_BAGLANTI = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_MD_ISARET = re.compile(r"(\*{1,3}|_{2,3}|`+)")
_KART_KIMLIK = re.compile(r"\b[A-Z]{1,3}-\d+\b")


def _tok(r: dict) -> int:
    """Defter satırının token toplamı: giriş + çıkış + önbellek okuma + önbellek yazma (USD/token düğmesi için)."""
    return sum(int(r.get(a) or 0) for a in ("giris", "cikis", "onbellek_okuma", "onbellek_yazma"))


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
_DEFTER_METIN_DISI = {"v", "zaman", "gorev", "surec", "ajan", "agent_id", "oturum", "model", "kaynak", "dokunulan", "token"}


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


def _transkript_son_dokunus(oturum, agent_id):
    """Alt ajan transkriptinin son yazılma zamanı (epoch sn); bulunamazsa None (karar verilmez)."""
    if not oturum or not agent_id:
        return None
    import glob
    kok = os.path.join(os.path.expanduser("~"), ".claude", "projects")
    desen = os.path.join(glob.escape(kok), "*", glob.escape(oturum), "subagents", "**", f"agent-{glob.escape(agent_id)}.jsonl")
    try:
        yollar = glob.glob(desen, recursive=True)
        return max(os.path.getmtime(y) for y in yollar) if yollar else None
    except OSError:
        return None


def _oturum_son_olaylar() -> dict:
    """niyet.jsonl'dan oturum -> (son olay zamanı, son olay türü). Okunamazsa boş (süzgeç devre dışı)."""
    son = {}
    try:
        import niyet
        for k in L.jsonl_oku(niyet.NIYET_YOLU):
            if not isinstance(k, dict) or not k.get("oturum"):
                continue
            z = A._zaman(k.get("zaman"))
            if z and (k["oturum"] not in son or z >= son[k["oturum"]][0]):
                son[k["oturum"]] = (z, k.get("tur"))
    except Exception:
        return {}
    return son


def _oturum_olu(ol, simdi) -> bool:
    return bool(ol and (ol[1] == "kapandi" or (simdi - ol[0]).total_seconds() / 3600 >= ASILI_OTURUM_SESSIZ_SAAT))


def arka_plan_oturumlari(sd: str, simdi=None) -> dict:
    """oturum -> açık arka plan görevi sayısı (Stop kancasının `oturumlar/<oturum>.json` içindeki `acik_gorevler` kaydı).
    Kapanmış ya da niyet.ARKA_PLAN_ZAMAN_ASIMI_DK'dır etkinliği olmayan oturum sayılmaz (niyet.gorunum ile aynı ölçüt)."""
    simdi = simdi or datetime.datetime.now().astimezone()
    out: dict = {}
    try:
        adlar = os.listdir(os.path.join(sd, "oturumlar"))
        import niyet
    except Exception:
        return out
    olaylar = None
    for ad in adlar:
        if not ad.endswith(".json") or ad.startswith(("acik_ajan_", "is_")):
            continue
        try:
            with open(os.path.join(sd, "oturumlar", ad), encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            continue
        gorevler = d.get("acik_gorevler") if isinstance(d, dict) else None
        if not isinstance(gorevler, list) or not gorevler:
            continue
        oid = ad[:-5]
        if olaylar is None:
            olaylar = _oturum_son_olaylar()
        ol = olaylar.get(oid)
        son = ol[0] if ol else A._zaman(d.get("guncelleme"))
        if (ol and ol[1] == "kapandi") or (son and (simdi - son).total_seconds() / 60 >= niyet.ARKA_PLAN_ZAMAN_ASIMI_DK):
            continue
        out[oid] = len(gorevler)
    return out


def sahipsiz_ajanlar(sd: str, simdi=None) -> list:
    """Oturumu kapanmış (ya da ASILI_OTURUM_SESSIZ_SAAT sessiz) ama `acik_ajan_*.json` kaydı kalmış ajanlar (salt okuma)."""
    simdi = simdi or datetime.datetime.now().astimezone()
    olaylar = _oturum_son_olaylar()
    out = []
    try:
        adlar = sorted(os.listdir(os.path.join(sd, "oturumlar")))
    except OSError:
        return out
    for ad in adlar:
        if not (ad.startswith("acik_ajan_") and ad.endswith(".json")):
            continue
        try:
            with open(os.path.join(sd, "oturumlar", ad), encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            continue
        if isinstance(d, dict) and _oturum_olu(olaylar.get(d.get("oturum")), simdi):
            out.append({"agent_id": d.get("agent_id"), "ajan": d.get("ajan"), "gorev": d.get("gorev", "-"),
                        "oturum": d.get("oturum"), "sahipsiz": True})
    return out


def asili_ajanlar(sd: str, simdi=None, oturum=None) -> list:
    """`oturumlar/acik_ajan_*.json` kayıtlarından başlangıcı ASILI_AJAN_DK'dan eski olanları döner;
    ASILI_AJAN_TEMIZLE_SAAT'ten eski kayıtları siler (bitişi hiç gelmeyen ajanların kalıntısı).
    Canlılık süzgeci: kaydın oturumu kapanmışsa (son olay `kapandi`) ya da ASILI_OTURUM_SESSIZ_SAAT'tir sessizse
    kayıt asılı sayılmaz ve silinir; niyet kaydı olmayan oturum eski kuralla çalışır. `oturum` verilirse yalnız
    o oturumun kayıtları döner (başka oturumun ajanı bu oturuma uyarı üretmez)."""
    simdi = simdi or datetime.datetime.now().astimezone()
    out = []
    olaylar = _oturum_son_olaylar()
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
        else:
            son_arac = A._zaman(d.get("son_arac"))
            sessiz = int((simdi - son_arac).total_seconds() / 60) if son_arac else None
            # Sessizlik saati: son araç çağrısı bilinen ajan, eşik dolmadıkça (uzun süredir çalışsa da) asılı sayılmaz;
            # eşik dolduysa yaşı ne olursa olsun takılı sayılır. Kaydı olmayan eski kuralla (yaş) çalışır.
            if sessiz is not None:
                if sessiz < _sessizlik_esigi_dk():
                    continue
            elif dk < ASILI_AJAN_DK:
                continue
            ol = olaylar.get(d.get("oturum"))
            if _oturum_olu(ol, simdi):
                # Oturum kapanmış ya da uzun süredir sessiz: ajan canlı değil, kayıt kalıntıdır.
                try:
                    os.remove(yol)
                except OSError:
                    pass
                continue
            if oturum and d.get("oturum") != oturum:
                continue
            son = None if sessiz is not None else _transkript_son_dokunus(d.get("oturum"), d.get("agent_id"))
            if son is not None and (simdi.timestamp() - son) / 60 >= ASILI_AJAN_DK:
                # Transkript ASILI_AJAN_DK'dır yazılmıyor: ajan çalışmıyor, bitiş kaydı düşmemiş (bayat kayıt).
                try:
                    os.remove(yol)
                except OSError:
                    pass
                continue
            out.append({"agent_id": d.get("agent_id"), "ajan": d.get("ajan"), "gorev": d.get("gorev", "-"),
                        "surec": d.get("surec"), "oturum": d.get("oturum"), "dakika": int(dk), "sessiz_dk": sessiz})
    return out


def _is_todolari(sd: str) -> list[dict]:
    """Açık işlerin todo.md durumu: yapılan/toplam madde ve açık maddelerin ilk beşi (Claude içi panelin tek kaynağı)."""
    import is_kaydi as IK
    out = []
    try:
        liste = IK.is_liste(sd, "acik")
    except Exception:  # noqa: BLE001
        return out
    for g in liste:
        try:
            t = IK.todo_ozet(g["klasor"])
        except Exception:  # noqa: BLE001
            continue
        out.append({"id": g["id"], "ad": IK.is_adi(g.get("baslik")), "biten": t["biten"], "toplam": t["toplam"],
                    "oturumlar": [o.get("oturum") for o in g.get("oturumlar") or [] if isinstance(o, dict)],
                    "acik": [temiz_metin(m, 120) for m in t["acik_maddeler"][:5]]})
    return out


def _sohbet_dokum(sd: str, proje: str, kayitlar: list, bugun: datetime.date) -> dict:
    """Sohbet başına günlük (ve bugün için saatlik) harcama: dönem süzmesi ve zaman grafiği için.

    Kaynak 'Bugün' tutarıyla aynı token defteridir (`kayitlar`), bu yüzden bugünün toplamı KPI ile tutar.
    Her değer [usd, token]; token = giriş + çıkış + önbellek okuma + önbellek yazma. Başlık sohbet önbelleğinden gelir,
    bilinmeyen oturum kısa kimlikle anılır."""
    baslik = {}
    try:
        baslik = {s["oturum"]: s["baslik"] for s in L.sohbetler(sd, proje, limit=250, tahmin=False)}
    except Exception:  # noqa: BLE001
        pass
    sohbet: dict = {}
    for r in kayitlar:
        oid, z = r.get("oturum"), A._zaman(r.get("zaman"))
        if not oid or not z:
            continue
        usd = r.get("maliyet_usd", 0) or 0
        tok = sum(r.get(a, 0) or 0 for a in ("giris", "cikis", "onbellek_okuma", "onbellek_yazma"))
        e = sohbet.setdefault(oid, {"oturum": oid, "baslik": baslik.get(oid) or f"Sohbet {oid[:8]}", "son": None, "g": {}, "s": {}})
        zi = z.isoformat(timespec="minutes")
        if e["son"] is None or zi > e["son"]:
            e["son"] = zi
        g = e["g"].setdefault(z.date().isoformat(), [0.0, 0])
        g[0] += usd
        g[1] += tok
        if z.date() == bugun:
            h = e["s"].setdefault(f"{z.hour:02d}", [0.0, 0])
            h[0] += usd
            h[1] += tok
    for e in sohbet.values():
        for tablo in (e["g"], e["s"]):
            for k, v in tablo.items():
                tablo[k] = [round(v[0], 4), v[1]]
    return {"gun": bugun.isoformat(), "sohbetler": sorted(sohbet.values(), key=lambda x: x["son"] or "", reverse=True)}


PENCERELER = L.PENCERELER
_pencere_icinde = L.pencere_icinde   # tek takvim günü tanımı ork_lib'de (hedef panosu ve panel aynı tanımı kullanır)


def _pencere_kirilimlari(kayitlar: list, bugun: datetime.date) -> dict:
    """Her pencere için iş türü, model ve ajan x iş türü harcaması (panel: Maliyet > Harcama dağılımı)."""
    cikti = {}
    ilk = min((z.date() for r in kayitlar if (z := A._zaman(r.get("zaman")))), default=bugun)
    for w in PENCERELER:
        surec, model, ajan_surec, toplam = collections.Counter(), collections.Counter(), {}, 0.0
        surec_t, model_t, toplam_t = collections.Counter(), collections.Counter(), 0
        for r in kayitlar:
            z = A._zaman(r.get("zaman"))
            if not z or not _pencere_icinde(w, z.date(), bugun):
                continue
            usd = r.get("maliyet_usd", 0) or 0
            tok = _tok(r)
            toplam += usd
            toplam_t += tok
            surec[r.get("surec", "-")] += usd
            model[(r.get("model") or "-").replace("claude-", "")] += usd
            surec_t[r.get("surec", "-")] += tok
            model_t[(r.get("model") or "-").replace("claude-", "")] += tok
            a = ajan_surec.setdefault((r.get("ajan", "-"), r.get("surec", "-")), {"kosu": 0, "usd": 0.0, "token": 0, "cikis": 0, "giris": 0})
            a["kosu"] += 1
            a["usd"] += usd
            a["token"] += tok
            a["cikis"] += r.get("cikis", 0) or 0
            a["giris"] += (r.get("giris", 0) or 0) + (r.get("onbellek_okuma", 0) or 0) + (r.get("onbellek_yazma", 0) or 0)
        n = L.pencere_gun_sayisi(w, bugun)
        gun = (bugun - ilk).days + 1 if n is None else max(1, min(n, (bugun - ilk).days + 1))   # veri başlamadan önceki günler ortalamaya girmez
        onc = L.onceki_aralik(w, bugun)
        onceki = None
        if onc:
            satir_o = [r for r in kayitlar if (z := A._zaman(r.get("zaman"))) and onc[0] <= z.date() <= onc[1]]
            onceki = {"usd": round(sum(r.get("maliyet_usd", 0) or 0 for r in satir_o), 4), "token": sum(_tok(r) for r in satir_o)}
        cikti[w] = {"usd": round(toplam, 4), "token": toplam_t, "gun": gun, "onceki": onceki, "surec": _yuvarla(dict(surec.most_common(10))),
                    "model": _yuvarla(dict(model.most_common(6))),
                    "surec_token": dict(surec_t.most_common(10)), "model_token": dict(model_t.most_common(6)),
                    "ajan_surec": sorted([{"ajan": a, "surec": su, **{k: (round(v, 4) if k == "usd" else v) for k, v in d.items()}}
                                          for (a, su), d in ajan_surec.items()], key=lambda x: -x["usd"])[:20]}
    return cikti


def _masaustu_oturumlari() -> dict:
    """Masaüstü sohbet kayıtları (CLI oturum kimliği → {arsiv, ...}); okunamazsa boş (hiçbir kart arşivli sayılmaz)."""
    try:
        import niyet
        return niyet.masaustu_oturumlari()
    except Exception:
        return {}


def kart_sahibi(k: dict, masa: dict) -> tuple:
    """I-145: kartın güncel sahibi (`son_oturum`, yoksa oluşturan `oturum`) ve o sohbetin arşivli olup olmadığı.
    Sohbet masaüstü kayıtlarında yoksa arşivli sayılmaz (kayıt görünmüyor, yanlış iddia edilmez)."""
    sahip = k.get("son_oturum") or k.get("oturum")
    if not sahip or sahip == "-":
        return None, False
    return sahip, bool((masa.get(sahip) or {}).get("arsiv"))


def olustur(sd: str, proje: str) -> dict:
    kayitlar = L.maliyet_kayitlari(sd)
    bugun = datetime.date.today()  # yerel gün sınırı; analitik.py ile aynı (UTC 'Z' damgaları yerel güne çevrilir)

    # --- kartlar
    kart_usd = collections.Counter()
    for r in kayitlar:
        if r.get("gorev") not in (None, "-"):
            kart_usd[r["gorev"]] += r.get("maliyet_usd", 0) or 0
    kart_pencere = L.pencere_toplamlari(kayitlar, bugun, lambda r: r.get("gorev") if r.get("gorev") not in (None, "-") else None)
    sifir = {w: {"usd": 0.0, "token": 0} for w in PENCERELER}
    ks = []
    masa = _masaustu_oturumlari()
    for k in L.kartlar(sd):
        d = L.kart_durumu_hesapla(k)
        son = (k.get("denetimler") or [{}])[-1]
        sahip, arsivli = kart_sahibi(k, masa)
        ks.append({"id": k["id"], "baslik": kisalt_baslik(k["baslik"]), "durum": d, "basamak": k["basamak"],
                   "oturum": k.get("oturum"), "son_oturum": sahip, "sahip_arsivli": arsivli, "is": k.get("is"),
                   "isci": len(k.get("isciler", [])), "denetim": son.get("karar", "-"),
                   "bagimli": k.get("bagimliliklar", []), "usd": round(kart_usd.get(k["id"], 0.0), 4),
                   "pencere": kart_pencere.get(k["id"], sifir), "guncelleme": k.get("guncelleme")})
    acik = [k for k in ks if k["durum"] in L.ACIK_DURUMLAR or k["durum"] in ("beklemede", "planlandi")]
    kapali = sorted([k for k in ks if k not in acik], key=lambda x: x.get("guncelleme") or "", reverse=True)[:10]
    kartlar = sorted(acik, key=lambda x: x["id"]) + kapali

    # --- maliyet
    bugunku = [r for r in kayitlar if (z := A._zaman(r.get("zaman"))) and z.date() == bugun]
    surec, model = collections.Counter(), collections.Counter()
    surec_t, model_t = collections.Counter(), collections.Counter()
    ajan_surec: dict = {}
    for r in bugunku:
        usd = r.get("maliyet_usd", 0) or 0
        surec[r.get("surec", "-")] += usd
        model[(r.get("model") or "-").replace("claude-", "")] += usd
        surec_t[r.get("surec", "-")] += _tok(r)
        model_t[(r.get("model") or "-").replace("claude-", "")] += _tok(r)
        a = ajan_surec.setdefault((r.get("ajan", "-"), r.get("surec", "-")), {"kosu": 0, "usd": 0.0, "token": 0, "cikis": 0, "giris": 0})
        a["kosu"] += 1
        a["usd"] += usd
        a["token"] += _tok(r)
        a["cikis"] += r.get("cikis", 0) or 0
        a["giris"] += (r.get("giris", 0) or 0) + (r.get("onbellek_okuma", 0) or 0) + (r.get("onbellek_yazma", 0) or 0)

    pencereler = _pencere_kirilimlari(kayitlar, bugun)

    sohbet_listesi = L.sohbetler(sd, proje, limit=15, tahmin=True)
    oturum_ids = {s["oturum"] for s in sohbet_listesi}
    oturumlar: dict = {}
    for r in kayitlar:
        oid = r.get("oturum")
        if oid not in oturum_ids:
            continue
        o = oturumlar.setdefault(oid, {"usd": 0.0, "token": 0, "surec": collections.Counter(), "model": collections.Counter(),
                                       "surec_token": collections.Counter(), "model_token": collections.Counter(), "ajan_surec": {}})
        usd = r.get("maliyet_usd", 0) or 0
        o["usd"] += usd
        o["token"] += _tok(r)
        o["surec"][r.get("surec", "-")] += usd
        o["model"][(r.get("model") or "-").replace("claude-", "")] += usd
        o["surec_token"][r.get("surec", "-")] += _tok(r)
        o["model_token"][(r.get("model") or "-").replace("claude-", "")] += _tok(r)
        a = o["ajan_surec"].setdefault((r.get("ajan", "-"), r.get("surec", "-")), {"kosu": 0, "usd": 0.0, "token": 0, "cikis": 0, "giris": 0})
        a["kosu"] += 1
        a["usd"] += usd
        a["token"] += _tok(r)
        a["cikis"] += r.get("cikis", 0) or 0
        a["giris"] += (r.get("giris", 0) or 0) + (r.get("onbellek_okuma", 0) or 0) + (r.get("onbellek_yazma", 0) or 0)
    for o in oturumlar.values():
        o["usd"] = round(o["usd"], 4)
        o["surec"] = _yuvarla(dict(o["surec"].most_common(8)))
        o["model"] = _yuvarla(dict(o["model"].most_common(6)))
        o["surec_token"] = dict(o["surec_token"].most_common(8))
        o["model_token"] = dict(o["model_token"].most_common(6))
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

    # --- defter ve perspektif
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
    import perspektif
    rd = perspektif.durum(sd)
    try:
        import onay
        onaylar = onay.sayac(sd)
    except Exception:
        onaylar = None
    try:
        import onay
        uygulama = bool(onay.uygulama_durumu(sd))
    except Exception:
        uygulama = False

    return {
        "surum": SURUM, "acik": True, "orkestra": True, "isler": _is_todolari(sd), "uretim": L.simdi(), "proje": os.path.basename(os.path.abspath(proje)),
        "kartlar": kartlar,
        "sayac": dict(collections.Counter(k["durum"] for k in acik)),
        "maliyet": {
            "bugun": round(A.bugun_usd(kayitlar, bugun), 4),
            "toplam": round(sum(r.get("maliyet_usd", 0) or 0 for r in kayitlar), 4),
            "bugun_token": sum(_tok(r) for r in bugunku),
            "toplam_token": sum(_tok(r) for r in kayitlar),
            "kalem": L.kalemler(kayitlar),   # I-064: token ve USD, dört kalemle
            "surec": _yuvarla(dict(surec.most_common(10))),
            "model": _yuvarla(dict(model.most_common(6))),
            "surec_token": dict(surec_t.most_common(10)), "model_token": dict(model_t.most_common(6)),
            "ajan_surec": sorted([{"ajan": a, "surec": s, **{k: (round(v, 4) if k == "usd" else v) for k, v in d.items()}}
                                  for (a, s), d in ajan_surec.items()], key=lambda x: -x["usd"])[:20],
            "oturumlar": oturumlar,
            "pencere": pencereler,
        },
        "sohbetler": sohbetler,
        "sohbet_dokum": _sohbet_dokum(sd, proje, kayitlar, bugun),
        "asili_ajanlar": asili_ajanlar(sd),
        "defter": defter,
        "perspektif": {"zamani_geldi": rd["zamani_geldi"], "rapor": bool(rd["okunmamis_rapor"]), "calisiyor": bool(rd["calisiyor"]),
                 "son_perspektif": rd["son_perspektif"]},
        "onaylar": onaylar,
        # Claude içi bant yalnız bunlar için çıkar: sohbet başına açık arka plan görevi, perspektif koşusu, onay uygulaması
        "arka_plan": {"oturumlar": arka_plan_oturumlari(sd), "perspektif": bool(rd["calisiyor"]), "uygulama": uygulama},
    }


def _taze_ozet(yol: str, proje: str, bas_ns: int) -> dict | None:
    """Kilit altında çağrılır. ozet.json bu çağrı başladıktan SONRA başlamış bir hesaplamanın ürünüyse onu döner, yoksa None.

    Eşik yazım zamanı değil hesaplama başlangıcıdır: çağrıdan önce başlayıp sonra yazan hesap, çağırının az önce yaptığı
    değişikliği okumamış olabilir (bayat). Damga ozet.json'un mtime_ns+boyutuna bağlıdır; dosya başka yoldan değiştiyse
    ya da proje farklıysa eşleşmez ve yeniden hesaplanır."""
    try:
        with open(yol + ".uretim", encoding="utf-8") as f:
            d = json.load(f)
        st = os.stat(yol)
        if (not isinstance(d, dict) or d.get("mtime_ns") != st.st_mtime_ns or d.get("boyut") != st.st_size
                or d.get("proje") != os.path.abspath(proje) or int(d.get("bas_ns", 0)) < bas_ns):
            return None
        with open(yol, encoding="utf-8") as f:
            o = json.load(f)
        return o if isinstance(o, dict) else None
    except (OSError, ValueError, TypeError):
        return None


def yaz(sd: str, proje: str) -> dict | None:
    """Anlık görüntüyü yazar; hata arayüzü bozmasın diye ozet_hata.txt'ye düşer, istisna fırlatmaz."""
    try:
        # Paralel ajan bitişleri aynı dosyayı aynı anda değiştirmeye çalışıp Windows'ta PermissionError alıyordu:
        # kilit altında sıraya girer; bayat anlık görüntü yazılmaz.
        # Single-flight (I-309 C6): N bekleyenin her biri olustur'u yeniden koşunca son bekleyen N x olustur bekliyor,
        # 20 sn'yi aşıp zaman aşımı veriyordu. Kilidi alan, bu çağrıdan sonra başlamış bir hesaplamanın yazdığını
        # bulursa (_taze_ozet) yeniden hesaplamaz.
        yol = os.path.join(sd, "ozet.json")
        bas_ns = time.time_ns()   # kilit beklemesinden ÖNCE: çağırının değişiklikleri bu andan öncedir
        with L.kilit(yol, bekleme_s=20.0):   # soğuk olustur ~4 sn sürer; 5 sn, dört paralel bitişte zaman aşımı veriyordu
            o = _taze_ozet(yol, proje, bas_ns)
            if o is None:
                uretim_ns = time.time_ns()
                o = olustur(sd, proje)
                L.atomik_yaz(yol, json.dumps(o, ensure_ascii=False))
                try:   # damga yalnız eniyileme: yazılamazsa sonraki çağrı yeniden hesaplar
                    st = os.stat(yol)
                    L.atomik_yaz(yol + ".uretim", json.dumps({"bas_ns": uretim_ns, "mtime_ns": st.st_mtime_ns,
                                                              "boyut": st.st_size, "proje": os.path.abspath(proje)}))
                except OSError:
                    pass
        try:
            os.remove(yol + ".bekliyor")   # önceki çakışmadan kalan işaret: bu yazım onu karşıladı
        except OSError:
            pass
        return o
    except PermissionError:
        # Hedef başka bir okuyucuda kilitli (Windows): hata sayılmaz, işaret bırakılır; sonraki tetikte yeniden yazılır.
        try:
            with open(os.path.join(sd, "ozet.json.bekliyor"), "w", encoding="utf-8") as f:
                f.write(L.simdi() + "\n")
        except OSError:
            pass
        return None
    except Exception as e:  # noqa: BLE001
        try:
            hata_yolu = os.path.join(sd, "ozet_hata.txt")   # son 20 hata kalır (yalnız sonuncusu değil)
            onceki = []
            if os.path.exists(hata_yolu):
                with open(hata_yolu, encoding="utf-8", errors="replace") as f:
                    onceki = f.read().splitlines()[-19:]
            L.atomik_yaz(hata_yolu, "\n".join(onceki + [f"{L.simdi()} {type(e).__name__}: {e}"]) + "\n")
        except Exception:
            pass
        try:   # ADR-0035: imzalı hata defteri
            import hata_kayit as HK
            HK.kaydet(sd, "ozet", type(e).__name__, str(e))
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
        "sohbetler": sohbetler, "defter": [], "perspektif": None,
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


# ---------------------------------------------------------------- arka plan yazımı (I-328 P1)

def _kos_kilidi_al(yol: str):
    """`ozet.json.kos` kilidini BEKLEMEDEN dener (L.kilit zaman aşımında .zaman_asimi.log satırı yazar; burada yazmaz).
    Alırsa açık fd'yi döner, alamazsa None. fd kapanınca (işçi ölse de) işletim sistemi kilidi düşürür."""
    fd = os.open(yol + ".kos", os.O_RDWR | os.O_CREAT)
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fd
    except OSError:
        os.close(fd)
        return None


def _sayac(yol: str) -> int:
    try:
        with open(yol, encoding="utf-8") as f:
            return int(f.read().strip() or 0)
    except (OSError, ValueError):
        return 0


def yaz_arka_plan(sd: str, proje: str) -> None:
    """Hook yolu: özeti kullanıcıyı bekletmeden yeniletir. `ozet.json.kirli` sayacını yükseltir ve işçiyi başlatır;
    işçi zaten koşuyorsa kendiliğinden çıkar ve koşan işçi bitişte `kirli` > `islenen` görüp yineler (kaçan uyandırma yok).
    ORKESTRA_OZET_ESITZAMANLI=1 eski eşzamanlı yazımı geri getirir."""
    if os.environ.get("ORKESTRA_OZET_ESITZAMANLI") == "1":
        yaz(sd, proje)
        return
    try:
        yol = os.path.join(sd, "ozet.json")
        L.atomik_yaz(yol + ".kirli", str(time.time_ns()))
        import cfg
        subprocess.Popen([sys.executable, os.path.abspath(__file__), "--isci", sd, proje], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=cfg.ARKA_PLAN_BAYRAK,
                         close_fds=True)
    except Exception:  # noqa: BLE001  (başlatılamazsa eski yola düş: panel bayat kalmasın)
        yaz(sd, proje)


def isci(sd: str, proje: str) -> None:
    """Arka plan işçisi: `kirli` > `islenen` olduğu sürece özeti yazar. Kilidi bıraktıktan sonra bir kez daha bakar."""
    yol = os.path.join(sd, "ozet.json")
    for _ in range(50):   # üst sınır: durmayan tetik akışında sonsuz döngü olmasın
        fd = _kos_kilidi_al(yol)
        if fd is None:
            return   # başka işçi var; bitişte kirli'ye bakacak
        try:
            while True:
                t = _sayac(yol + ".kirli")
                if t <= _sayac(yol + ".islenen"):
                    break
                yaz(sd, proje)
                L.atomik_yaz(yol + ".islenen", str(t))
        finally:
            os.close(fd)
        if _sayac(yol + ".kirli") <= _sayac(yol + ".islenen"):
            return


if __name__ == "__main__" and len(sys.argv) == 4 and sys.argv[1] == "--isci":
    isci(sys.argv[2], sys.argv[3])
