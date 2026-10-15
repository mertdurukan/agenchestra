"""orkestra komutları: defter (orkestra.py bölünmesinden)."""
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
import soru_sinif as SS  # noqa: E402
from komutlar._ortak import hata, sd_gerekli  # noqa: E402
from komutlar.kart import _kart_al, _kim  # noqa: E402


def cmd_defter_ekle(a):
    sd = sd_gerekli()
    ajan_id, ajan_tipi = _kim(a)
    if a.surec not in L.SURECLER:
        hata(f"süreç şunlardan biri olmalı: {', '.join(L.SURECLER)}")
    L.defter_ekle(sd, {"gorev": a.gid, "surec": a.surec, "ajan": ajan_tipi, "agent_id": None if ajan_id in ("ana", "bilinmiyor") else ajan_id,
                       "model": "-", "yaptim": a.yaptim, "sonuc": a.sonuc, "not": a.not_, "kaynak": "ajan"})
    print("eklendi")


def _blok_metni(r: dict) -> str:
    return L.defter_blogu(r).strip()


def cmd_defter_baglam(a):
    sd = sd_gerekli()
    k = _kart_al(sd, a.gid)
    ilgili = set(k["bagimliliklar"]) | {a.gid}
    parcalar = [f"# Bağlam: {a.gid} — {k['baslik']}",
                f"Basamak {k['basamak']} · durum {L.kart_durumu_hesapla(k)}",
                "Kabul kriterleri:\n" + "\n".join(f"  {i+1}. {c}" for i, c in enumerate(k["kabul_kriterleri"])),
                "Yazma alanı: " + (", ".join(k["yazma_alani"]) or "(sınırsız)")]
    if k.get("girdi"):
        parcalar.append("Girdi: " + k["girdi"])
    son_ret = [d for d in k["denetimler"] if d["karar"] == "ret"][-1:]
    if son_ret:
        parcalar.append("SON RET — düzeltme talimatı: " + (son_ret[0].get("talimat") or son_ret[0].get("gerekce")))
    for b in k["bagimliliklar"]:
        bk = L.kart_oku(sd, b)
        if bk:
            parcalar.append(f"Bağımlılık {b} ({L.kart_durumu_hesapla(bk)}): çıktılar {', '.join(bk.get('ciktilar') or []) or '-'}"
                            + (f"\n  özet: {bk.get('son_ozet', '')[:400]}" if bk.get("son_ozet") else ""))
    kayitlar = [r for r in L.defter_kayitlari(sd) if r.get("gorev") in ilgili]
    metin = "\n".join(parcalar) + "\n\n# İlgili defter kayıtları (en yeni sonda)\n"
    bloklar = [_blok_metni(r) for r in kayitlar]
    secili = []
    toplam = len(metin)
    for b in reversed(bloklar):
        if toplam + len(b) > a.max:
            break
        secili.insert(0, b)
        toplam += len(b) + 2
    if len(secili) < len(bloklar):
        metin += f"(… {len(bloklar) - len(secili)} eski kayıt atlandı: `orkestra defter oku --gorev {a.gid}`)\n"
    print(metin + "\n\n".join(secili))


def cmd_defter_oku(a):
    sd = sd_gerekli()
    kayitlar = L.defter_kayitlari(sd)
    if a.gorev:
        kayitlar = [r for r in kayitlar if r.get("gorev") == a.gorev]
    for r in kayitlar[-a.son:]:
        print(_blok_metni(r) + "\n")


def cmd_defter_ozet(a):
    sd = sd_gerekli()
    son = {}
    for r in L.defter_kayitlari(sd):
        son[r.get("gorev", "-")] = r
    for g, r in son.items():
        print(f"{g:8s} {r.get('zaman', '')[:16]} {r.get('surec', '-'):10s} {r.get('ajan', '-'):24s} {str(r.get('sonuc') or r.get('yaptim') or '')[:80]}")


def kaydet(alt):
    """Bu modülün alt komutlarını ana ayrıştırıcıya ekler."""
    defter = alt.add_parser("defter").add_subparsers(dest="alt", required=True)
    e = defter.add_parser("ekle")
    e.add_argument("gid")
    e.add_argument("--surec", required=True)
    e.add_argument("--yaptim")
    e.add_argument("--sonuc")
    e.add_argument("--not", dest="not_")
    e.set_defaults(f=cmd_defter_ekle)
    b = defter.add_parser("baglam")
    b.add_argument("gid")
    b.add_argument("--max", type=int, default=2000)
    b.set_defaults(f=cmd_defter_baglam)
    o = defter.add_parser("oku")
    o.add_argument("--gorev")
    o.add_argument("--son", type=int, default=10)
    o.set_defaults(f=cmd_defter_oku)
    defter.add_parser("ozet").set_defaults(f=cmd_defter_ozet)
