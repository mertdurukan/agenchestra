"""Orkestra niyet kaydı: hangi sohbette hangi projenin hangi parçası yapılıyor, neye yarayacak, kimi bekliyor.

Kayıt hesap genelidir (bütün projeler tek dosyada): ~/.claude/orkestra-panel/niyet.jsonl
Olay türleri:
  niyet   ana ajan yazar: `orkestra niyet --ne "…" --neden "…"`  (iş değişince; aynı işin devamında yazılmaz)
  sonuc   ana ajan yazar: `orkestra niyet --sonuc "…"`            (iş bitince ne çıktı)
  istek   UserPromptSubmit hook'u (kullanıcı yazdı → Claude çalışıyor)
  tur     Stop hook'u (Claude turu bitirdi → seni bekliyor)
  kapandi SessionEnd hook'u
`gorunum()` bunları oturum başına tek satıra indirger; panel /simdi.json ile okur.
"""
from __future__ import annotations

import argparse
import collections
import datetime
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ork_lib as L  # noqa: E402

GENEL_DIZIN = os.path.join(os.path.expanduser("~"), ".claude", "orkestra-panel")
NIYET_YOLU = os.path.join(GENEL_DIZIN, "niyet.jsonl")
AZAMI_BAYT = 3 * 1024 * 1024
ESKI_GUN = 3          # bu kadar gün dokunulmayan sohbet "beklemede" sayılır
GORUNUM_GUN = 7       # şeritte gösterilen en eski etkinlik


def _kisalt(metin: str | None, n: int) -> str:
    m = " ".join(re.sub(r"</?[A-Za-z_\-]+[^>]*>", " ", metin or "").split())  # <pasted_content …> gibi etiketler
    return m if len(m) <= n else m[: n - 1].rstrip() + "…"


def olay(oturum: str | None, proje: str | None, tur: str, **alan) -> None:
    """Tek olay ekler. Hata asla çağırana taşmaz (hook'ları bozmamalı)."""
    if not oturum or oturum == "-":
        return
    try:
        os.makedirs(GENEL_DIZIN, exist_ok=True)
        if os.path.exists(NIYET_YOLU) and os.path.getsize(NIYET_YOLU) > AZAMI_BAYT:
            with L.kilit(NIYET_YOLU):
                if os.path.getsize(NIYET_YOLU) > AZAMI_BAYT:
                    os.replace(NIYET_YOLU, NIYET_YOLU + ".1")
        kayit = {"zaman": L.simdi(), "oturum": oturum, "proje": os.path.abspath(proje) if proje else None, "tur": tur}
        kayit.update({k: (L.maskele(v) if isinstance(v, str) else v) for k, v in alan.items() if v not in (None, "")})
        L.jsonl_ekle(NIYET_YOLU, kayit)
    except Exception:
        pass


def son_niyet(oturum: str) -> dict | None:
    """Bu oturumun en son niyet kaydı (hook bağlamına koymak için)."""
    son = None
    for k in L.jsonl_oku(NIYET_YOLU):
        if k.get("oturum") == oturum and k.get("tur") in ("niyet", "sonuc"):
            son = k
    return son


def baglam_metni(oturum: str | None) -> str:
    """UserPromptSubmit'te ana ajana verilen kısa hatırlatma."""
    k = son_niyet(oturum) if oturum else None
    kayitli = (f"Kayıtlı niyet: ne=\"{k.get('ne', '')}\" · neden=\"{k.get('neden', '')}\"" if k and k.get("tur") == "niyet"
               else "Bu sohbet için kayıtlı niyet yok.")
    return ("Orkestra niyet kaydı (kullanıcı birden çok sohbeti panelden izliyor). " + kayitli + " "
            "Bu istek YENİ bir iş başlatıyor ya da işi değiştiriyorsa, ilk araç çağrılarınla birlikte bir kez çalıştır: "
            "`orkestra niyet --ne \"<şu an ne yapılıyor, en çok 12 kelime>\" --neden \"<bu neye yarayacak, hangi hedefe hizmet ediyor; en çok 15 kelime>\"`. "
            "Aynı işin devamıysa YAZMA. İş bitince: `orkestra niyet --sonuc \"<ne çıktı, en çok 15 kelime>\"`. "
            "Kullanıcıya bundan söz etme.")


