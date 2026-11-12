"""01/02/03 aşama görünümleri (EDEL uyarlaması, ADR-0179): kaynak kayıttan üretilir, elle düzenlenmez.

- 01-Baslangic.md: kapı 1 kararı, gap'ler (G), başarı kriterleri (S), S→T doğrulama planı, yol kararı.
- 02-Gelistirme.md: kapı 2 kararı, plan maddeleri (P) ve todo durumu, G→P→S bağları.
- 03-Dogrulama-ve-Yayin.md: kapı 3 kararı, T→E kanıt tablosu (tazelik, commit), tam G→P→S→T→E zinciri, sözleşme sonucu, teslim.

Kaynak tektir (mevcut durum, sözleşme, plan.md, todo.md, kanit.jsonl, is.json); görünüm her üretimde baştan yazılır.
plan_gorunum.py'den ayrıdır: o kimlikleri silip düz anlatım verir, bu görünüm kimlikli izlenebilirlik satırı taşır.
"""
from __future__ import annotations

import os
import re

import is_sirasi as S
import muhendislik_kontrol as MK
import ork_lib as L

DOSYALAR = ("01-Baslangic.md", "02-Gelistirme.md", "03-Dogrulama-ve-Yayin.md")
BASLIK_NOTU = "> Bu dosya kayıttan üretilmiştir (ADR-0179, `orkestra is gorunum`); elle düzenleme, kaynağı düzelt."

_G_SATIRI = re.compile(r"^\s*[-*]\s+\*\*G(\d+):?\*\*:?[ \t]*(.*)$", re.M)
_S_SATIRI = re.compile(r"^\s*[-*]\s+\*\*S(\d+):?\*\*:?[ \t]*(.*)$", re.M)
_P_BASLIK = re.compile(r"^###[ \t]+P(\d+)\b[ \t]*(.*)$", re.M)
_TODO = re.compile(r"^\s*[-*]\s*\[([ xX])\]\s*P(\d+)\b", re.M)


def _k(n, on):
    return f"{on}{n}" if n is not None else "—"


def _kapi_bolumu(kp: dict) -> list[str]:
    sat = [f"**Kapı {kp['kapi']} ({kp['ad']}):** {kp['sonuc']}", ""]
    sat += [f"- {e['kontrol']}: {e['mesaj']}" for e in kp["eksikler"]]
    sat += [f"- engel {e}" for e in kp["engeller"]]
    if kp["eksikler"] or kp["engeller"]:
        sat.append("")
    return sat


def _bas(baslik: str, ad: str, r: dict, kaynaklar: list[str]) -> list[str]:
    return [f"# {baslik}: {ad}", "", BASLIK_NOTU, "",
            f"**Üretim:** {L.simdi()} · **Kademe:** {r['kademe']} · **Kapı modu:** {r['mod']} · **Genel:** {r['genel']}", "",
            "**Kaynak:** " + ", ".join(f"`{k}`" for k in kaynaklar if k), ""]


def _bolum_satirlari(metin: str, ad: str) -> list[str]:
    b = S._baslik_bolumu(metin or "", ad)
    return [s for s in b.splitlines() if s.strip()] if b else []


def baslangic(b: MK.Baglam, r: dict, baslik: str) -> str:
    sat = _bas(baslik, "01 Başlangıç", r, [os.path.basename(b.md_yolu or ""), os.path.basename(b.soz_yolu or ""), "plan.md"])
    sat += _kapi_bolumu(r["kapilar"][0])
    problem = _bolum_satirlari(b.soz, "Problem")
    if problem:
        sat += ["## Problem", ""] + problem + [""]
    sat += ["## Gap'ler (G)", ""]
    gler = {int(n): t for n, t in _G_SATIRI.findall(b.md or "")}
    sat += [f"- **G{n}:** {gler[n]}" for n in sorted(gler)] or ["- yok"]
    sat += ["", "## Başarı kriterleri (S)", ""]
    sler = {int(n): t for n, t in _S_SATIRI.findall(S._baslik_bolumu(b.soz or "", "Başarı kriterleri"))}
    sat += [f"- **S{n}:** {sler[n]}" for n in sorted(sler)] or ["- yok"]
    sat += ["", "## Doğrulama planı (S→T)", ""]
    for s in sorted(sler):
        tler = [t for t in sorted(b.tler) if s in b.tler[t]["s"]]
        sat.append(f"- S{s} → " + (", ".join(f"T{t}" for t in tler) if tler else "T yok"))
    yol = _bolum_satirlari(b.md, "Yol kararı")
    if yol:
        sat += ["", "## Yol kararı", ""] + yol
    return "\n".join(sat).rstrip() + "\n"


