"""orkestra komutları: bekleme (ADR-0146). Model çağırmaz.

`orkestra bekleme ac "<ne>" --olay "<hangi olayla biter>" [--tahmin-s N] [--kaynak K] [--p N]`   bekleme kaydı açar,
                                  bağımsız todo maddelerini basar.
`orkestra bekleme kapat <id> [--yapilan N]`   kaydı kapatır; bekleme_kapat olayını (bekleme_s, bos_s, yapilan) yazar.
`orkestra bekleme liste`          açık kayıtlar.
`orkestra bekleme rapor`          bekleme olaylarının ölçümü (olay sayısı, bağımsız iş oranı, boş süre).
"""
from __future__ import annotations

import json
import os

import ork_lib as L
from komutlar._ortak import sd_gerekli


def _is_klasoru(sd: str, is_id: str) -> str | None:
    try:
        import is_kaydi
        for g in is_kaydi.is_liste(sd, "acik"):
            if str(g.get("id")) == str(is_id):
                return g.get("klasor")
    except Exception:
        pass
    return None


def _bagli_is(sd: str) -> str:
    oid = os.environ.get("CLAUDE_SESSION_ID") or ""
    for ad in (f"{oid}.json", f"is_{oid}.json"):
        try:
            with open(os.path.join(sd, "oturumlar", ad), encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict) and d.get("is"):
                return str(d["is"])
        except (OSError, ValueError):
            continue
    return ""


def cmd_ac(a):
    import bekleme_kaydi as BK
    sd = sd_gerekli()
    is_id = a.is_id or _bagli_is(sd)
    k = BK.ac(sd, a.ne, a.olay, a.tahmin_s, a.kaynak, is_id, a.p)
    klasor = _is_klasoru(sd, is_id) if is_id else None
    isler = BK.bagimsiz_isler(klasor, a.p) if klasor else []
    print(BK.baglam_satiri(k, isler))


def cmd_kapat(a):
    import bekleme_kaydi as BK
    s = BK.kapat(sd_gerekli(), a.id, a.yapilan)
    if not s:
        print(f"bekleme kaydı yok: {a.id}")
        return
    print(f"{a.id} kapandı: bekleme {s['bekleme_s']} sn, boş {s['bos_s']} sn, beklerken yapılan {s['yapilan']}")


def cmd_liste(a):
    import bekleme_kaydi as BK
    kayitlar = BK.liste(sd_gerekli())
    for k in kayitlar:
        print(f"{k['id']} {k['kaynak']}: {k['ne']} (biter: {k['olay']})")
    print(f"{len(kayitlar)} açık bekleme")


def cmd_rapor(a):
    import bekleme_kaydi as BK
    print(json.dumps(BK.rapor(sd_gerekli()), ensure_ascii=False, indent=2))


def kaydet(alt):
    p = alt.add_parser("bekleme", help="bekleme kaydı: beklerken bağımsız iş (ADR-0146)").add_subparsers(dest="alt", required=True)
    ac = p.add_parser("ac", help="bekleme kaydı aç ve bağımsız maddeleri listele")
    ac.add_argument("ne")
    ac.add_argument("--olay", required=True, help="bekleme hangi olayla biter")
    ac.add_argument("--tahmin-s", type=float, default=None, dest="tahmin_s")
    ac.add_argument("--kaynak", default="elle", help="kaynak_kira | arka_plan | ci | denetci | elle")
    ac.add_argument("--p", type=int, default=None, help="beklenen plan maddesi (P numarası)")
    ac.add_argument("--is", dest="is_id", default="")
    ac.set_defaults(f=cmd_ac)
    k = p.add_parser("kapat", help="kaydı kapat, ölçümü yaz")
    k.add_argument("id")
    k.add_argument("--yapilan", type=int, default=None)
    k.set_defaults(f=cmd_kapat)
    p.add_parser("liste", help="açık kayıtlar").set_defaults(f=cmd_liste)
    p.add_parser("rapor", help="ölçüm özeti").set_defaults(f=cmd_rapor)
