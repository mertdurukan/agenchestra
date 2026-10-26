"""Kanıtsız iddia ölçümü (ADR-0085, I-226): sohbet dökümlerinden bilgi sorusu turlarını sayar ve etiketleme için
katmanlı rastgele örnek çıkarır; model çağrılmaz, dökümler salt okunur.

Çerçeve = turda kanıt aracı yok ve yanıtta iddia sözcüğü var. Ana ölçü çerçeveden bağımsızdır: tüm bilgi sorusu
turlarındaki A oranı = çerçeve içi A × çerçeve payı + çerçeve dışı A × (1 − pay). Kapının kendi sayısı ölçü değildir
(ilgisiz araç çağrısıyla mekanik olarak düşürülebilir). Kalıplar ve eşikler `ayarlar/kanit_rubrik.json`'dadır
(proje durum dizinindeki aynı adlı dosya anahtar bazında ezer).
"""
from __future__ import annotations

import glob
import json
import os
import random
import re
import time
from collections import Counter

_KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VARSAYILAN_YOL = os.path.join(_KOK, "ayarlar", "kanit_rubrik.json")
PROJE_DOSYA = "kanit_rubrik.json"


def _json_oku(yol):
    try:
        with open(yol, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except Exception:
        return None


def rubrik_oku(sd=None) -> dict:
    r = _json_oku(VARSAYILAN_YOL) or {}
    if sd:
        p = _json_oku(os.path.join(sd, PROJE_DOSYA))
        if p:
            r.update(p)
    return r


def _metin(icerik) -> str:
    if isinstance(icerik, str):
        return icerik
    if isinstance(icerik, list):
        return "\n".join(b.get("text", "") for b in icerik if isinstance(b, dict) and b.get("type") == "text")
    return ""


def _gercek_istem(m):
    c = m.get("content")
    if isinstance(c, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
        return None
    t = _metin(c).strip()
    if not t or t.startswith("<") or t.startswith("Caveat:") or "[Request interrupted" in t:
        return None
    return t


def tur_satirlari(satirlar):
    """Döküm satırlarını (JSONL metni) kullanıcı turlarına böler: {istem, zaman, cagrilar[(ad, girdi)], yanit(son metin)}.
    Yan zincirler atlanır."""
    tur = None
    for satir in satirlar:
        try:
            e = json.loads(satir)
        except Exception:
            continue
        if e.get("isSidechain"):
            continue
        m = e.get("message") or {}
        if e.get("type") == "user":
            t = _gercek_istem(m)
            if t is not None:
                if tur:
                    yield tur
                tur = {"istem": t, "zaman": e.get("timestamp", ""), "cagrilar": [], "yanit": ""}
        elif e.get("type") == "assistant" and tur is not None:
            for b in m.get("content") or []:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "tool_use":
                    tur["cagrilar"].append((b.get("name", ""), b.get("input") or {}))
                elif b.get("type") == "text" and b.get("text", "").strip():
                    tur["yanit"] = b["text"]
    if tur:
        yield tur


def turlar(yol):
    with open(yol, encoding="utf-8", errors="replace") as f:
        yield from tur_satirlari(f)


def son_tur(yol, kuyruk_bayt: int = 2_000_000):
    """Dökümün son kullanıcı turu (yalnız dosya sonundan `kuyruk_bayt` okunur; Stop kancasında tüm dökümü okumamak için).
    Kuyruk turu tam içermiyorsa (tur kuyruktan uzunsa) yine de kuyruktaki en son turu verir. Okunamazsa None."""
    try:
        with open(yol, "rb") as f:
            f.seek(0, os.SEEK_END)
            boy = f.tell()
            f.seek(max(0, boy - kuyruk_bayt))
            ham = f.read().decode("utf-8", errors="replace")
        satirlar = ham.split("\n")
        if boy > kuyruk_bayt:
            satirlar = satirlar[1:]  # ilk satır kesik olabilir
        son = None
        for son in tur_satirlari(satirlar):
            pass
        return son
    except Exception:
        return None


def kanit_cagrisi(cagri, r: dict) -> bool:
    """Okuma/araştırma aracı ya da (bildirim niteliğinde olmayan) kabuk komutu kanıt sayılır; todo/plan/niyet çağrıları sayılmaz."""
    ad, girdi = cagri
    if ad in (r.get("okuma_araclari") or []):
        return True
    if ad in (r.get("kabuk_araclari") or []):
        return not re.search(r.get("ilgisiz_kabuk_kalibi") or r"(?!x)x", str(girdi.get("command", "")), re.I)
    return bool(ad.startswith("mcp__") and re.search(r.get("mcp_okuma_kalibi") or r"(?!x)x", ad, re.I)
                and not re.search(r.get("mcp_ilgisiz_kalibi") or r"(?!x)x", ad))


def kanitli_mi(tur: dict, r: dict) -> bool:
    return any(kanit_cagrisi(c, r) for c in tur["cagrilar"])


def iddia_var(yanit: str, r: dict) -> bool:
    return bool(re.search(r.get("iddia_kalibi") or r"(?!x)x", yanit or "", re.I))


def tur_ozeti(tur: dict, r: dict, sinif: str) -> dict:
    return {"zaman": tur["zaman"][:16], "sinif": sinif, "kanitli": kanitli_mi(tur, r),
            "iddia": iddia_var(tur["yanit"], r), "atif": bool(re.search(r.get("atif_kalibi") or r"(?!x)x", tur["yanit"]))}


def _hedef(girdi: dict) -> str:
    for k in ("file_path", "path", "command", "pattern", "url", "query", "skill", "description"):
        v = girdi.get(k)
        if v:
            return " ".join(str(v).split())[:70]
    return ""


def baglam_metni(gecmis, r: dict) -> str:
    """Etiketleyiciye 'bağlama dayanır' (B) kararı için kanıt: son turlarda kullanıcının yazdığı kısa istem ve yapılan
    kanıt sayılan çağrılar (araç + hedef). Metin dökümden mekanik çıkarılır; etiketleyici döküm aramak zorunda kalmaz."""
    n = r.get("baglam_tur", 6)
    satirlar = []
    for t in list(gecmis)[-n:]:
        cag = [f"{a} {_hedef(g)}".strip() for a, g in t["cagrilar"] if kanit_cagrisi((a, g), r)][:10]
        satirlar.append(f"K: {' '.join(t['istem'].split())[:140]}" + (f" | Ç: {'; '.join(cag)}" if cag else ""))
    return "\n".join(satirlar)[: r.get("baglam_max_karakter", 1400)]


def olc(dosyalar, sinif_fn, r: dict, sinir_zaman: str, donem_sinir: str | None = None):
    """Dökümleri tarar. Dönüş: (sayac, ic_havuz, dis_havuz, kapanis_havuzu).
    ic_havuz = çerçeve içi soru turları, dis_havuz = çerçeve dışı soru turları; her kayıt etiketleme için istem+yanıt taşır.
    `sinif_fn(istem) -> 'soru'|'devam'|'is'`; `donem_sinir` UTC (bilgi sorusu notu öncesi/sonrası ayrımı)."""
    say = Counter()
    ic, dis, kapanis = [], [], []
    kapanis_kalibi = re.compile(r.get("kapanis_kalibi") or r"(?!x)x", re.I)
    ilgisiz = re.compile(r.get("ilgisiz_kabuk_kalibi") or r"(?!x)x", re.I)
    kabuk = set(r.get("kabuk_araclari") or [])
    yazma = set(r.get("yazma_araclari") or [])
    ist_max, yan_max = r.get("istem_max_karakter", 300), r.get("yanit_max_karakter", 600)
    for p in dosyalar:
        onceki = False
        for t in turlar(p):
            if t["zaman"] and t["zaman"] < sinir_zaman:
                onceki = kanitli_mi(t, r)
                continue
            donem = "notlu" if (donem_sinir and t["zaman"] >= donem_sinir) else "notsuz"
            kanitli = kanitli_mi(t, r)
            sinif = sinif_fn(t["istem"])
            kayit = {"oturum": os.path.basename(p)[:8], "zaman": t["zaman"][:16], "donem": donem,
                     "onceki_tur_kanitli": onceki, "istem": t["istem"][:ist_max], "yanit": t["yanit"][:yan_max],
                     "atif": bool(re.search(r.get("atif_kalibi") or r"(?!x)x", t["yanit"]))}
            if sinif == "soru":
                say[f"{donem}:soru"] += 1
                if not kanitli and iddia_var(t["yanit"], r):
                    say[f"{donem}:kanitsiz_iddiali"] += 1
                    say[f"{donem}:ki_onceki_kanitli"] += onceki
                    ic.append(dict(kayit, katman="ic"))
                else:
                    dis.append(dict(kayit, katman="dis"))
            elif sinif == "is" and kapanis_kalibi.search(t["yanit"]):
                adlar = [c[0] for c in t["cagrilar"]]
                yaz = [i for i, a in enumerate(adlar) if a in yazma]
                if yaz:
                    say[f"{donem}:is_kapanis_yazimli"] += 1
                    sonra = t["cagrilar"][yaz[-1] + 1:]
                    if not any(c[0] in kabuk and not ilgisiz.search(str(c[1].get("command", ""))) for c in sonra):
                        say[f"{donem}:is_kapanis_calistirmasiz"] += 1
                        kapanis.append(dict(kayit, katman="kapanis"))
            onceki = kanitli
    return say, ic, dis, kapanis


def ornekle(havuz: list, k: int, tohum: int) -> list:
    """Sabit tohumla yeniden üretilebilir rastgele örnek (havuz sırasından bağımsız: önce sıralanır)."""
    s = sorted(havuz, key=lambda x: (x["oturum"], x["zaman"], x["istem"]))
    random.Random(tohum).shuffle(s)
    return s[:k]


def jeffreys_ust(a: int, n: int, w: float | None = None, a2: int = 0, n2: int = 0,
                 cekilis: int = 200000, tohum: int = 1, kuyruk: float = 0.975):
    """Katmanlı oran ve Jeffreys üst sınırı. Tek katman: w=None → a/n ve Beta(a+½, n−a+½) kuyruk yüzdeliği.
    İki katman: w çerçeve payı; nokta = w·a/n + (1−w)·a2/n2. Dönüş (nokta, üst). Boş katman (n=0) için ValueError."""
    if n <= 0 or (w is not None and n2 <= 0):
        raise ValueError("katman örneği boş")
    rng = random.Random(tohum)
    xs = []
    for _ in range(cekilis):
        p = rng.betavariate(a + 0.5, n - a + 0.5)
        if w is not None:
            p = w * p + (1 - w) * rng.betavariate(a2 + 0.5, n2 - a2 + 0.5)
        xs.append(p)
    xs.sort()
    nokta = a / n if w is None else w * a / n + (1 - w) * a2 / n2
    return nokta, xs[min(len(xs) - 1, int(kuyruk * len(xs)))]


def wilson(a: int, n: int, z: float = 1.96):
    """Wilson %95 aralığı (alt, üst); n=0 için (0, 1)."""
    if n <= 0:
        return 0.0, 1.0
    p = a / n
    d = 1 + z * z / n
    m = (p + z * z / (2 * n)) / d
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return max(0.0, m - h), min(1.0, m + h)


def dosya_listesi(gun: int, desen: str, simdi: float | None = None):
    """Son `gun` günde değişen sohbet dökümleri (`desen`: jsonl dosyalarına glob; ~ açılır). Dönüş (sınır_epoch, dosyalar)."""
    simdi = simdi if simdi is not None else time.time()
    sinir = simdi - gun * 86400
    return sinir, sorted(p for p in glob.glob(os.path.expanduser(desen)) if os.path.getmtime(p) >= sinir)


def ana_olcu(ic_a: int, ic_n: int, dis_a: int, dis_n: int, soru_n: int, ic_toplam: int, **kw):
    """Ana ölçü: tüm bilgi sorusu turlarındaki A oranı (nokta, Jeffreys %95 üst). w = çerçeve içi tur / tüm soru turu."""
    if soru_n <= 0:
        raise ValueError("soru turu yok")
    return jeffreys_ust(ic_a, ic_n, ic_toplam / soru_n, dis_a, dis_n, **kw)
