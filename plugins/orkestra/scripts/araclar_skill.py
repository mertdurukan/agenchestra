"""Panel /araclar: skill listesi ve aç/kapat (ADR-0098).

Kaynaklar: eklenti (`orkestra:<ad>`), kullanıcı (`~/.claude/skills`) ve proje (`<proje>/.claude/skills`).
Yazma yalnız projenin `.claude/settings.local.json` dosyasına yapılır (yerel, git dışı):
- kullanıcı/proje skill'i: `skillOverrides[ad] = "off"` (listeden çıkar);
- eklenti skill'i: `permissions.deny` içine `Skill(orkestra:ad)` (çağrı engellenir, listede görünmeye devam eder;
  skillOverrides eklenti skill'inde etkisizdir — skill_deney_20261030.md).
Yalnız bulunan skill adları kabul edilir. Yazma: doğrula → yedekle → geçici dosya + os.replace; bozuk JSON'a dokunulmaz.
"""
from __future__ import annotations

import json
import os
import re
import shutil

EKLENTI_KOK = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
EKLENTI_ADI = "orkestra"
DURUMLAR = ("acik", "kapali")
KONUMLAR = ("kapali", "ihtiyacta", "surekli")  # ADR-0113: panel anahtarı üç konumlu
_ALAN = re.compile(r"^(name|description)\s*:\s*(.*?)\s*$", re.M)


class SkillHata(ValueError):
    """İstemciye gösterilebilir doğrulama hatası."""


def _alanlar(baslik: str) -> dict:
    """name/description değerleri; `>-`, `|` gibi blok değerler girintili satırlarından birleştirilir."""
    sonuc, satirlar, i = {}, baslik.splitlines(), 0
    while i < len(satirlar):
        m = _ALAN.match(satirlar[i])
        i += 1
        if not m:
            continue
        ad, deger = m.group(1), m.group(2)
        if re.fullmatch(r"[>|][+-]?", deger):
            parca = []
            while i < len(satirlar) and (not satirlar[i].strip() or satirlar[i][:1] in " \t"):
                parca.append(satirlar[i].strip())
                i += 1
            deger = " ".join(p for p in parca if p)
        sonuc[ad] = deger
    return sonuc


def _basliktan(yol: str, varsayilan: str) -> tuple:
    try:
        with open(yol, encoding="utf-8") as f:
            metin = f.read(4000)
    except OSError:
        return varsayilan, ""
    m = re.match(r"---\s*\n(.*?)\n---", metin, re.S)
    alanlar = _alanlar(m.group(1)) if m else {}
    return (alanlar.get("name") or varsayilan).strip("'\""), (alanlar.get("description") or "").strip("'\"")


def _tara(dizin: str, kaynak: str, onek: str = "") -> list:
    if not os.path.isdir(dizin):
        return []
    sonuc = []
    for klasor in sorted(os.listdir(dizin)):
        md = os.path.join(dizin, klasor, "SKILL.md")
        if os.path.isfile(md):
            ad, aciklama = _basliktan(md, klasor)
            sonuc.append({"ad": onek + ad, "kaynak": kaynak, "aciklama": aciklama[:300]})
    return sonuc


def ayar_yolu(proje: str) -> str:
    return os.path.join(proje, ".claude", "settings.local.json")


def _oku(yol: str) -> dict:
    if not os.path.exists(yol):
        return {}
    try:
        with open(yol, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError) as e:
        raise SkillHata("ayar dosyası okunamadı; dosyaya dokunulmadı") from e
    if not isinstance(d, dict):
        raise SkillHata("ayar dosyası bir JSON nesnesi değil; dosyaya dokunulmadı")
    return d


