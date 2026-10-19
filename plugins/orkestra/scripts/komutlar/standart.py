"""orkestra komutları: standart (ekip yapı standartları kaydı, ADR-0006; model çağırmaz).

`orkestra standart liste`        kayıtlı standartları ve kaynağını (proje|eklenti) basar
`orkestra standart goster AD`    standardın içeriğini basar (proje dosyası eklentiyi ezer)
`orkestra standart yol AD`       standardın dosya yolunu basar
`orkestra standart ekle AD`      projede boş kalıp açar (var olanı ezmez)
"""
from __future__ import annotations

from komutlar._ortak import hata


def _sd():
    import ork_lib as L
    return L.durum_dizini()


def cmd_standart_liste(a):
    import standart as S
    for ad, kaynak, _y in S.liste(_sd()):
        print(f"{ad}\t{kaynak}")


def cmd_standart_goster(a):
    import standart as S
    m = S.oku(a.ad, _sd())
    if m is None:
        hata(f"standart yok: {a.ad} (`orkestra standart liste`)")
    print(m)


def cmd_standart_yol(a):
    import standart as S
    y = S.yol(a.ad, _sd())
    if not y:
        hata(f"standart yok: {a.ad}")
    print(y)


def cmd_standart_ekle(a):
    import standart as S
    sd = _sd()
    if not sd:
        hata("bu projede orkestra açık değil (`orkestra baslat`).")
    try:
        print(S.ekle(a.ad, sd))
    except ValueError as e:
        hata(str(e))


def kaydet(alt):
    p = alt.add_parser("standart", help="ekip yapı standartları: PR, commit, dal, review, Jira yorumu").add_subparsers(dest="alt", required=True)
    p.add_parser("liste", help="kayıtlı standartlar").set_defaults(f=cmd_standart_liste)
    g = p.add_parser("goster", help="standardın içeriğini basar")
    g.add_argument("ad")
    g.set_defaults(f=cmd_standart_goster)
    y = p.add_parser("yol", help="standardın dosya yolunu basar")
    y.add_argument("ad")
    y.set_defaults(f=cmd_standart_yol)
    e = p.add_parser("ekle", help="projede yeni standart kalıbı açar")
    e.add_argument("ad")
    e.set_defaults(f=cmd_standart_ekle)