# ---------------------------------------------------------------- görünüm

def _zaman(s):
    try:
        z = datetime.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return z if z.tzinfo else z.astimezone()
    except Exception:
        return None


def _basliklar(proje: str) -> dict:
    """Projenin sohbetleri: oturum → (kenar çubuğundaki ad, transkriptin son değişme zamanı); ork_lib önbelleğiyle."""
    try:
        sd = os.path.join(proje, ".claude", "orkestra")
        ls = L.sohbetler(sd if os.path.isdir(sd) else None, proje, limit=40, tahmin=False)
        return {s["oturum"]: (s["baslik"], s.get("son")) for s in ls}
    except Exception:
        return {}


def _gunluk_istekleri(proje: str, sinir: datetime.datetime) -> list[dict]:
    """Niyet kaydı başlamadan önceki sohbetler için orkestra günlüğündeki istekler (yedek)."""
    out = []
    for o in L.jsonl_oku(os.path.join(proje, ".claude", "orkestra", "gunluk.jsonl")):
        if o.get("tur") == "istek" and (_zaman(o.get("zaman")) or sinir) >= sinir and not str(o.get("metin", "")).startswith("<"):
            out.append({"zaman": o["zaman"], "oturum": o.get("oturum"), "proje": proje, "tur": "istek", "metin": o.get("metin")})
    return out


def _proje_adi(yol: str | None) -> str:
    return os.path.basename((yol or "").rstrip("\\/")) or (yol or "?")


