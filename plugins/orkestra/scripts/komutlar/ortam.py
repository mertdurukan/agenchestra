"""orkestra komutları: ortam (codebase ortamları; I-249, ADR-0001). Model çağırmaz, bağlantı kurmaz.

`orkestra ortam liste`                          codebase'leri, kilit türünü, ortam yolunu ve kurulum durumunu basar
`orkestra ortam kur [CODEBASE]`                 manifest + kilitten ortamı kurar (verilmezse tümü)
`orkestra ortam dogrula [CODEBASE]`             kilit damgasını güncel kilitle karşılaştırır (yok | eski | guncel)
`orkestra ortam calistir CODEBASE [--kimlik S] -- KOMUT`  komutu ortamdan koşturur
`orkestra ortam veri`                           veri kaynağı profilleri (salt okunur; kimlik kaydı adı, kapı)
"""
from __future__ import annotations

from komutlar._ortak import hata, sd_gerekli


def _kok(sd):
    import ork_lib as L
    return L.proje_dizini()


def _secili(a, sd):
    import ortam as O
    kok = _kok(sd)
    try:
        if a.codebase:
            return kok, [O.bul(kok, sd, a.codebase)]
    except O.OrtamHata as e:
        hata(str(e))
    k = O.kayitlar(kok, sd)
    return kok, [k[y] for y in sorted(k)]


def cmd_liste(a):
    import ortam as O
    sd = sd_gerekli()
    kok, kayitlar = _secili(a, sd)
    for r in kayitlar:
        print(f"{r['ad']}: {r['tur']}, kilit {r['kilit_turu']}, {O.dogrula(r, kok)['durum']} <- {r['ortam_yolu']}")
    print(f"{len(kayitlar)} codebase")


def cmd_kur(a):
    import ortam as O
    sd = sd_gerekli()
    kok, kayitlar = _secili(a, sd)
    basarisiz = 0
    for r in kayitlar:
        try:
            s = O.kur(r, kok)
            print(f"{s['codebase']}: {s['durum']} ({s['arac']}) -> {s['ortam_yolu']}")
        except O.OrtamHata as e:
            basarisiz += 1
            print(f"HATA {e}")
    if basarisiz:
        raise SystemExit(1)


def cmd_dogrula(a):
    import ortam as O
    sd = sd_gerekli()
    kok, kayitlar = _secili(a, sd)
    kotu = 0
    for r in kayitlar:
        d = O.dogrula(r, kok)
        kotu += d["durum"] != "guncel"
        print(f"{d['codebase']}: {d['durum']}")
    if kotu:
        raise SystemExit(1)


def cmd_calistir(a):
    import ortam as O
    import ortam_calistir as C
    sd = sd_gerekli()
    kok = _kok(sd)
    try:
        kayit = O.bul(kok, sd, a.codebase)
        raise SystemExit(C.calistir(kayit, kok, [x for x in a.komut if x != "--"], a.kimlik))
    except O.OrtamHata as e:
        hata(str(e))


def cmd_veri(a):
    import harita_ortam as HO
    import ortam_db as D
    sd = sd_gerekli()
    try:
        for ad, p in D.profiller(HO.ayar_oku(sd)).items():
            c = D.coz(p)
            print(f"{ad}: {p['tur']}, salt okunur, kimlik {p['kimlik']} ({c['kimlik_durumu']}), kapı {p['kapi'] or '-'}")
    except D.ProfilHata as e:
        hata(str(e))


def kaydet(alt):
    p = alt.add_parser("ortam", help="codebase ortamları: manifestten kilitli ortam kur, doğrula, komutu ortamdan koştur").add_subparsers(dest="alt", required=True)
    p.add_parser("liste", help="codebase'ler ve ortam durumu").set_defaults(f=cmd_liste, codebase=None)
    for ad, f, yardim in (("kur", cmd_kur, "ortamı kur (verilmezse tüm codebase'ler)"),
                          ("dogrula", cmd_dogrula, "kilit damgasını doğrula")):
        x = p.add_parser(ad, help=yardim)
        x.add_argument("codebase", nargs="?", default=None)
        x.set_defaults(f=f)
    c = p.add_parser("calistir", help="komutu codebase ortamından koştur")
    c.add_argument("codebase")
    c.add_argument("--kimlik", default=None, metavar="SERVIS", help="orkestra kimlik servisi (değerler maskelenir)")
    c.add_argument("komut", nargs="+")
    c.set_defaults(f=cmd_calistir)
    p.add_parser("veri", help="veri kaynağı profilleri (salt okunur; bağlantı kurulmaz)").set_defaults(f=cmd_veri)
