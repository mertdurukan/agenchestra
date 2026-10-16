"""orkestra komutları: sağlık (doktor)."""
from __future__ import annotations

import sys

import doktor  # noqa: E402


def cmd_doktor(a):
    kod = doktor.calistir(a)
    if kod:
        sys.exit(kod)


def kaydet(alt):
    """Bu modülün alt komutlarını ana ayrıştırıcıya ekler."""
    d = alt.add_parser("doktor", help="ilk çalıştırma sağlık denetimi ve güvenli onarım (A otomatik, B --evet, C rehber)")
    doktor.argumanlar(d)
    d.set_defaults(f=cmd_doktor)
