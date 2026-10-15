"""orkestra komutları: _ortak (orkestra.py bölünmesinden)."""
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


BETIK_DIZINI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


BASAMAKLAR = ("T0", "T1", "T2", "T3", "T4")


def hata(mesaj: str, kod: int = 2):
    print(f"orkestra: {mesaj}", file=sys.stderr)
    sys.exit(kod)


def sd_gerekli() -> str:
    sd = L.durum_dizini()
    if not sd:
        hata("bu projede orkestra açık değil (`orkestra baslat`).")
    return sd


def oturum_id() -> str:
    return os.environ.get("CLAUDE_CODE_SESSION_ID") or os.environ.get("CLAUDE_SESSION_ID") or "-"


README = """# .claude/orkestra — çalışma zamanı durumu

Bu klasörü orkestra plugin'i yönetir; elle düzenleme yapma (hook'lar engeller).

| Dosya | Ne | Kim yazar |
|---|---|---|
| `gorevler/<id>.json` | Görev kartları: kabul kriteri, yazma alanı, bağımlılık, denetimler | `orkestra kart …` |
| `ortak_defter.md` / `.jsonl` | Herkes ne yaptığını yazar; yalnız sona ekleme | SubagentStop/Stop hook'ları + `orkestra defter ekle` |
| `maliyet.jsonl` | Her ajanın her süreç için token ve maliyet kaydı | SubagentStop/Stop hook'ları |
| `gunluk.jsonl` | İstekler (maskeli), skill/ajan kullanımı — skill avcısı okur | UserPromptSubmit/PostToolUse hook'ları |
| `perspektif/` | Hafıza bakım raporları | perspektif koşusu |
| `onerilen_skill/` | Skill avcısının taslakları (onayın gerekir) | skill-avcisi |
| `raporlar/` | `orkestra maliyet rapor` çıktıları | CLI |
"""
