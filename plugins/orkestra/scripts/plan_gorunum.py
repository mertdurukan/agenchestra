"""Kullanıcıya gösterilen plan ve todo görünümü (ADR-0127).

plan.md ve todo.md kapıların okuduğu kayıttır (P/G kimlikleri, Dayanak, Gap, Alternatifler...); kullanıcı için anlam taşımaz.
Bu modül kayıttan, kimliksiz ve düz anlatımlı iki türev dosya üretir: plan_gorunum.md ve todo_gorunum.md.
Kayıt değişmez, görünüm kayıttan her seferinde yeniden üretilir; elle düzenlenmez.
"""
from __future__ import annotations

import os
import re

_YORUM = re.compile(r"<!--.*?-->", re.S)
_P_BASLIK = re.compile(r"^#{2,4}\s+P(\d+)\s*[—–:.-]?\s*(.*)$")
_ETIKET = re.compile(r"^\*\*([^*:]+):\*\*\s*(.*)$")
# kullanıcıya gösterilmeyen bölümler (kayıt için tutulur)
_GIZLI_BOLUM = ("dalgalar", "gap kapsama", "best in class denetimi")
_GIZLI_ALAN = ("Sıra", "Önce oku", "ADR", "LLM çıktısı", "Hazırlanma saati")
_GOSTERILEN_ALAN = {"Ne": "Ne yapılacak", "Kabul": "Bitti sayılır"}  # P maddesinde kullanıcıya giden alanlar
_NUMARA = re.compile(r"^\s*(?:[-*]\s+)?\*{0,2}[RSK]\d+:?\*{0,2}:?\s*")
_DAYANAK = re.compile(r"\s*Dayanak:\s*MD\s*§[\d.]+\.?", re.I)
_P_ATIF = re.compile(r"\s*\((?:P\d+(?:[,\s]+)?)+\)")


def _bolumler(metin: str) -> list[tuple[str, list[str]]]:
    """[(## başlık metni, gövde satırları)]; ilk öğenin başlığı '' ve gövdesi belge başıdır."""
    sonuc: list[tuple[str, list[str]]] = [("", [])]
    for s in _YORUM.sub("", metin).splitlines():
        if re.match(r"^##\s", s):
            sonuc.append((re.sub(r"^##\s+", "", s).strip(), []))
        else:
            sonuc[-1][1].append(s)
    return sonuc


def _temiz(satir: str) -> str:
    s = _NUMARA.sub("", satir)
    s = _DAYANAK.sub("", s)
    s = _P_ATIF.sub("", s)
    return re.sub(r"\s{2,}", " ", s).strip(" -")


def _maddeler(govde: list[str]) -> list[str]:
    """Madde işaretli satırlardan numarasız düz cümleler (boş ve 'Yok' dışında)."""
    cikti = []
    for s in govde:
        if re.match(r"^\s*[-*]\s+\S", s) or re.match(r"^\s*\d+\.\s+\S", s):
            t = _temiz(re.sub(r"^\s*(?:[-*]|\d+\.)\s+", "", s))
            if t:
                cikti.append(t)
    return cikti


def _numarali(liste: list[str]) -> list[str]:
    return [f"{i}. {t}" for i, t in enumerate(liste, 1)]


def _p_bloklari(govde: list[str]) -> list[tuple[int, str, dict[str, str]]]:
    bloklar: list[tuple[int, str, dict[str, str]]] = []
    for s in govde:
        m = _P_BASLIK.match(s)
        if m:
            bloklar.append((int(m.group(1)), m.group(2).strip(), {}))
            continue
        if not bloklar:
            continue
        e = _ETIKET.match(s.strip())
        if e:
            bloklar[-1][2][e.group(1).strip()] = e.group(2).strip()
        elif s.strip() and bloklar[-1][2]:
            son = list(bloklar[-1][2])[-1]
            bloklar[-1][2][son] += " " + s.strip()
    return bloklar


def hazirlanma(metin: str) -> str:
    m = re.search(r"\*\*Hazırlanma saati:\*\*\s*(\d{2}\.\d{2}\.\d{4}\s+\d{2}:\d{2})", metin)
    return m.group(1) if m else ""