def gorunum(gun: int = GORUNUM_GUN) -> dict:
    simdi = datetime.datetime.now().astimezone()
    sinir = simdi - datetime.timedelta(days=gun)
    olaylar = [o for o in L.jsonl_oku(NIYET_YOLU) if (_zaman(o.get("zaman")) or sinir) >= sinir]
    projeler = {o.get("proje") for o in olaylar if o.get("proje")}
    # orkestralı projelerin günlüğünden, niyet kaydı öncesi sohbetleri de getir
    if hasattr(L, "calisma_alanlari"):
        try:
            projeler |= {a["yol"] for a in L.calisma_alanlari() if a.get("orkestra")}
        except Exception:
            pass
    kayitli_oturum = {o.get("oturum") for o in olaylar}
    for p in list(projeler):
        olaylar += [o for o in _gunluk_istekleri(p, sinir) if o["oturum"] not in kayitli_oturum]
    olaylar.sort(key=lambda o: o.get("zaman") or "")

    oturumlar: dict = collections.OrderedDict()
    akis = []
    for o in olaylar:
        oid = o.get("oturum")
        s = oturumlar.setdefault(oid, {"oturum": oid, "proje_yol": o.get("proje"), "ne": None, "neden": None, "sonuc": None,
                                       "niyet_zamani": None, "son_istek": None, "son_olay": None, "son_zaman": None,
                                       "baslangic": o.get("zaman"), "istek_sayisi": 0, "kapandi": False, "hooklu": False})
        s["proje_yol"] = s["proje_yol"] or o.get("proje")
        t = o.get("tur")
        s["hooklu"] = s["hooklu"] or t in ("tur", "kapandi", "niyet", "sonuc")
        if t == "niyet":
            if s["ne"] and (o.get("ne") != s["ne"]):
                akis.append({"zaman": s["niyet_zamani"], "oturum": oid, "proje_yol": s["proje_yol"], "tur": "onceki",
                             "ne": s["ne"], "neden": s["neden"], "sonuc": s["sonuc"]})
            s.update(ne=o.get("ne") or s["ne"], neden=o.get("neden") or s["neden"], niyet_zamani=o["zaman"], sonuc=None)
            akis.append({"zaman": o["zaman"], "oturum": oid, "proje_yol": s["proje_yol"], "tur": "niyet",
                         "ne": o.get("ne"), "neden": o.get("neden")})
        elif t == "sonuc":
            s["sonuc"] = o.get("sonuc")
            s["sonuc_zamani"] = o["zaman"]
            akis.append({"zaman": o["zaman"], "oturum": oid, "proje_yol": s["proje_yol"], "tur": "sonuc",
                         "ne": s["ne"], "sonuc": o.get("sonuc")})
        elif t == "istek":
            s["son_istek"] = o.get("metin") or s["son_istek"]
            s["istek_sayisi"] += 1
            s["kapandi"] = False
        elif t == "kapandi":
            s["kapandi"] = True
        if t in ("istek", "tur", "kapandi", "niyet", "sonuc"):
            if t in ("istek", "tur", "kapandi"):
                s["son_olay"] = t
            s["son_zaman"] = o["zaman"]

    basliklar: dict = {}
    for p in {s["proje_yol"] for s in oturumlar.values() if s["proje_yol"]}:
        basliklar.update(_basliklar(p))
    kartlar: dict = collections.defaultdict(list)
    for p in {s["proje_yol"] for s in oturumlar.values() if s["proje_yol"]}:
        sd = os.path.join(p, ".claude", "orkestra")
        if os.path.isdir(sd):
            for k in L.kartlar(sd):
                d = L.kart_durumu_hesapla(k)
                if k.get("oturum") in oturumlar:
                    kartlar[k["oturum"]].append({"id": k["id"], "baslik": _kisalt(k.get("baslik"), 70), "durum": d,
                                                 "teslim_ozeti": _kisalt(k.get("teslim_ozeti"), 120)})

    satirlar = []
    for s in oturumlar.values():
        z = _zaman(s["son_zaman"])
        yas_gun = (simdi - z).total_seconds() / 86400 if z else 99
        acik_kart = [k for k in kartlar.get(s["oturum"], []) if k["durum"] in L.ACIK_DURUMLAR]
        baslik, transkript_son = basliklar.get(s["oturum"], (None, None))
        tz = _zaman(transkript_son)
        if tz and (not z or tz > z):
            z, s["son_zaman"] = tz, tz.isoformat(timespec="minutes")
            yas_gun = (simdi - z).total_seconds() / 86400
        bosta_dk = (simdi - z).total_seconds() / 60 if z else 9999
        if s["kapandi"]:
            bekleyen = "kapandi"
        elif s["sonuc"] and (s.get("sonuc_zamani") or "") >= (s["niyet_zamani"] or ""):
            bekleyen = "bitti"
        elif yas_gun >= ESKI_GUN:
            bekleyen = "beklemede"
        elif (s["son_olay"] == "istek" or acik_kart) and (s["hooklu"] or bosta_dk < 10):
            bekleyen = "claude"  # hook'suz (eski) sohbette transkript 10 dk durgunsa Claude çalışmıyordur
        else:
            bekleyen = "sen"
        # niyet yazılmadıysa yedek: açık kart ya da son istek
        yedek = None
        if not s["ne"]:
            if acik_kart:
                yedek = acik_kart[0]["baslik"]
            elif kartlar.get(s["oturum"]):
                yedek = kartlar[s["oturum"]][-1]["baslik"]
            else:
                yedek = _kisalt(s["son_istek"], 110)
        satirlar.append({
            "oturum": s["oturum"], "kisa": (s["oturum"] or "")[:8], "proje": _proje_adi(s["proje_yol"]), "proje_yol": s["proje_yol"],
            "sohbet": baslik or (s["oturum"] or "")[:8],
            "ne": s["ne"], "neden": s["neden"], "sonuc": s["sonuc"], "yedek": yedek, "niyet_var": bool(s["ne"]),
            "bekleyen": bekleyen, "son_zaman": s["son_zaman"], "baslangic": s["baslangic"], "istek_sayisi": s["istek_sayisi"],
            "son_istek": _kisalt(s["son_istek"], 160),
            "kartlar": {"acik": len(acik_kart), "toplam": len(kartlar.get(s["oturum"], [])),
                        "teslim": sum(1 for k in kartlar.get(s["oturum"], []) if k["durum"] == "teslim"),
                        "aktif": acik_kart[:3]},
        })
    sira = {"sen": 0, "claude": 1, "bitti": 2, "beklemede": 3, "kapandi": 4}
    satirlar.sort(key=lambda r: (sira.get(r["bekleyen"], 9), -(_zaman(r["son_zaman"]) or sinir).timestamp()))
    for a in akis:
        a["proje"] = _proje_adi(a.get("proje_yol"))
        a["sohbet"] = (basliklar.get(a["oturum"]) or (None,))[0] or (a["oturum"] or "")[:8]
    akis = sorted([a for a in akis if a["tur"] != "onceki"], key=lambda a: a["zaman"] or "", reverse=True)[:40]
    sayac = collections.Counter(r["bekleyen"] for r in satirlar)
    return {"uretim": L.simdi(), "oturumlar": satirlar, "akis": akis, "sayac": dict(sayac),
            "niyetsiz": sum(1 for r in satirlar if not r["niyet_var"] and r["bekleyen"] in ("sen", "claude"))}


