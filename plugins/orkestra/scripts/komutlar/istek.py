"""orkestra komutları: `is istek` — işin istek defterini (istek_defteri.md) kullanıcı mesajından çıkarır (ADR-0110)."""
from __future__ import annotations

import argparse
import os
import sys

import istek_defteri as ID  # noqa: E402
from komutlar._ortak import hata, sd_gerekli  # noqa: E402


def cmd_is_istek(a):
    import komutlar.isler as isler
    sd = sd_gerekli()
    kayit = isler._is_gerekli(sd, a.is_id)
    if a.mesaj_dosya:
        with open(a.mesaj_dosya, encoding="utf-8") as f:
            mesaj = f.read()
    else:
        mesaj = a.mesaj or ""
    try:
        maddeler = ID.olustur(kayit["klasor"], mesaj, a.talep)
    except ValueError as e:
        return hata(str(e))
    for i, m in enumerate(maddeler, 1):
        print(f"R{i}: {m}")
    print(os.path.join(kayit["klasor"], ID.DOSYA))


def kaydet(alt):
    is_parser = alt.choices.get("is")
    if is_parser is None:
        raise RuntimeError("istek: `is` komutu kayıtlı değil (isler modülü önce kaydedilmeli)")
    is_alt = next(x for x in is_parser._actions if isinstance(x, argparse._SubParsersAction))
    d = is_alt.add_parser("istek", help="kullanıcı mesajındaki bağlantıları ve taleplerini R1…Rn olarak istek_defteri.md'ye yazar (ADR-0110)")
    d.add_argument("--yardım", action="help", help="bu yardımı gösterir")
    d.add_argument("is_id", help="iş kimliği (I-nnn)")
    d.add_argument("--mesaj-dosya", dest="mesaj_dosya", help="kullanıcı mesajının metin dosyası (bağlantılar betikle çıkarılır)")
    d.add_argument("--mesaj", help="kullanıcı mesajı (kısa)")
    d.add_argument("--talep", action="append", default=[], help="bağlantısı olmayan serbest metin talebi (tekrarlanabilir)")
    d.set_defaults(f=cmd_is_istek)
