"""Eklenti kural metinlerindeki ADR atıfları ORK-ADR- önekli olmalı; KURALLAR.md bloğu json ile tutarlı."""
import json
import os
import re
import sys

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import kapi_mod  # noqa: E402
ONEKSIZ = re.compile(r"(?<!ORK-)\bADR-\d")


def _kurallar():
    with open(os.path.join(KOK, "kurallar", "eklenti_kurallari.json"), encoding="utf-8") as f:
        return json.load(f)["kurallar"]


def test_eklenti_kural_metinlerinde_oneksiz_adr_yok():
    kotu = [(r["id"], k) for r in _kurallar() if r.get("katman") == "plugin"
            for k in ("metin", "neden") if ONEKSIZ.search(r.get(k) or "")]
    assert kotu == []


def test_kurallar_md_oneksiz_adr_yok_ve_blok_json_ile_tutarli():
    with open(os.path.join(KOK, "KURALLAR.md"), encoding="utf-8") as f:
        md = f.read().replace("\r\n", "\n")
    assert not ONEKSIZ.search(md)
    blok = md.split("<!-- eklenti-kurallari:basla -->")[1].split("<!-- eklenti-kurallari:bitis -->")[0]
    blok = re.sub(r"\s+", " ", blok)
    for r in _kurallar():
        if r.get("durum") == "etkin":
            assert re.sub(r"\s+", " ", kapi_mod.mod_coz(r["metin"])).strip() in blok, r["id"]
