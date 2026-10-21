"""orkestra komutları: ara (iş klasörü, ADR ve kural metni araması; model çağırmaz).

`orkestra ara "<sorgu>" [--json] [--n 10]`
"""
from __future__ import annotations

import json

from komutlar._ortak import sd_gerekli


def cmd_ara(a):
    import belge_ara as BA
    sd = sd_gerekli()
    sonuc = BA.ara(BA.belgeler(BA.proje_kok(sd), sd), a.sorgu, a.n)
    if a.json:
        print(json.dumps(sonuc, ensure_ascii=False, indent=2))
    else:
        print(BA.biclem(sonuc))
    return 0


def kaydet(alt):
    p = alt.add_parser("ara", help="iş klasörü, ADR ve kural metninde ara (TF-IDF; model çağırmaz)")
    p.add_argument("sorgu", help="aranacak sözcükler")
    p.add_argument("--n", type=int, default=10, help="en çok kaç sonuç (varsayılan 10)")
    p.add_argument("--json", action="store_true")
    p.set_defaults(f=cmd_ara)
