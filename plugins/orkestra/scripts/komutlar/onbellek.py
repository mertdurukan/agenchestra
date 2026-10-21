"""orkestra komutları: onbellek (önbellek kaçaklarını sınıflar ve USD ile döker; model çağırmaz).

`orkestra onbellek kacak [--gun N] [--defter] [--olay] [--json]`
"""
from __future__ import annotations

import json

from komutlar._ortak import sd_gerekli


def cmd_kacak(a):
    import onbellek_kacak as OK
    sd = sd_gerekli()
    o = OK.ozet(sd, a.gun, yalniz_defter=a.defter)
    if a.json:
        print(json.dumps(o, ensure_ascii=False, indent=2))
        return
    pencere = f"son {a.gun:g} gün" if a.gun else "tüm kayıt"
    print(f"önbellek kaçakları ({pencere}): {o['olay_sayisi']} olay, ${o['usd']:.2f} yazma maliyeti")
    for s, v in o["siniflar"].items():
        print(f"  {s}: {v['olay']} olay, ${v['usd']:.2f}")
    print(f"son 24 saatte 5 dakikalık katman: {o['katman_5dk_son_24s']} çağrı")
    if a.olay:
        for e in sorted(o["olaylar"], key=lambda x: -x["usd"]):
            print(f"  {e['zaman'][:16]} {e['sinif']} oturum={e['oturum'][:8]} boşluk={e['bosluk_dk']}dk "
                  f"önceki={e['onceki_baglam'] // 1000}k yazma={e['yazma'] // 1000}k ${e['usd']:.2f} "
                  f"{e['model_once']}->{e['model']}")


def kaydet(alt):
    p = alt.add_parser("onbellek", help="önbellek kaçakları")
    s = p.add_subparsers(dest="alt")
    k = s.add_parser("kacak", help="kaçak olaylarını sınıfla (katman_5dk, model, bosluk, sikistirma, diger) ve USD ile dök")
    k.add_argument("--gun", type=float, help="son N takvim günü (boşsa tüm kayıt)")
    k.add_argument("--defter", action="store_true", help="yalnız maliyet defterinde kaydı olan oturumlar")
    k.add_argument("--olay", action="store_true", help="olay listesini de yaz (USD'ye göre azalan)")
    k.add_argument("--json", action="store_true")
    k.set_defaults(f=cmd_kacak)
