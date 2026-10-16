"""orkestra komutları: teknik (kart teknik detayı; salt okuma, yalnız `md --yaz` iş klasörüne yazar)."""
from __future__ import annotations

import json

from komutlar._ortak import hata, sd_gerekli


def cmd_teknik_goster(a):
    import teknik
    sd = sd_gerekli()
    d = teknik.derle(sd, a.kart)
    if "hata" in d:
        hata(d["hata"], 1)
    if a.json:
        print(json.dumps(d, ensure_ascii=False, indent=2))
    else:
        print(teknik.kart_md(a.kart, d["ne"].get("baslik"), d))


def cmd_teknik_md(a):
    import teknik
    sd = sd_gerekli()
    try:
        metin, yol = teknik.md(sd, a.is_id, yaz=a.yaz)
    except ValueError as e:
        hata(str(e), 1)
    print(yol if yol else metin)


def kaydet(alt):
    t = alt.add_parser("teknik", help="kartın teknik detayı (betikle derlenir, LLM'siz)").add_subparsers(dest="alt", required=True)
    g = t.add_parser("goster", help="kartın 7 blokluk teknik detayı")
    g.add_argument("kart")
    g.add_argument("--json", action="store_true")
    g.set_defaults(f=cmd_teknik_goster)
    m = t.add_parser("md", help="işin kartları oluşturma sırasıyla markdown")
    m.add_argument("is_id")
    m.add_argument("--yaz", action="store_true", help="iş klasörüne teknik_detay.md yazar")
    m.set_defaults(f=cmd_teknik_md)
