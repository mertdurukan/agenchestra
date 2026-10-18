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
import soru_sinif as SS  # noqa: E402
from komutlar._ortak import README, hata  # noqa: E402


def cmd_baslat(a):
    sd = L.durum_dizini(olustur=True)
    rd = os.path.join(sd, "README.md")
    if not os.path.exists(rd):
        L.atomik_yaz(rd, README)
    print(sd)
    print("Orkestra açıldı (çalışma zamanı dosyaları .git/info/exclude ile git dışında).")
    print("İş başlatmak için `/orkestra:is <istek>`.")
    print("Panel `/orkestra`, maliyet raporu `/orkestra:maliyet`.")


def cmd_guncelle(a):
    import guncelle as G  # noqa: E402
    kod = G.calistir(kuru=a.kuru)
    if kod:
        sys.exit(kod)


def kaydet(alt):
    """Bu modülün alt komutlarını ana ayrıştırıcıya ekler."""
    alt.add_parser("baslat").set_defaults(f=cmd_baslat)

    gc = alt.add_parser("update", aliases=["guncelle"], help="yayın klonunu GitHub'dan çek, kurulu plugin'leri kendi kapsamıyla güncelle (LLM'siz)")
    gc.add_argument("--kuru", action="store_true", help="yalnız komutları yaz, çalıştırma")
    gc.set_defaults(f=cmd_guncelle)