def plan_gorunumu(metin: str) -> str:
    """plan.md → kullanıcı görünümü (kimliksiz, gizli alanlar çıkarılmış)."""
    bolumler = _bolumler(metin)
    baslik = next((s[2:].strip() for s in metin.splitlines() if s.startswith("# ")), "Plan")
    cikti = [f"# {baslik}", ""]
    saat = hazirlanma(metin)
    if saat:
        cikti += [f"<sub>Hazırlanma: {saat}</sub>", ""]
    for ad, govde in bolumler[1:]:
        ad_k = re.sub(r"^\d+\.\s*", "", ad).strip()
        if ad_k.lower() in _GIZLI_BOLUM:
            continue
        if ad_k == "Hedef":
            satirlar = [s for s in (_temiz(g) for g in _maddeler(govde)) if s]
            cikti += ["## Hedef", ""] + [f"- {t}" for t in satirlar] + [""]
        elif ad_k.startswith("Mevcut durumdan"):
            m = _maddeler(govde)
            if m:
                cikti += ["## Mevcut durumda bulduklarımız", ""] + _numarali(m) + [""]
        elif ad_k == "Kararlar":
            m = _maddeler(govde)
            if m:
                cikti += ["## Alınan kararlar", ""] + _numarali(m) + [""]
        elif ad_k == "Plan maddeleri":
            bl = _p_bloklari(govde)
            cikti += ["## Yapılacaklar", ""]
            for i, (_n, bas, alan) in enumerate(bl, 1):
                cikti += [f"### {i}. {bas}", ""]
                for k, etiket in _GOSTERILEN_ALAN.items():
                    if alan.get(k):
                        cikti += [f"**{etiket}:** {_temiz(alan[k]) if k == 'Ne' else alan[k]}", ""]
        elif ad_k == "Riskler":
            m = _maddeler(govde)
            if m:
                cikti += ["## Riskler", ""] + _numarali(m) + [""]
        elif ad_k in ("Doğrulanamayanlar", "Doğrulanmayanlar"):
            icerik = [s for s in govde if s.strip()]
            if icerik:
                cikti += ["## Doğrulanamayanlar", ""] + icerik + [""]
        elif ad_k:
            icerik = [s for s in govde if s.strip()]
            if icerik:
                cikti += [f"## {ad_k}", ""] + icerik + [""]
    return "\n".join(cikti).rstrip() + "\n"


def todo_gorunumu(todo: str, plan: str) -> str:
    """todo.md → plan maddesi başlığı altında gruplanmış, düz cümleli görünüm."""
    p_ad = {}
    plan_bl = None
    for ad, govde in _bolumler(plan)[1:]:
        if re.sub(r"^\d+\.\s*", "", ad).strip() == "Plan maddeleri":
            plan_bl = _p_bloklari(govde)
    sira = []
    for i, (n, bas, alan) in enumerate(plan_bl or [], 1):
        p_ad[n] = (i, bas, alan.get("Kabul", ""))
        sira.append(n)
    gruplar: dict[int, list[tuple[bool, str, str]]] = {}
    baslik = next((s[2:].strip() for s in todo.splitlines() if s.startswith("# ")), "Yapılacaklar")
    baslik = re.sub(r"^Yapılacaklar\s*[—-]\s*", "", baslik)
    baslik = re.sub(r":\s*yapılacaklar$", "", baslik)
    for s in todo.splitlines():
        m = re.match(r"^\s*[-*]\s*\[([ xX])\]\s*P(\d+):\s*(.+)$", s)
        if not m:
            continue
        metin, _, kanit = m.group(3).partition(" — ")
        gruplar.setdefault(int(m.group(2)), []).append((m.group(1).lower() == "x", metin.strip(), kanit.strip()))
    toplam = sum(len(v) for v in gruplar.values())
    bitti = sum(1 for v in gruplar.values() for x in v if x[0])
    cikti = [f"# {baslik}: yapılacaklar", "", f"**Durum:** {toplam} işten {bitti} tanesi bitti, {toplam - bitti} tanesi kaldı.", ""]
    for n in sira + [k for k in gruplar if k not in sira]:
        if n not in gruplar:
            continue
        no, bas, kabul = p_ad.get(n, (n, f"Madde {n}", ""))
        cikti += [f"## {no}. {bas}", ""]
        if kabul:
            cikti += [f"Bitti sayılır: {kabul}", ""]
        for yapildi, metin, kanit in gruplar[n]:
            cikti.append(f"- [{'x' if yapildi else ' '}] {metin}" + (f" (kanıt: {kanit})" if kanit and yapildi else ""))
        cikti.append("")
    return "\n".join(cikti).rstrip() + "\n"


def _oku(yol: str) -> str:
    try:
        with open(yol, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def _yaz(yol: str, icerik: str) -> None:
    if _oku(yol) != icerik:
        with open(yol, "w", encoding="utf-8", newline="\n") as f:
            f.write(icerik)


def uret(klasor: str) -> list[str]:
    """plan_gorunum.md ve todo_gorunum.md'yi kayıttan günceller; üretilen dosya adlarını döner."""
    plan = _oku(os.path.join(klasor, "plan.md"))
    todo = _oku(os.path.join(klasor, "todo.md"))
    uretilen = []
    if plan.strip():
        _yaz(os.path.join(klasor, "plan_gorunum.md"), plan_gorunumu(plan))
        uretilen.append("plan_gorunum.md")
    if todo.strip() and plan.strip():
        _yaz(os.path.join(klasor, "todo_gorunum.md"), todo_gorunumu(todo, plan))
        uretilen.append("todo_gorunum.md")
    return uretilen
