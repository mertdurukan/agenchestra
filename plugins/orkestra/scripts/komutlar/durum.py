"""orkestra komutları: durum (oturum worktree'lerindeki ayrışmış durum kopyalarını ana klasöre devralır; ADR-0033).

`orkestra durum devral [--uygula] [--tum] [--kaynak YOL] [--json]`
"""
from __future__ import annotations

import json
import os

from komutlar._ortak import hata, sd_gerekli


def cmd_devral(a):
    import durum_devral as DD
    hedef = sd_gerekli()
    kaynaklar = DD.kaynaklar(hedef, tum=a.tum, kaynak=a.kaynak)
    if not kaynaklar:
        hata("devralınacak ayrı durum klasörü yok (ana ağaçtasın ya da ağaçta `.claude/orkestra` bulunmuyor).", 1)
    rapor = []
    for k in kaynaklar:
        if not os.path.isdir(k):
            hata(f"kaynak klasör yok: {k}")
        plan = DD.planla(k, hedef)
        s = {"kaynak": k, "eklenecek": DD.say(plan), "jsonl": {ad: len(v) for ad, v in plan["jsonl"].items()},
             "isler": [i for i, _ in plan["isler"]], "dosyalar": len(plan["dosyalar"]), "takma": len(plan["takma"]),
             "cakisma": plan["cakisma"], "uygulandi": False}
        if a.uygula and (s["eklenecek"] or not os.path.exists(os.path.join(k, DD.DAMGA))):
            sonuc = DD.uygula(k, hedef, plan)
            s.update(uygulandi=True, yedek=sonuc["yedek"])
        rapor.append(s)
    if a.json:
        print(json.dumps(rapor, ensure_ascii=False, indent=2))
        return
    for s in rapor:
        print(f"kaynak: {s['kaynak']}")
        print(f"  hedefte olmayan: {s['eklenecek']} öğe (jsonl satırı {sum(s['jsonl'].values())}, iş {len(s['isler'])}, "
              f"dosya {s['dosyalar']}, takma {s['takma']})")
        for ad, n in s["jsonl"].items():
            print(f"    {ad}: {n} satır")
        if s["isler"]:
            print(f"    işler: {', '.join(s['isler'])}")
        for c in s["cakisma"]:
            print(f"  ÇAKIŞMA (yazılmadı): {c}")
        if s["uygulandi"]:
            print(f"  uygulandı; yedek: {s['yedek']}; kaynakta {DD.DAMGA} damgası var (kaynak silinmedi)")
        elif s["eklenecek"]:
            print("  kuru koşu: uygulamak için `--uygula`")
        else:
            print("  devralınacak bir şey yok")


def kaydet(alt):
    p = alt.add_parser("durum", help="oturum worktree durum kopyaları")
    s = p.add_subparsers(dest="alt")
    d = s.add_parser("devral", help="worktree kopyasındaki ana klasörde olmayan kayıtları ana durum klasörüne ekle "
                                    "(kuru koşu varsayılan; kaynak silinmez)")
    d.add_argument("--uygula", action="store_true", help="kuru koşu yerine yaz (yedek alır, kaynağa .devralindi koyar)")
    d.add_argument("--tum", action="store_true", help="deponun bütün ağaçlarını tara (varsayılan: bulunduğun ağaç)")
    d.add_argument("--kaynak", help="doğrudan bir durum klasörü yolu")
    d.add_argument("--json", action="store_true")
    d.set_defaults(f=cmd_devral)