# ---------------------------------------------------------------- komut satırı

def _oturum_projesi(oturum: str) -> str | None:
    """Oturumun projesi: hook'ların yazdığı kayıttan (Bash'in o anki klasörü proje olmayabilir), yoksa transkriptin yerinden."""
    for k in reversed(L.jsonl_oku(NIYET_YOLU)):
        if k.get("oturum") == oturum and k.get("tur") in ("istek", "tur") and k.get("proje"):
            return k["proje"]
    kok = os.path.join(os.path.expanduser("~"), ".claude", "projects")
    for d in os.listdir(kok) if os.path.isdir(kok) else []:
        if os.path.exists(os.path.join(kok, d, oturum + ".jsonl")) and hasattr(L, "calisma_alanlari"):
            return next((a["yol"] for a in L.calisma_alanlari() if a["id"] == d), None)
    return None


def cmd(a) -> None:
    oturum = a.oturum or os.environ.get("CLAUDE_CODE_SESSION_ID") or os.environ.get("CLAUDE_SESSION_ID")
    if a.goster:
        g = gorunum()
        for r in g["oturumlar"]:
            print(f"[{r['bekleyen']}] {r['proje']} · {r['sohbet']}: {r['ne'] or r['yedek'] or '-'}"
                  + (f" → {r['neden']}" if r["neden"] else "") + (f" ✓ {r['sonuc']}" if r["sonuc"] else ""))
        return
    if getattr(a, "ajan_id", None):
        sys.exit("niyet: yalnız ana ajan yazar (alt ajanlar kart özetini kullanır).")
    if not oturum:
        sys.exit("niyet: oturum kimliği bulunamadı (CLAUDE_CODE_SESSION_ID yok); --oturum ver.")
    proje = _oturum_projesi(oturum) or L.proje_dizini()
    if a.ne or a.neden:
        if not (a.ne and a.neden):
            sys.exit("niyet: --ne ile --neden birlikte verilir.")
        olay(oturum, proje, "niyet", ne=_kisalt(a.ne, 140), neden=_kisalt(a.neden, 160))
    if a.sonuc:
        olay(oturum, proje, "sonuc", sonuc=_kisalt(a.sonuc, 160))
    if not (a.ne or a.sonuc):
        sys.exit("niyet: --ne/--neden ya da --sonuc ver (göstermek için --goster).")
    print("niyet kaydedildi")


def ekle_ayristirici(alt) -> None:
    p = alt.add_parser("niyet", help="sohbetin şu an ne yaptığını ve neye yarayacağını kaydet (panel 'Şu an' şeridi)")
    p.add_argument("--ne", help="şu an ne yapılıyor (≤12 kelime)")
    p.add_argument("--neden", help="neye yarayacak, hangi hedefe hizmet ediyor (≤15 kelime)")
    p.add_argument("--sonuc", help="iş bitince ne çıktı (≤15 kelime)")
    p.add_argument("--oturum", help="oturum kimliği (varsayılan: CLAUDE_CODE_SESSION_ID)")
    p.add_argument("--goster", action="store_true", help="bütün sohbetlerin şu anki durumunu yaz")
    p.set_defaults(f=cmd)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(prog="niyet")
    alt = ap.add_subparsers()
    ekle_ayristirici(alt)
    a = ap.parse_args(["niyet"] + sys.argv[1:])
    a.f(a)
