"""İş klasörü, ADR ve kural metni araması (I-139 P7, bce F37): `orkestra ara "<sorgu>"`.

Saf Python, model çağırmaz. Yöntem `oner.benzer` ile aynıdır (TF-IDF + kosinüs); belgeler kart gibi verilir.
Kaynaklar: işlerin klasöründeki `*.md` (merkezi iş kaydından), `<proje>/adr/*.md`, `<proje>/.claude/rules/*.md`.
Dizin her aramada yeniden kurulur (yüzlerce küçük md; kalıcı dizin yok, eskime sorunu yok).
"""
from __future__ import annotations

import glob
import os
import re

import oner

AZAMI_KARAKTER = 20000


def _oku(yol: str) -> str:
    try:
        with open(yol, encoding="utf-8", errors="replace") as f:
            return f.read(AZAMI_KARAKTER)
    except OSError:
        return ""


def _baslik(metin: str, yol: str) -> str:
    for s in metin.splitlines():
        if s.startswith("# "):
            return s[2:].strip()
    return os.path.basename(yol)


def belgeler(proje: str, sd: str | None = None) -> list[dict]:
    """[{yol (proje köküne göreli), tur: is|adr|kural, is_id, baslik, metin}]"""
    adaylar: list[tuple[str, str, str]] = []
    if sd:
        try:
            import is_kaydi
            for g in is_kaydi.is_liste(sd):
                kl = g.get("klasor")
                if kl and os.path.isdir(kl):
                    adaylar += [(p, "is", g["id"]) for p in sorted(glob.glob(os.path.join(kl, "*.md")))]
        except Exception:
            pass
    adaylar += [(p, "adr", "") for p in sorted(glob.glob(os.path.join(proje, "adr", "*.md")))]
    adaylar += [(p, "kural", "") for p in sorted(glob.glob(os.path.join(proje, ".claude", "rules", "*.md")))]
    sonuc, gorulen = [], set()
    for yol, tur, is_id in adaylar:
        mutlak = os.path.abspath(yol)
        if mutlak in gorulen:
            continue
        gorulen.add(mutlak)
        metin = _oku(mutlak)
        if not metin.strip():
            continue
        try:
            goreli = os.path.relpath(mutlak, proje)
        except ValueError:
            goreli = mutlak
        sonuc.append({"yol": goreli.replace("\\", "/"), "tur": tur, "is_id": is_id, "baslik": _baslik(metin, mutlak), "metin": metin})
    return sonuc


def _parca(metin: str, sorgu_tokenleri: set[str]) -> str:
    """Sorgu sözcüklerinden en çok içeren satır (en çok 140 karakter)."""
    en, en_n = "", 0
    for s in metin.splitlines():
        if not s.strip():
            continue
        n = len(sorgu_tokenleri & set(oner._tokenler(s)))
        if n > en_n:
            en, en_n = s.strip(), n
    return (en or "")[:140]


def ara(belge_listesi: list[dict], sorgu: str, n: int = 10) -> list[dict]:
    """[{yol, tur, is_id, baslik, skor, parca}] skora göre; eşleşme yoksa boş liste."""
    sorgu_tokenleri = set(oner._tokenler(sorgu))
    if not sorgu_tokenleri or not belge_listesi:
        return []
    kartlar = [{"id": i, "baslik": b["metin"]} for i, b in enumerate(belge_listesi)]
    sonuc = []
    for r in oner.benzer(kartlar, sorgu, k=max(1, n)):
        b = belge_listesi[r["id"]]
        sonuc.append({"yol": b["yol"], "tur": b["tur"], "is_id": b["is_id"], "baslik": b["baslik"], "skor": r["skor"],
                      "parca": _parca(b["metin"], sorgu_tokenleri)})
    return sonuc


def proje_kok(sd: str) -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(sd)))


def biclem(sonuc: list[dict]) -> str:
    if not sonuc:
        return "eşleşme yok"
    return "\n".join(f"{i}. [{r['tur']}{' ' + r['is_id'] if r['is_id'] else ''}] {r['yol']}  ({r['skor']:.3f})\n   {r['baslik']}"
                     + (f"\n   > {r['parca']}" if r["parca"] else "") for i, r in enumerate(sonuc, 1))
