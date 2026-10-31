"""İşçi ajanlarını (agents/isci-t1..t4.md) tek protokol gövdesinden üretir (ADR-0120).

Kaynak: ajan_kaynak/isci_protokol.md (gövde), ajan_kaynak/isci_basamak.json (basamak başına sabit alanlar),
ayarlar/model_politikasi.json `basamak` (model, effort). Claude Code ajan dosyasında include yoktur; üretilen dosya
depoya girer. Kullanım: ajan_uret.py [--kontrol]  (--kontrol: depodakiyle farkı listeler, çıkış 1).
"""
from __future__ import annotations

import json
import os
import sys

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KAYNAK = os.path.join(KOK, "ajan_kaynak")
POLITIKA = os.path.join(KOK, "ayarlar", "model_politikasi.json")


def _json(yol):
    with open(yol, encoding="utf-8") as f:
        return json.load(f)


def uret(politika: dict | None = None, basamak: dict | None = None, govde: str | None = None) -> dict:
    """{dosya adı: içerik}; politika/basamak/govde testte verilebilir."""
    pol = (politika or _json(POLITIKA))["basamak"]
    bas = basamak or _json(os.path.join(KAYNAK, "isci_basamak.json"))
    if govde is None:
        with open(os.path.join(KAYNAK, "isci_protokol.md"), encoding="utf-8", newline="") as f:
            govde = f.read()
    cikti = {}
    for b, alan in bas.items():
        model, effort = pol[b]["model"], pol[b]["effort"]
        ust = ["---", f"name: {alan['name']}", f"description: {alan['description']}", f"tools: {alan['tools']}",
               f"disallowedTools: {alan['disallowedTools']}", f"model: {model}", f"effort: {effort}",
               f"maxTurns: {alan['maxTurns']}", f"color: {alan['color']}", "---"]
        gov = govde.replace("{basamak}", b).replace("{model}", model.capitalize()).replace("{effort}", effort)
        cikti[alan["name"] + ".md"] = "\n".join(ust) + "\n" + gov
    return cikti


def main(argv=None) -> int:
    a = list(sys.argv[1:] if argv is None else argv)
    cikti = uret()
    farkli = []
    for ad, icerik in cikti.items():
        yol = os.path.join(KOK, "agents", ad)
        try:
            with open(yol, encoding="utf-8", newline="") as f:
                mevcut = f.read()
        except OSError:
            mevcut = None
        if mevcut != icerik:
            farkli.append(ad)
            if "--kontrol" not in a:
                with open(yol, "w", encoding="utf-8", newline="") as f:
                    f.write(icerik)
    if farkli:
        print(("fark: " if "--kontrol" in a else "yazıldı: ") + ", ".join(farkli))
    return 1 if farkli and "--kontrol" in a else 0


if __name__ == "__main__":
    sys.exit(main())
