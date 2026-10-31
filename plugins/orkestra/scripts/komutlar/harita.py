"""orkestra komutları: harita (proje sistem haritası; model çağırmaz, ADR-0005).

`orkestra harita yenile [--katman K]... [--zorla]`  eskimiş (ya da --zorla ile tüm) katmanları baştan tarar
`orkestra harita oku [KATMAN]`                        kayıtları basar; eskimiş katmanı önce yeniler
`orkestra harita denetle`                             eskimiş katman sayısını basar (yazmaz)
"""
from __future__ import annotations

from komutlar._ortak import hata, sd_gerekli


def _kok(sd):
    import ork_lib as L
    return L.proje_dizini()


def cmd_harita_yenile(a):
    import harita as H
    sd = sd_gerekli()
    kat = a.katman or None
    for k in kat or ():
        if k not in H.KATMANLAR:
            hata(f"bilinmeyen katman: {k} (geçerli: {', '.join(H.KATMANLAR)})")
    s = H.yenile(_kok(sd), sd, katmanlar=kat, zorla=a.zorla)
    print(f"harita güncellendi: yenilenen {len(s['yenilenen'])} ({', '.join(s['yenilenen']) or '-'}), atlanan {len(s['atlanan'])}")


def cmd_harita_oku(a):
    import harita as H
    sd = sd_gerekli()
    if a.katman and a.katman not in H.KATMANLAR:
        hata(f"bilinmeyen katman: {a.katman} (geçerli: {', '.join(H.KATMANLAR)})")
    kayitlar = H.oku(_kok(sd), sd, a.katman)
    for r in kayitlar:
        isaret = "" if r["durum"] == "dogrulandi" else " [doğrulanamadı]"
        print(f"{r['id']}: {r['rol']}{isaret} <- {', '.join(r['yer'][:3])}{' …' if len(r['yer']) > 3 else ''}")
    print(f"{len(kayitlar)} kayıt")


def cmd_harita_denetle(a):
    import harita as H
    sd = sd_gerekli()
    d = H.denetle(_kok(sd), sd)
    print(f"eskimiş: {len(d['eskimis'])}" + (f" ({', '.join(d['eskimis'])})" if d["eskimis"] else ""))


def cmd_harita_istek(a):
    import harita as H
    import harita_istek as HI
    sd = sd_gerekli()
    graf = os.path.join(H.klasor_yolu(sd), HI.GRAF_DIZINI)
    print(HI.metin(HI.etki(a.metin, graf)))


def kaydet(alt):
    p = alt.add_parser("harita", help="proje sistem haritası: yapılandırma, süreç, altyapı kayıtlarını betikle üretir ve günceller").add_subparsers(dest="alt", required=True)
    y = p.add_parser("yenile", help="eskimiş katmanları baştan tarayıp yeniden yazar")
    y.add_argument("--katman", action="append", default=[], metavar="K", help="yalnız bu katman (tekrarlanabilir)")
    y.add_argument("--zorla", action="store_true", help="eskimemiş olsa da yeniden tara")
    y.set_defaults(f=cmd_harita_yenile)
    o = p.add_parser("oku", help="kayıtları basar; eskimiş katmanı önce yeniler")
    o.add_argument("katman", nargs="?", default=None)
    o.set_defaults(f=cmd_harita_oku)
    d = p.add_parser("denetle", help="eskimiş katman sayısını basar (dosya yazmaz)")
    d.set_defaults(f=cmd_harita_denetle)
