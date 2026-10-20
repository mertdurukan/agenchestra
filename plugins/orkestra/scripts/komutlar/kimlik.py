"""orkestra komutları: kimlik (credentials; ADR-0008). Hiçbir komut değer yazmaz.

`orkestra kimlik kur`                       kök klasörü kurar, ACL'yi yalnız kullanıcıya sıkılaştırır
`orkestra kimlik liste`                     servisleri ve anahtar ADLARINI listeler
`orkestra kimlik var SERVIS [ANAHTAR]`      varlık denetimi (çıkış kodu 0/1)
`orkestra kimlik ekle SERVIS ANAHTAR`       değeri gizli sorar (getpass), dosyaya yazar
`orkestra kimlik calistir SERVIS -- KOMUT`  değişkenleri alt sürecin ortamına koyar, çıktıyı maskeler
`orkestra kimlik aktar KLASOR [--uygula]`   eski Keys\\*.env dosyalarını kopyalar (kaynağı silmez)
`orkestra kimlik denetle`                   klasör izninin gevşek olup olmadığını söyler
"""
from __future__ import annotations

from komutlar._ortak import hata


def _k():
    import kimlik as K
    return K


def _sar(f):
    K = _k()
    try:
        return f(K)
    except K.KimlikHata as e:
        hata(str(e))


def cmd_kur(a):
    def f(K):
        for s in K.kur(a.proje):
            print(s)
    _sar(f)


def cmd_liste(a):
    def f(K):
        for ust, servis, adlar in K.liste(a.proje):
            print(f"{ust}/{servis}: {', '.join(adlar) or '-'}")
        print(f"kök: {K.kok()}")
    _sar(f)


def cmd_var(a):
    def f(K):
        try:
            d = K.yukle(a.servis, a.proje)
        except K.KimlikHata:
            print("yok")
            raise SystemExit(1)
        if a.anahtar and a.anahtar not in d:
            print("yok")
            raise SystemExit(1)
        print("var")
    _sar(f)


def cmd_ekle(a):
    import getpass

    def f(K):
        v = getpass.getpass(f"{a.servis}.{a.anahtar} değeri (görünmez): ")
        K.ekle(a.servis, a.anahtar, v, a.proje, a.ortak)
        print(f"yazıldı: {a.servis}.{a.anahtar}")
    _sar(f)


def cmd_calistir(a):
    def f(K):
        komut = [x for x in a.komut if x != "--"]
        raise SystemExit(K.calistir(a.servis, komut, a.proje))
    _sar(f)


def cmd_aktar(a):
    def f(K):
        for servis, durum, adlar in K.aktar(a.klasor, a.proje, a.uygula):
            print(f"{servis}: {durum}; anahtarlar: {', '.join(adlar) or '-'}")
        if not a.uygula:
            print("(kuru çalışma; yazmak için --uygula)")
    _sar(f)


def cmd_denetle(a):
    def f(K):
        b = K.izin_gevsek_mi(K.kok())
        print("izin gevşek: " + ", ".join(b) if b else "izin sıkı")
        if b:
            raise SystemExit(1)
    _sar(f)


def kaydet(alt):
    p = alt.add_parser("kimlik", help="kimlik bilgisi klasörü (kullanıcı-düzeyi, proje bazlı .env; değer yazmaz)").add_subparsers(dest="alt", required=True)

    def ortak(x):
        x.add_argument("--proje", default=None, help="proje adı (varsayılan: git kökünün klasör adı)")
        return x
    ortak(p.add_parser("kur", help="kök klasörü kur, ACL sıkılaştır")).set_defaults(f=cmd_kur)
    ortak(p.add_parser("liste", help="servis ve anahtar adları")).set_defaults(f=cmd_liste)
    v = ortak(p.add_parser("var", help="servis/anahtar var mı (0/1)"))
    v.add_argument("servis")
    v.add_argument("anahtar", nargs="?")
    v.set_defaults(f=cmd_var)
    e = ortak(p.add_parser("ekle", help="değeri gizli sorup yaz"))
    e.add_argument("servis")
    e.add_argument("anahtar")
    e.add_argument("--ortak", action="store_true", help="_ortak kapsamına yaz")
    e.set_defaults(f=cmd_ekle)
    c = ortak(p.add_parser("calistir", help="komutu servis değişkenleriyle çalıştır (çıktı maskeli)"))
    c.add_argument("servis")
    c.add_argument("komut", nargs="+")
    c.set_defaults(f=cmd_calistir)
    t = ortak(p.add_parser("aktar", help="eski Keys klasöründen kopyala (kaynak silinmez)"))
    t.add_argument("klasor")
    t.add_argument("--uygula", action="store_true")
    t.set_defaults(f=cmd_aktar)
    p.add_parser("denetle", help="klasör izni gevşek mi").set_defaults(f=cmd_denetle)
