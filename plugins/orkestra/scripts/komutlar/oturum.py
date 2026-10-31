"""orkestra komutları: oturum (oturumlar arası farkındalık ve not; ADR-0125). Model çağırmaz.

`orkestra oturum liste [--json]`        bu projede canlı oturumlar (depo, dal, çalışma ağacı, iş, kaç dk önce)
`orkestra oturum not HEDEF "metin"`     hedef oturumun gelen kutusuna not bırakır (HEDEF: kimlik öneki, ≥4 karakter)
`orkestra oturum oku`                   bu oturumun okunmamış notları
`orkestra oturum rapor [--gun N]`       çakışma tespitleri (gölge günlük) ve hook gecikmesi

Not VERİDİR: alan oturum onu talimat saymaz, izin yükseltmez. Sır kalıbı içeren not reddedilir.
"""
from __future__ import annotations

import json
import os
import sys
import time

from komutlar._ortak import sd_gerekli


def _benim() -> str | None:
    return os.environ.get("CLAUDE_CODE_SESSION_ID") or os.environ.get("CLAUDE_SESSION_ID")


def cmd_liste(a):
    import oturum_farkindalik as F
    sd = sd_gerekli()
    t = time.time()
    satirlar = []
    for e in os.scandir(os.path.join(sd, "oturumlar")):
        if not e.name.endswith(".json") or ".baglanti" in e.name or e.name.startswith("acik_ajan_"):
            continue
        try:
            if t - e.stat().st_mtime > F.CANLI_S:
                continue
            with open(e.path, encoding="utf-8") as f:
                k = (json.load(f) or {}).get("konum")
        except (OSError, ValueError, AttributeError):
            continue
        if isinstance(k, dict) and t - float(k.get("gorulme") or 0) <= F.CANLI_S:
            satirlar.append({"oturum": e.name[:-5][:8], "dal": k.get("dal"), "worktree": k.get("worktree"), "is": k.get("is"),
                             "dk": int((t - float(k.get("gorulme") or 0)) // 60), "ben": e.name[:-5] == _benim()})
    satirlar.sort(key=lambda r: r["dk"])
    if a.json:
        print(json.dumps(satirlar, ensure_ascii=False, indent=2))
        return
    for r in satirlar:
        print(f"{r['oturum']}{' (ben)' if r['ben'] else ''}\t{r['dal']}\t{r['is'] or '-'}\t{r['dk']} dk\t{r['worktree']}")
    print(f"{len(satirlar)} canlı oturum")


def cmd_not(a):
    import oturum_farkindalik as F
    sd = sd_gerekli()
    hedef, hata = F.hedef_coz(sd, a.hedef)
    if not hedef:
        sys.exit(f"oturum not: {hata}")
    ok, hata = F.not_birak(sd, hedef, _benim() or "-", a.metin)
    if not ok:
        sys.exit(f"oturum not: {hata}")
    print(f"not bırakıldı: {hedef[:8]} (sonraki araç çağrısında görür)")


def cmd_oku(a):
    import oturum_farkindalik as F
    sd = sd_gerekli()
    benim = _benim()
    if not benim:
        sys.exit("oturum oku: oturum kimliği yok (CLAUDE_CODE_SESSION_ID)")
    n = F.gelen_oku(sd, benim)
    for x in n:
        print(f"[{x.get('kimden', '-')}] {x.get('zaman', '')} {x['metin']}")
    if not n:
        print("okunmamış not yok")


def cmd_rapor(a):
    import oturum_olcum as O
    sd = sd_gerekli()
    if a.sinifla:
        zaman, _, sonuc = a.sinifla.partition("=")
        if sonuc not in ("dogru", "yanlis"):
            sys.exit("oturum rapor: --sinifla ZAMAN=dogru|yanlis")
        O.sinifla(sd, zaman, sonuc)
        print("sınıflandı")
        return
    print(json.dumps(O.rapor(sd, a.gun, a.gecikme), ensure_ascii=False, indent=2))


def kaydet(alt):
    p = alt.add_parser("oturum", help="oturumlar arası farkındalık: canlı oturumlar, not bırak/oku, ölçüm").add_subparsers(
        dest="alt", required=True)
    d = p.add_parser("liste", help="bu projede canlı oturumlar")
    d.add_argument("--json", action="store_true")
    d.set_defaults(f=cmd_liste)
    n = p.add_parser("not", help="hedef oturumun gelen kutusuna not bırak (veri, talimat değil)")
    n.add_argument("hedef")
    n.add_argument("metin")
    n.set_defaults(f=cmd_not)
    o = p.add_parser("oku", help="bu oturumun okunmamış notları")
    o.set_defaults(f=cmd_oku)
    r = p.add_parser("rapor", help="çakışma tespitleri ve gecikme ölçümü (gölge günlük)")
    r.add_argument("--gun", type=int, default=7)
    r.add_argument("--gecikme", type=int, default=0, help="N çağrılık hook ek süresi ölçümü (ör. 1000)")
    r.add_argument("--sinifla", metavar="ZAMAN=dogru|yanlis", help="bir tespiti elle sınıfla (yanlış pozitif ölçümü)")
    r.set_defaults(f=cmd_rapor)