def _yaz(yol: str, veri: dict) -> None:
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    if os.path.exists(yol):
        shutil.copy2(yol, yol + ".orkestra.bak")
    gecici = yol + ".orkestra.tmp"
    with open(gecici, "w", encoding="utf-8", newline="\n") as f:
        json.dump(veri, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(gecici, yol)


def _kural(ad: str) -> str:
    return f"Skill({ad})"


def konum_yolu(proje: str) -> str:
    return os.path.join(proje, ".claude", "orkestra", "skill_durum.json")


VARSAYILAN_YOL = os.path.join(EKLENTI_KOK, "ayarlar", "skill_surekli.json")


def _liste_oku(yol: str, anahtar: str) -> set:
    try:
        with open(yol, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return set()
    ad = d.get(anahtar) if isinstance(d, dict) else None
    return {x for x in ad if isinstance(x, str)} if isinstance(ad, list) else set()


def varsayilan_surekli() -> set:
    """Eklentinin her projede sürekli açık verdiği skill adları (ayarlar/skill_surekli.json, ADR-0119)."""
    return _liste_oku(VARSAYILAN_YOL, "varsayilan")


def surekli_oku(proje: str) -> set:
    """Sürekli açık skill adları (ADR-0113, ADR-0119): eklenti varsayılanı - projenin `haric` listesi + projenin `surekli` listesi.
    Dosya yok ya da bozuksa o katman boş küme; yazma yolu bozuk dosyaya dokunmaz."""
    yol = konum_yolu(proje)
    return (varsayilan_surekli() - _liste_oku(yol, "haric")) | _liste_oku(yol, "surekli")


def liste(proje: str, kullanici_dizin: str | None = None, eklenti_dizin: str | None = None) -> list:
    """Her skill için: ad, kaynak (eklenti|kullanici|proje), aciklama, durum (acik|kapali), konum (kapali|ihtiyacta|surekli), mekanizma."""
    kullanici_dizin = kullanici_dizin or os.path.join(os.path.expanduser("~"), ".claude", "skills")
    eklenti_dizin = eklenti_dizin or os.path.join(EKLENTI_KOK, "skills")
    ayar = _oku(ayar_yolu(proje))
    kapali_ek = set((ayar.get("permissions") or {}).get("deny") or [])
    off = {k for k, v in (ayar.get("skillOverrides") or {}).items() if v == "off"}
    surekli = surekli_oku(proje)
    sonuc = []
    for s in _tara(eklenti_dizin, "eklenti", EKLENTI_ADI + ":"):
        s["mekanizma"] = "deny"
        s["durum"] = "kapali" if _kural(s["ad"]) in kapali_ek else "acik"
        sonuc.append(s)
    for kaynak, dizin in (("kullanici", kullanici_dizin), ("proje", os.path.join(proje, ".claude", "skills"))):
        for s in _tara(dizin, kaynak):
            s["mekanizma"] = "skillOverrides"
            s["durum"] = "kapali" if s["ad"] in off else "acik"
            sonuc.append(s)
    for s in sonuc:
        s["konum"] = "kapali" if s["durum"] == "kapali" else ("surekli" if s["ad"] in surekli else "ihtiyacta")
    return sonuc


def degistir(ad, durum, proje: str, kullanici_dizin: str | None = None, eklenti_dizin: str | None = None) -> dict:
    """Skill'i açar ya da kapatır; yalnız listede bulunan ad kabul edilir. Sonucu dosyadan yeniden okuyup döner."""
    if not isinstance(ad, str):
        raise SkillHata("geçersiz skill adı")
    if durum not in DURUMLAR:
        raise SkillHata("durum acik ya da kapali olmalı")
    bulunan = {s["ad"]: s for s in liste(proje, kullanici_dizin, eklenti_dizin)}
    if ad not in bulunan:
        raise SkillHata("bilinmeyen skill")
    yol = ayar_yolu(proje)
    ayar = _oku(yol)
    if bulunan[ad]["mekanizma"] == "deny":
        izin = ayar.setdefault("permissions", {})
        deny = [x for x in izin.get("deny") or [] if x != _kural(ad)]
        if durum == "kapali":
            deny.append(_kural(ad))
        if deny:
            izin["deny"] = deny
        else:
            izin.pop("deny", None)
        if not izin:
            ayar.pop("permissions", None)
    else:
        ov = dict(ayar.get("skillOverrides") or {})
        if durum == "kapali":
            ov[ad] = "off"
        else:
            ov.pop(ad, None)
        if ov:
            ayar["skillOverrides"] = ov
        else:
            ayar.pop("skillOverrides", None)
    _yaz(yol, ayar)
    gercek = {s["ad"]: s["durum"] for s in liste(proje, kullanici_dizin, eklenti_dizin)}[ad]
    return {"ad": ad, "istenen": durum, "durum": gercek, "tamam": gercek == durum}


def konum_ata(ad, konum, proje: str, kullanici_dizin: str | None = None, eklenti_dizin: str | None = None) -> dict:
    """Üç konum (ADR-0113): kapali = çağrı engelli; ihtiyacta = açık, açıklama uyunca çağrılır; surekli = açık ve
    oturum açılışında gövdesi bağlama yüklenir. Sonucu dosyalardan yeniden okuyup döner."""
    if konum not in KONUMLAR:
        raise SkillHata("konum kapali, ihtiyacta ya da surekli olmalı")
    yol = konum_yolu(proje)
    d = {}
    if os.path.exists(yol):
        try:
            with open(yol, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError) as e:
            raise SkillHata("skill_durum.json okunamadı; dosyaya dokunulmadı") from e
        if not isinstance(d, dict):
            raise SkillHata("skill_durum.json bir JSON nesnesi değil; dosyaya dokunulmadı")
    r = degistir(ad, "kapali" if konum == "kapali" else "acik", proje, kullanici_dizin, eklenti_dizin)
    if not r["tamam"]:
        return {**r, "konum": None, "istenen": konum, "tamam": False}
    once = surekli_oku(proje)
    kume = (once | {ad}) if konum == "surekli" else (once - {ad})
    if kume != once:
        # ADR-0119: eklenti varsayılanı projede `haric` ile kapatılır; proje kendi `surekli` listesini yalnız varsayılan dışı adlarla tutar
        varsayilan = varsayilan_surekli()
        d["surekli"] = sorted(kume - varsayilan)
        d["haric"] = sorted(varsayilan - kume)
        if not d["haric"]:
            d.pop("haric")
        _yaz(yol, d)
    gercek = {s["ad"]: s for s in liste(proje, kullanici_dizin, eklenti_dizin)}[ad]
    return {"ad": ad, "istenen": konum, "durum": gercek["durum"], "konum": gercek["konum"], "tamam": gercek["konum"] == konum}


def govde_yolu(ad, proje: str, kullanici_dizin: str | None = None, eklenti_dizin: str | None = None):
    """Listede bulunan skill'in SKILL.md yolu; yoksa None (sürekli açık yükleme için, ADR-0113)."""
    kullanici_dizin = kullanici_dizin or os.path.join(os.path.expanduser("~"), ".claude", "skills")
    eklenti_dizin = eklenti_dizin or os.path.join(EKLENTI_KOK, "skills")
    for dizin, onek in ((eklenti_dizin, EKLENTI_ADI + ":"), (kullanici_dizin, ""), (os.path.join(proje, ".claude", "skills"), "")):
        if not os.path.isdir(dizin):
            continue
        for klasor in sorted(os.listdir(dizin)):
            md = os.path.join(dizin, klasor, "SKILL.md")
            if os.path.isfile(md) and onek + _basliktan(md, klasor)[0] == ad:
                return md
    return None
