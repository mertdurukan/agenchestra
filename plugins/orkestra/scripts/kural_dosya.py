"""Kural dosyaları: sistemin çalışmasını yöneten tüm kural/yönerge dosyalarını listeler, tam okur, güvenli yazar.

Panelin Kurallar sayfası kullanır. Dosya yolu istemciden asla alınmaz: kimlik (yol özeti) her istekte taze
listeden çözülür, yani yalnız aşağıdaki beyaz listedeki dosyalar okunur/yazılır.

Gruplar: proje (CLAUDE.md, AGENTS.md, .claude/rules, ajanlar, skill'ler, komutlar, ayarlar),
kullanıcı (~/.claude/CLAUDE.md ve ayarlar), eklenti (KURALLAR.md, ajanlar, skill'ler, hooks), hafıza.

Yazma güvenceleri: çakışma denetimi (taban özeti), atomik yazım, yazmadan önce yedek
(sd/kural_yedek/, dosya başına son 10), boyut sınırı, .json için geçerlilik denetimi, CRLF korunur.
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import re
import shutil
import time

import ork_lib as L

DOSYA_MAX = 512 * 1024
YEDEK_SAYISI = 10

GRUP_AD = {"proje": "Proje", "kullanici": "Kullanıcı (genel)", "eklenti": "Orkestra eklentisi", "hafiza": "Hafıza"}
GRUP_SIRA = ("proje", "eklenti", "kullanici", "hafiza")


def _kimlik(yol: str) -> str:
    return hashlib.sha1(os.path.normcase(os.path.abspath(yol)).encode("utf-8")).hexdigest()[:12]


def _hafiza_dizini(proje: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]", "-", os.path.abspath(proje))
    return os.path.join(os.path.expanduser("~"), ".claude", "projects", slug, "memory")


def _adaylar(proje: str) -> list[tuple[str, str, str]]:
    """(grup, görünen ad, yol) — beyaz liste; yalnız var olan dosyalar elenir üst katmanda."""
    c = os.path.join
    pc = c(proje, ".claude")
    out: list[tuple[str, str, str]] = []

    def ekle(grup, kok, desenler):
        for d in desenler:
            for y in sorted(glob.glob(c(kok, d), recursive=True)):
                out.append((grup, os.path.relpath(y, kok).replace("\\", "/"), y))

    ekle("proje", proje, ["CLAUDE.md", "CLAUDE.local.md", "AGENTS.md"])
    ekle("proje", proje, [".claude/rules/**/*.md", ".claude/agents/*.md", ".claude/commands/*.md",
                          ".claude/skills/*/SKILL.md", ".claude/settings.json", ".claude/settings.local.json"])
    ekle("eklenti", L.PLUGIN_ROOT, ["KURALLAR.md", "GELISTIRME.md", "kurallar/*.json", "agents/*.md", "skills/*/SKILL.md",
                                    "hooks/hooks.json"])
    h = os.path.join(os.path.expanduser("~"), ".claude")
    ekle("kullanici", h, ["CLAUDE.md", "settings.json"])
    hd = _hafiza_dizini(proje)
    if os.path.isdir(hd):
        ekle("hafiza", hd, ["*.md"])
    return out


def liste(proje: str) -> list[dict]:
    gorulen, out = set(), []
    for grup, ad, yol in _adaylar(proje):
        if not os.path.isfile(yol) or os.path.islink(yol):
            continue
        kimlik = _kimlik(yol)
        if kimlik in gorulen:
            continue
        gorulen.add(kimlik)
        try:
            st = os.stat(yol)
        except OSError:
            continue
        out.append({"id": kimlik, "grup": grup, "grup_ad": GRUP_AD[grup], "ad": ad, "boyut": st.st_size,
                    "degisim": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(st.st_mtime)),
                    "yazilabilir": st.st_size <= DOSYA_MAX and os.access(yol, os.W_OK)})
    out.sort(key=lambda d: (GRUP_SIRA.index(d["grup"]), d["ad"].lower()))
    return out


def _coz(proje: str, kimlik: str) -> tuple[dict, str]:
    for g, ad, yol in _adaylar(proje):
        if os.path.isfile(yol) and not os.path.islink(yol) and _kimlik(yol) == kimlik:
            return {"grup": g, "ad": ad}, yol
    raise LookupError("kural dosyası bulunamadı.")


def _ozet(ham: bytes) -> str:
    return hashlib.sha256(ham).hexdigest()


def oku(proje: str, kimlik: str) -> dict:
    meta, yol = _coz(proje, kimlik)
    boyut = os.path.getsize(yol)
    if boyut > DOSYA_MAX:
        raise ValueError(f"dosya çok büyük ({boyut // 1024} KB); en çok {DOSYA_MAX // 1024} KB açılır.")
    with open(yol, "rb") as f:
        ham = f.read()
    try:
        metin = ham.decode("utf-8-sig") if ham.startswith(b"\xef\xbb\xbf") else ham.decode("utf-8")
    except UnicodeDecodeError as e:
        raise ValueError("dosya UTF-8 değil; panelden açılmaz.") from e
    return {"id": kimlik, "grup": meta["grup"], "ad": meta["ad"], "yol": yol,
            "metin": metin.replace("\r\n", "\n"), "crlf": "\r\n" in metin, "taban": _ozet(ham)}


def _yedekle(sd: str, kimlik: str, yol: str) -> None:
    kok = os.path.join(sd, "kural_yedek")
    os.makedirs(kok, exist_ok=True)
    ek = os.path.splitext(yol)[1]
    shutil.copy2(yol, os.path.join(kok, f"{kimlik}_{time.strftime('%Y%m%d_%H%M%S')}{ek}"))
    eskiler = sorted(glob.glob(os.path.join(kok, f"{kimlik}_*")))
    for e in eskiler[:-YEDEK_SAYISI]:
        try:
            os.remove(e)
        except OSError:
            pass


def yaz(proje: str, sd: str, kimlik: str, metin: str, taban: str) -> dict:
    """Çakışma (taban uyuşmaz) → ValueError('cakisma: ...'); diğer geçersizlikler de ValueError."""
    if not isinstance(metin, str) or not isinstance(taban, str) or not taban:
        raise ValueError("metin ve taban metin olmalı.")
    if "\x00" in metin:
        raise ValueError("metinde geçersiz karakter var.")
    if len(metin.encode("utf-8")) > DOSYA_MAX:
        raise ValueError(f"metin çok büyük; en çok {DOSYA_MAX // 1024} KB.")
    meta, yol = _coz(proje, kimlik)
    with open(yol, "rb") as f:
        ham = f.read()
    if _ozet(ham) != taban:
        raise ValueError("cakisma: dosya sen açtıktan sonra başka yerde değişti. Yenile ve değişikliğini yeniden uygula.")
    if yol.lower().endswith(".json"):
        try:
            json.loads(metin)
        except ValueError as e:
            raise ValueError(f"geçerli JSON değil: {e}") from e
    crlf = b"\r\n" in ham
    govde = metin.replace("\r\n", "\n")
    if crlf:
        govde = govde.replace("\n", "\r\n")
    bom = ham.startswith(b"\xef\xbb\xbf")
    if bom:
        govde = "﻿" + govde
    if govde.encode("utf-8") == ham:
        return {"id": kimlik, "taban": taban, "degisti": False}
    _yedekle(sd, kimlik, yol)
    L.atomik_yaz(yol, govde)
    with open(yol, "rb") as f:
        yeni = _ozet(f.read())
    return {"id": kimlik, "taban": yeni, "degisti": True, "ad": meta["ad"]}
