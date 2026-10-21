"""orkestra komutları: isabet (kapanmış işlerde anılan dosyalar ile değişen dosyaların kesinlik/duyarlılık ölçümü; model çağırmaz).

`orkestra isabet [I-nnn ...] [--son 20] [--kok DİZİN]... [--on-baglam] [--json]`
"""
from __future__ import annotations

import json

from komutlar._ortak import hata, sd_gerekli


def cmd_isabet(a):
    import belge_ara as BA
    import is_kaydi
    import isabet as IS
    sd = sd_gerekli()
    proje = BA.proje_kok(sd)
    kokler = [proje] + [k for k in a.kok or []]
    git_koklari = IS.git_kokleri(kokler)
    if not git_koklari:
        hata("git deposu bulunamadı; --kok ile bir git dizini ver.")
    tahmin = None
    if a.on_baglam:
        import on_baglam as OB
        tahmin = lambda kayit: OB.yollar(kayit.get("baslik") or "", kokler, sd, kayit.get("klasor"), kayit.get("id"))  # noqa: E731
    kayitlar = is_kaydi.is_liste(sd, "kapandi")
    if a.isler:
        secili = {i.upper() for i in a.isler}
        kayitlar = [k for k in kayitlar if k["id"] in secili]
    else:
        kayitlar = sorted(kayitlar, key=lambda k: is_kaydi.is_no(k["id"]))[-a.son:]
    satirlar = []
    for g in kayitlar:
        kayit = is_kaydi.is_al(sd, g["id"]) or g
        kayit = dict(kayit, id=g["id"])
        s = IS.olc(kayit, git_koklari, kokler, tahmin)
        if s:
            satirlar.append(s)
    t = IS.toplam(satirlar)
    if a.json:
        print(json.dumps({"isler": satirlar, "toplam": t}, ensure_ascii=False, indent=2))
    else:
        print(IS.biclem(satirlar, t))
    return 0


def kaydet(alt):
    p = alt.add_parser("isabet", help="kapanmış işlerde anılan dosyalar ile değişen dosyaların kesinlik ve duyarlılığını ölç")
    p.add_argument("isler", nargs="*", help="iş kimlikleri (boşsa son kapananlar)")
    p.add_argument("--son", type=int, default=20, help="kimlik verilmezse son kaç kapanmış iş (varsayılan 20)")
    p.add_argument("--kok", action="append", help="ek git/çalışma dizini (iş başka depoyu değiştirdiyse)")
    p.add_argument("--on-baglam", action="store_true", dest="on_baglam", help="anılan yerine ön bağlam hook'unun önereceği yolları ölç")
    p.add_argument("--json", action="store_true")
    p.set_defaults(f=cmd_isabet)