def gelistirme(b: MK.Baglam, r: dict, baslik: str) -> str:
    sat = _bas(baslik, "02 Geliştirme", r, ["plan.md", "todo.md"])
    sat += _kapi_bolumu(r["kapilar"][1])
    basliklar = {int(n): t.strip() for n, t in _P_BASLIK.findall(b.plan or "")}
    todo = {int(p): d.strip().lower() == "x" for d, p in _TODO.findall(b.todo or "")}
    sat += ["## Plan maddeleri (P)", "", "| P | Madde | Gap | Sözleşme | Todo |", "| --- | --- | --- | --- | --- |"]
    for p in sorted(b.pler):
        durum = "bitti" if todo.get(p) else ("açık" if p in todo else "todo'da yok")
        sat.append(f"| P{p} | {basliklar.get(p, '')} | {', '.join(f'G{g}' for g in sorted(b.p_g(p))) or '—'} | "
                   f"{', '.join(f'S{s}' for s in sorted(b.p_s(p))) or '—'} | {durum} |")
    biten = sum(1 for v in todo.values() if v)
    sat += ["", f"**Todo:** {biten}/{len(todo)} bitti", "", "## İzlenebilirlik (G→P→S)", ""]
    gorulen = set()
    for z in r["zincir"]:
        anahtar = (z["g"], z["p"], z["s"])
        if anahtar not in gorulen:
            gorulen.add(anahtar)
            sat.append(f"- {_k(z['g'], 'G')} → {_k(z['p'], 'P')} → {_k(z['s'], 'S')}")
    return "\n".join(sat).rstrip() + "\n"


def dogrulama(b: MK.Baglam, r: dict, baslik: str) -> str:
    sat = _bas(baslik, "03 Doğrulama ve Yayın", r, ["plan.md", MK.KANIT_DOSYA, "is.json"])
    sat += _kapi_bolumu(r["kapilar"][2])
    sat += ["## Doğrulama ve kanıt (T→E)", "", "| T | S | Son kanıt | Durum | Saat | Commit |", "| --- | --- | --- | --- | --- | --- |"]
    for t in sorted(b.tler):
        e = MK._e_ozeti(b, t)
        sat.append(f"| T{t} | {', '.join(f'S{s}' for s in b.tler[t]['s']) or '—'} | {e.get('e') or '—'} | {e['durum']} | "
                   f"{e.get('zaman') or '—'} | {(e.get('commit') or '—')[:10]} |")
    if not b.tler:
        sat.append("| — | — | — | doğrulama planı yok | — | — |")
    sat += ["", "## Tam zincir (G→P→S→T→E)", ""]
    for z in r["zincir"]:
        e = z["e"]
        sat.append(f"- {_k(z['g'], 'G')} → {_k(z['p'], 'P')} → {_k(z['s'], 'S')} → {_k(z['t'], 'T')} → "
                   f"{e.get('e') or '—'} ({e['durum']})")
    evaller = [(t, MK.son_kanit(b.kanitlar, t)) for t in sorted(b.tler) if b.tler[t]["eval"]]
    if evaller:
        sat += ["", "## Eval kanıtları", ""]
        for t, e in evaller:
            ev = (e or {}).get("eval") or {}
            sat.append(f"- T{t}: " + ", ".join(f"{a}={ev.get(a, '—')}" for a in MK.EVAL_ALANLARI) + f" (kaynak: {ev.get('kaynak', '—')})")
    sonuc = _bolum_satirlari(b.soz, "Sonuç")
    sat += ["", "## Sözleşme sonucu", ""] + (sonuc or ["- henüz yazılmadı"])
    t = b.is_kaydi.get("teslim") or {}
    sat += ["", "## Teslim", "", f"- PR: {t.get('pr') or '—'}",
            f"- Yerel birleşme: {(t.get('yerel_birlesme') or {}).get('commit', '—') if isinstance(t.get('yerel_birlesme'), dict) else (t.get('yerel_birlesme') or '—')}",
            f"- İnceleme: {t.get('inceleme') or '—'}"]
    return "\n".join(sat).rstrip() + "\n"


def uret(klasor: str) -> list[str]:
    """Üç görünümü iş klasörüne yazar; yazılan yolları döner."""
    b = MK.Baglam(klasor)
    r = MK.kontrol(klasor)
    baslik = b.is_kaydi.get("baslik") or os.path.basename(os.path.normpath(klasor))
    yollar = []
    for ad, f in zip(DOSYALAR, (baslangic, gelistirme, dogrulama)):
        yol = os.path.join(klasor, ad)
        L.atomik_yaz(yol, f(b, r, baslik))
        yollar.append(yol)
    return yollar


def var_mi(klasor: str) -> bool:
    return os.path.isfile(os.path.join(klasor, DOSYALAR[0]))
