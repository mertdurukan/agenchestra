"""01/02/03 aşama görünümleri (EDEL uyarlaması, ADR-0179): kaynak kayıttan üretilir, elle düzenlenmez.

- 01-Baslangic.md: kapı 1 kararı, gap'ler (G), başarı kriterleri (S), S→T doğrulama planı, yol kararı.
- 02-Gelistirme.md: kapı 2 kararı, plan maddeleri (P) ve todo durumu, G→P→S bağları.
- 00-Anlatim.md: bağlamı bilmeyen okura altı başlıkta anlatım (P6); her madde [Veri]/[Çıkarım] etiketli, model çağrısı yok.
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
            f"- Yerel birleşme: {yerel_birlesme_satiri(t.get('yerel_birlesme'))}",
            f"- İnceleme: {t.get('inceleme') or '—'}"]
    return "\n".join(sat).rstrip() + "\n"


ANLATIM = "00-Anlatim.md"

_PARANTEZ = re.compile(r"\(([^()]*)\)")
_DOSYA_SATIR = re.compile(r"[\w./\\-]+\.\w{1,6}:\d+")
_ETIKET = re.compile(r"^\[(Veri|Çıkarım)\][ \t]*")
_YORUM = re.compile(r"<!--.*?-->", re.S)


def etiket(metin: str) -> str:
    """[Veri]: parantez içinde dosya:satır ya da komut (`...`) taşıyan madde; diğerleri [Çıkarım]. Model çağrısı yok."""
    for ic in _PARANTEZ.findall(metin):
        if _DOSYA_SATIR.search(ic) or re.search(r"`[^`]+`", ic):
            return "[Veri]"
    return "[Çıkarım]"


def _madde(metin: str, girinti: str = "") -> str:
    metin = metin.strip()
    m = _ETIKET.match(metin)
    if m:
        return f"{girinti}- [{m.group(1)}] {metin[m.end():]}"
    return f"{girinti}- {etiket(metin)} {metin}"


def _mdden_maddeler(govde: str) -> list[str]:
    sat: list[str] = []
    for ham in _YORUM.sub("", govde or "").splitlines():
        if not ham.strip() or re.match(r"^\s*(```|[|][\s:|-]+[|]?\s*$)", ham):
            continue
        h = re.match(r"^#{3,6}[ \t]+(.*)$", ham)
        if h:
            sat += ["", f"**{h.group(1).strip()}**", ""]
            continue
        g = len(ham) - len(ham.lstrip())
        girinti = "  " * (g // 2) if g else ""
        t = re.sub(r"^(?:[-*]|\d+\.)\s+", "", ham.strip())
        if t.startswith("|"):
            t = " · ".join(c.strip() for c in t.strip("|").split("|") if c.strip())
        sat.append(_madde(t, girinti))
    return sat


def _numarali_bolum(metin, no_ya_da_ad) -> str:
    on = rf"{no_ya_da_ad}\.[ \t]*[^\n]*" if isinstance(no_ya_da_ad, int) else rf"(?:\d+\.[ \t]*)?{re.escape(no_ya_da_ad)}[ \t]*"
    m = re.search(rf"^##[ \t]+{on}$(.*?)(?=^##[ \t]|\Z)", metin or "", re.M | re.S)
    return m.group(1) if m else ""


def _yok(neden: str) -> list[str]:
    return [f"- [Çıkarım] {neden}"]


def anlatim(b, r, baslik):
    sat = [f"# Anlatım: {baslik}", "", BASLIK_NOTU, "",
           f"**Üretim:** {L.simdi()} · **Kademe:** {r['kademe']}", "",
           "**Kaynak:** " + ", ".join(f"`{k}`" for k in [os.path.basename(b.md_yolu or ""), "plan.md", MK.KANIT_DOSYA] if k), ""]
    for no, ad in ((1, "Sistem nasıl çalışıyor"), (2, "Ne, neden olmuyor")):
        sat += [f"## {no}. {ad}", ""]
        sat += _mdden_maddeler(_numarali_bolum(b.md, no)) or _yok(f"Mevcut durumda §{no} bölümü yok.")
        sat.append("")
    gler = {int(n): t.strip() for n, t in _G_SATIRI.findall(b.md or "")}
    basliklar = {int(n): t.strip() for n, t in _P_BASLIK.findall(b.plan or "")}
    sat += ["## 3. Ne yaparsak ne düzelir, hangi bulguyu kapatır", ""]
    p_sat = []
    for p in sorted(b.pler):
        ne = MK._alan(b.pler[p], "Ne") or basliklar.get(p, "")
        kapatir = "; ".join(f"G{g}: {gler[g]}" if g in gler else f"G{g}" for g in sorted(b.p_g(p)))
        p_sat.append(_madde(f"**P{p} {basliklar.get(p, '')}:** {ne}" + (f" Kapattığı bulgu: {kapatir}" if kapatir else "")))
    sat += p_sat or _yok("Planda P maddesi yok.")
    sat += ["", "## 4. Neyi yapmamalı", ""]
    elenen = [_madde(f"**P{p}:** {m.group(1).strip()}") for p in sorted(b.pler)
              for m in re.finditer(r"^[-*][ \t]+(?:Elenen|Alternatifler?):[ \t]*(.+)$", b.pler[p], re.M)]
    sat += elenen or _yok("Planda elenen alternatif yok.")
    sat += ["", "## 5. Düzeldiğini nasıl anlarız", ""]
    t_sat = []
    for t in sorted(b.tler):
        e = MK._e_ozeti(b, t)
        s = ", ".join(f"S{x}" for x in b.tler[t]["s"]) or "—"
        kanit = f"{e['e']} {e['durum']}" if e.get("e") else e["durum"]
        komut = b.tler[t]["komut"]
        parca = f"komut: `{komut}`; son kanıt: {kanit}" if komut else f"son kanıt: {kanit}"
        t_sat.append(_madde(f"**T{t}** ({s}) sınanır ({parca})"))
    sat += t_sat or _yok("Doğrulama planında T yok.")
    sat += ["", "## 6. Hâlâ bilinmeyenler", ""]
    ham = (_mdden_maddeler(_numarali_bolum(b.md, "Doğrulanamayanlar"))
           + _mdden_maddeler(_numarali_bolum(b.plan, "Doğrulanamayanlar")))
    ham = [x for x in ham if not re.match(r"^\s*- \[[^\]]+\] yok\.?$", x, re.I)]
    sat += ham or _yok("Mevcut durum ve plan doğrulanamayan madde bildirmiyor.")
    return "\n".join(sat).rstrip() + "\n"


def yerel_birlesme_satiri(yb) -> str:
    """Teslim bölümündeki yerel birleşme değeri: commit, kod başka depodaysa depo yolu da (I-459)."""
    if isinstance(yb, dict):
        commit = yb.get("commit") or "—"
        return f"{commit} (depo: {yb['depo']})" if yb.get("depo") else str(commit)
    return str(yb or "—")


def uret(klasor: str) -> list[str]:
    """Anlatım ve üç aşama görünümünü iş klasörüne yazar (anlatım ilk); yazılan yolları döner."""
    b = MK.Baglam(klasor)
    r = MK.kontrol(klasor)
    baslik = b.is_kaydi.get("baslik") or os.path.basename(os.path.normpath(klasor))
    yollar = []
    for ad, f in zip((ANLATIM,) + DOSYALAR, (anlatim, baslangic, gelistirme, dogrulama)):
        yol = os.path.join(klasor, ad)
        L.atomik_yaz(yol, f(b, r, baslik))
        yollar.append(yol)
    return yollar


def var_mi(klasor: str) -> bool:
    return os.path.isfile(os.path.join(klasor, DOSYALAR[0]))
