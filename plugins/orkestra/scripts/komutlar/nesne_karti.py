"""orkestra komutları: nesne-karti (ADR-0177; model çağırmaz).

`orkestra nesne-karti dogrula KART [--dokum DOSYA] [--json]`
    Kart dosyasındaki iddiaların derece, kaynak hiyerarşisi ve kaynakça biçimini denetler. `--dokum` verilirse KESİN
    iddiaların kaynak komutu ya da yolu dökümde tam eşleşmeyle aranır. Çıkış 0: bulgu yok, 1: bulgu var, 2: dosya yok.
"""
from __future__ import annotations

import json
import os
import sys

from komutlar._ortak import hata


def _oku(yol: str, ad: str) -> str:
    if not os.path.isfile(yol):
        hata(f"{ad} dosyası yok: {yol}")
    with open(yol, encoding="utf-8") as f:
        return f.read()


def cmd_dogrula(a):
    import nesne_karti as NK
    import ork_lib as L
    metin = _oku(a.kart, "kart")
    dokum = _oku(a.dokum, "döküm") if a.dokum else None
    bulgu = NK.dogrula(metin, NK.ayar_oku(L.durum_dizini()), dokum)
    if a.json:
        print(json.dumps({"sayi": len(bulgu), "bulgular": bulgu}, ensure_ascii=False, indent=2))
    else:
        for b in bulgu:
            print(f"{b['tur']}\tsatir={b['satir']}\t{b['ayrinti']}")
        print(f"bulgu={len(bulgu)}")
    if bulgu:
        sys.exit(1)
    return 0


def kaydet(alt):
    p = alt.add_parser("nesne-karti", help="nesne kartı doğrulayıcısı (ADR-0177): derece, kaynak hiyerarşisi, kaynakça")
    s = p.add_subparsers(dest="alt", required=True)
    d = s.add_parser("dogrula", help="kart dosyasını denetle (çıkış 0 temiz, 1 bulgu, 2 dosya yok)")
    d.add_argument("kart", help="kart dosyası (md)")
    d.add_argument("--dokum", help="ham çıktı dökümü; KESİN kaynakların komutu ya da yolu burada tam geçmeli")
    d.add_argument("--json", action="store_true")
    d.set_defaults(f=cmd_dogrula)
