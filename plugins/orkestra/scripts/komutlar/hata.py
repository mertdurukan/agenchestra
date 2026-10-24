"""orkestra komutları: hata (ADR-0035). Salt okur.

`orkestra hata en-cok [--gun N] [--kaynak hook|cli|ozet|kart|kural | --tum] [--ilk N] [--json]`
Varsayılan görünüm kural ihlallerini dışlar (uyum sayacı, hata değil); `--kaynak kural` ya da `--tum` ile görünür.
`orkestra hata liste [--ilk N] [--json]`   (hata.jsonl'in son satırları)
"""
from __future__ import annotations

import json
import os

import ork_lib as L  # noqa: E402
from komutlar._ortak import sd_gerekli  # noqa: E402


def cmd_en_cok(a):
    import hata_en_cok as HE
    satirlar = HE.birlestir(sd_gerekli(), a.gun, a.kaynak, kural_haric=not a.tum)
    if a.ilk:
        satirlar = satirlar[:a.ilk]
    if a.json:
        print(json.dumps(satirlar, ensure_ascii=False, indent=1))
        return
    if not satirlar:
        print("hata kaydı yok")
    for r in satirlar:
        print(HE.satir_metni(r))
    if not a.tum and not a.kaynak:
        print("(kural ihlalleri dışarıda: --kaynak kural ya da --tum)")


def cmd_liste(a):
    import hata_kayit as HK
    satirlar = [r for r in L.jsonl_oku(os.path.join(sd_gerekli(), HK.DOSYA)) if isinstance(r, dict)]
    satirlar = satirlar[-a.ilk:] if a.ilk else satirlar
    if a.json:
        print(json.dumps(satirlar, ensure_ascii=False, indent=1))
        return
    if not satirlar:
        print("hata.jsonl boş")
    for r in satirlar:
        print(f"{str(r.get('zaman', ''))[:19].replace('T', ' ')}  [{r.get('kaynak')}] {r.get('imza')}")


def cmd_ozet(a):
    import ret_olcum as RO
    o = RO.ozet(RO.yukle(sd_gerekli()), baslangic=a.baslangic, oncesi=a.oncesi, sonrasi=a.sonrasi, bitis=a.bitis)
    if a.json:
        print(json.dumps(o, ensure_ascii=False, indent=1))
        return
    for s in RO.metin(o):
        print(s)


def kaydet(alt):
    """Bu modülün alt komutlarını ana ayrıştırıcıya ekler."""
    h = alt.add_parser("hata", help="tekrar eden hatalar (hook, CLI, özet, kart reti, kural ihlali)").add_subparsers(dest="alt", required=True)
    e = h.add_parser("en-cok", help="aynı imzalı hataları sayıya göre sıralar (salt okuma)")
    e.add_argument("--gun", type=int, default=0, help="son N gün (0 = tümü)")
    g = e.add_mutually_exclusive_group()
    g.add_argument("--kaynak", choices=("hook", "cli", "ozet", "kart", "kural", "davranis"))
    g.add_argument("--tum", action="store_true", help="kural ihlalleri dahil tüm kaynaklar")
    e.add_argument("--ilk", type=int, default=0, help="ilk N satır (0 = tümü)")
    e.add_argument("--json", action="store_true")
    e.set_defaults(f=cmd_en_cok)
    li = h.add_parser("liste", help="hata.jsonl'in son satırları")
    li.add_argument("--ilk", type=int, default=20, help="son N satır (0 = tümü)")
    li.add_argument("--json", action="store_true")
    li.set_defaults(f=cmd_liste)
    oz = h.add_parser("ozet", help="R1–R9 ret/100 tur, Garwood üst sınırı, önce/sonra kararı (salt okuma)")
    oz.add_argument("--baslangic", help="pencere başı (YYYY-MM-DD ya da ISO zaman; yoksa başından)")
    oz.add_argument("--bitis", help="pencere sonu (yoksa şimdi)")
    oz.add_argument("--oncesi", help="öncesi penceresinin sonu (karşılaştırma)")
    oz.add_argument("--sonrasi", help="sonrası penceresinin başı (karşılaştırma; yoksa --oncesi)")
    oz.add_argument("--json", action="store_true")
    oz.set_defaults(f=cmd_ozet)
