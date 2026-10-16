"""orkestra komutları: iz (işlem izi ağacı ve kapsama ölçer)."""
from __future__ import annotations

import json

import iz as IZ  # noqa: E402
from komutlar._ortak import hata, sd_gerekli  # noqa: E402


def cmd_iz(a):
    sd = sd_gerekli()
    if a.secici == "kapsama":
        k = IZ.kapsama(sd)
        print(json.dumps(k, ensure_ascii=False, indent=2) if a.json else IZ.kapsama_metni(k))
        return
    ag = IZ.agac(sd, a.secici)
    if ag is None:
        hata(f"'{a.secici}' için defter satırı yok (istek_id, I-nnn ya da oturum kimliği ver).", 2)
    if a.json:
        print(IZ.json_metni(ag))
    elif a.csv:
        print(IZ.csv_metni(ag), end="")
    else:
        print(IZ.metin(ag))


def kaydet(alt):
    p = alt.add_parser("iz", help="istek / iş / oturum için süre ve token ağacı; `iz kapsama` atıf kapsama ölçümü")
    p.add_argument("secici", help="istek_id, I-nnn, oturum kimliği ya da 'kapsama'")
    p.add_argument("--json", action="store_true")
    p.add_argument("--csv", action="store_true")
    p.set_defaults(f=cmd_iz)
