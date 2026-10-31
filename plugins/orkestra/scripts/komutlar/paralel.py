"""orkestra komutları: paralel (bağımsız komutları paralel koşar; P-041, ADR-0100).

`orkestra paralel [-n N] [--zaman-asimi SN] [--ilk-hatada-dur] -- "komut1" "komut2" ...`
"""
from __future__ import annotations

import sys


def cmd_paralel(a):
    import paralel_calistir
    argv = list(a.komutlar)
    if a.n is not None:
        argv = ["-n", str(a.n)] + argv
    argv = ["--zaman-asimi", str(a.zaman_asimi)] + argv
    if a.ilk_hatada_dur:
        argv = ["--ilk-hatada-dur"] + argv
    sys.exit(paralel_calistir.main(argv))


def kaydet(alt):
    p = alt.add_parser("paralel", help="bağımsız komutları (lint, derleme, doğrulama, test) paralel koşar")
    p.add_argument("-n", type=int, default=None, help="genişlik (varsayılan: otomatik)")
    p.add_argument("--zaman-asimi", type=float, default=900.0, help="komut başına saniye")
    p.add_argument("--ilk-hatada-dur", action="store_true", help="biri düşünce başlamamış işleri iptal et")
    p.add_argument("komutlar", nargs="+", help="paralel koşacak komutlar (-- sonrası)")
    p.set_defaults(f=cmd_paralel)
