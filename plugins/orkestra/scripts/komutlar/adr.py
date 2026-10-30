"""orkestra komutları: adr (ADR hedef deposu ve numarası; ADR-0097).

`orkestra adr yeni <iş> "<başlık>"`   planın `**Kök:**` deposuna sıradaki numarayla altı alanlı ADR iskeleti yazar
`orkestra adr depo <iş>`              hedef depoyu, sıradaki numarayı ve uzak depo durumunu gösterir
İskeletin alanları boştur: doldurulana kadar ADR kapısı (P-015) geçmez.
"""
from __future__ import annotations

import datetime
import os
import re
import unicodedata

import adr_depo
from komutlar._ortak import hata, sd_gerekli


def _slug(baslik):
    s = unicodedata.normalize("NFKD", baslik.replace("ı", "i").replace("İ", "I")).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return (s[:60].rstrip("-")) or "karar"


def iskelet(no, baslik, is_id):
    gun = datetime.date.today().isoformat()
    return (f"# ADR-{no:04d}: {baslik}\n\n**Durum:** Önerildi\n\n**Tarih:** {gun}\n\n**Bağlam:**\n\n**Karar:**\n\n"
            f"**Seçenekler:**\n\n**Sonuçlar:**\n\n**İlgili iş:** {is_id}\n")


def _hedef(a):
    from komutlar import isler
    sd = sd_gerekli()
    kayit = isler._is_gerekli(sd, a.is_id)
    proje = isler._proje_koku(sd)
    try:
        plan = open(os.path.join(kayit["klasor"], "plan.md"), encoding="utf-8").read()
    except OSError:
        plan = ""
    return adr_depo.depolar(plan, kayit["klasor"], proje)[0]


def cmd_yeni(a):
    kok = _hedef(a)
    no = adr_depo.sonraki_no(kok)
    yol = os.path.join(kok, "adr", f"ADR-{no:04d}-{_slug(a.baslik)}.md")
    if os.path.exists(yol):
        hata(f"ADR zaten var: {yol}")
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    with open(yol, "x", encoding="utf-8") as f:
        f.write(iskelet(no, a.baslik, a.is_id))
    print(f"ADR-{no:04d} → {yol}")
    print(f"plan.md'ye yaz: **ADR:** ADR-{no:04d}; atıf depo adıyla verilir ({os.path.basename(kok)} ADR-{no:04d})")


def cmd_depo(a):
    kok = _hedef(a)
    print(f"hedef depo: {kok}")
    print(f"sıradaki numara: ADR-{adr_depo.sonraki_no(kok):04d}")
    print(f"uzak depo: {'var' if adr_depo.uzak_var(kok) else 'yok (ADR yedeksiz; orkestra doktor uyarır)'}")


def kaydet(alt):
    p = alt.add_parser("adr", help="ADR hedef deposu ve numarası (ADR-0097)").add_subparsers(dest="alt", required=True)
    y = p.add_parser("yeni", help="hedef depoya altı alanlı ADR iskeleti yaz")
    y.add_argument("is_id")
    y.add_argument("baslik")
    y.set_defaults(f=cmd_yeni)
    d = p.add_parser("depo", help="hedef depo, sıradaki numara, uzak depo durumu")
    d.add_argument("is_id")
    d.set_defaults(f=cmd_depo)
