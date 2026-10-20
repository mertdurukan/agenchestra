"""orkestra komutları: push-kapisi (ADR-0012).

`orkestra push-kapisi kur`            .git/hooks/pre-push yazar (var olan hook zincirlenir)
`orkestra push-kapisi kaldir`         kapıyı kaldırır, saklanan hook'u geri koyar
`orkestra push-kapisi durum`          kurulu mu, yasak yollar
`orkestra push-kapisi yol ekle YOL`   yasak yol ekler (.claude/orkestra/push_kapisi.json)
`orkestra push-kapisi kontrol UZAK`   hook'un içeriden çağırdığı denetim (stdin: pre-push satırları)
"""
from __future__ import annotations

import sys

from komutlar._ortak import hata


def _p():
    import push_kapisi as P
    return P


def _sar(f):
    P = _p()
    try:
        return f(P)
    except P.KapiHata as e:
        hata(str(e))


def _yaz(satirlar):
    for s in satirlar:
        print(s)


def cmd_kur(a):
    _sar(lambda P: _yaz(P.kur()))


def cmd_kaldir(a):
    _sar(lambda P: _yaz(P.kaldir()))


def cmd_durum(a):
    _sar(lambda P: _yaz(P.durum()))


def cmd_yol_ekle(a):
    _sar(lambda P: _yaz(["yasak yollar: " + ", ".join(P.yol_ekle(P.git_koku(), a.yol.strip("/\\")))]))


def cmd_kontrol(a):
    P = _p()
    girdi = sys.stdin.read()
    try:
        raise SystemExit(P.kontrol(a.uzak, girdi))
    except P.KapiHata as e:
        hata(str(e))


def kaydet(alt):
    p = alt.add_parser("push-kapisi", help="yasak yola dokunan commit uzak depoya gitmez (pre-push kapısı)").add_subparsers(dest="alt", required=True)
    p.add_parser("kur", help="pre-push kapısını kur").set_defaults(f=cmd_kur)
    p.add_parser("kaldir", help="kapıyı kaldır").set_defaults(f=cmd_kaldir)
    p.add_parser("durum", help="kurulu mu, yasak yollar").set_defaults(f=cmd_durum)
    y = p.add_parser("yol", help="yasak yol yönetimi").add_subparsers(dest="yol_alt", required=True)
    e = y.add_parser("ekle", help="yasak yol ekle")
    e.add_argument("yol")
    e.set_defaults(f=cmd_yol_ekle)
    k = p.add_parser("kontrol", help="(hook içi) stdin'deki gönderim satırlarını denetle")
    k.add_argument("uzak", nargs="?", default="")
    k.add_argument("adres", nargs="?", default="")
    k.set_defaults(f=cmd_kontrol)
