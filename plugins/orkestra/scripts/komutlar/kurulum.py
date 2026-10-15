"""orkestra komutları: kurulum (orkestra.py bölünmesinden)."""
from __future__ import annotations

import argparse
import collections
import csv
import datetime
import io
import json
import hashlib
import os
import re
import subprocess
import sys
import time

import ork_lib as L  # noqa: E402
import ret_nedeni as RN  # noqa: E402
from komutlar._ortak import README, hata  # noqa: E402


def cmd_baslat(a):
    sd = L.durum_dizini(olustur=True)
    rd = os.path.join(sd, "README.md")
    if not os.path.exists(rd):
        L.atomik_yaz(rd, README)
    print(sd)


def cmd_guncelle(a):
    pazar = "claude-orchestration"
    exe = L.claude_exe()
    if not exe:
        hata("claude.exe bulunamadı (CLAUDE_CODE_EXECPATH ya da %APPDATA%/Claude/claude-code/<sürüm>/*/claude.exe).")
    kaynak = L.pazar_kaynagi(pazar)
    if kaynak and os.path.isdir(os.path.join(kaynak, ".git")):
        # Yayın klonu: önce kaynağı ilerlet; kirliyse (elle düzenlenmiş) güncellemeyi reddet.
        g = ["git", "-C", kaynak]
        print("$ " + " ".join(g + ["status", "--porcelain"]))
        if not a.kuru:
            r = subprocess.run(g + ["status", "--porcelain"], capture_output=True, text=True, encoding="utf-8", errors="replace")
            if r.returncode != 0:
                hata(f"yayın klonu okunamadı ({kaynak}): {(r.stderr or r.stdout).strip()}")
            if r.stdout.strip():
                hata(f"yayın klonunda commitlenmemiş değişiklik var ({kaynak}); güncelleme reddedildi. Klon elle düzenlenmez: değişiklikleri geri al (git -C {kaynak} checkout -f .) ya da klonu yeniden kur (araclar/yayin_kur.py).")
        for k in (g + ["fetch", "-q", "origin"], g + ["merge", "--ff-only", "-q", "@{u}"]):
            print("$ " + " ".join(k))
            if a.kuru:
                continue
            r = subprocess.run(k, capture_output=True, text=True, encoding="utf-8", errors="replace")
            if r.returncode != 0:
                hata(f"yayın klonu ilerletilemedi ({' '.join(k[3:])}): {(r.stderr or r.stdout).strip()}")
    proje = L.proje_dizini()
    adlar = []
    try:
        with open(os.path.join(os.path.expanduser("~"), ".claude", "plugins", "installed_plugins.json"), encoding="utf-8") as f:
            for anahtar, girdiler in (json.load(f).get("plugins") or {}).items():
                ad, _, p = anahtar.partition("@")
                if p == pazar and any(os.path.normcase(os.path.abspath(g.get("projectPath") or "")) == os.path.normcase(proje)
                                      and g.get("scope") == "project" for g in girdiler):
                    adlar.append(ad)
    except Exception:
        pass
    if not adlar:
        hata(f"bu projede ({proje}) kurulu {pazar} plugin'i bulunamadı.")
    komutlar = [[exe, "plugin", "marketplace", "update", pazar]] + [[exe, "plugin", "update", f"{ad}@{pazar}", "--scope", "project"] for ad in adlar]
    for k in komutlar:
        print("$ " + " ".join(f'"{x}"' if " " in x else x for x in k))
        if a.kuru:
            continue
        r = subprocess.run(k, cwd=proje, capture_output=True, text=True, encoding="utf-8", errors="replace")
        cikti = (r.stdout + r.stderr).strip()
        if cikti:
            print("  " + cikti.replace(chr(10), chr(10) + "  "))
        if r.returncode != 0:
            hata(f"komut başarısız (çıkış {r.returncode}).")
    if not a.kuru:
        print("Tamam. Değişiklik yeni oturumda yüklenir: yeni oturum aç ya da /reload-plugins.")


def kaydet(alt):
    """Bu modülün alt komutlarını ana ayrıştırıcıya ekler."""
    alt.add_parser("baslat").set_defaults(f=cmd_baslat)

    gc = alt.add_parser("guncelle", help="plugin önbelleğini kaynak depodan yenile")
    gc.add_argument("--kuru", action="store_true", help="yalnız komutları yaz")
    gc.set_defaults(f=cmd_guncelle)
