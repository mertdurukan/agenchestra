"""orkestra komutları: teslim kuyruğu (I-323 P2). Model çağırmaz.

`orkestra teslim kuyruk ekle --dal D [--teslim ID] [--oturum O] [--test gecti|yok]`   işi kuyruğa verir, sırayı yazar
`orkestra teslim kuyruk liste [--durum D] [--json]`                                  teslimler ve tek-koşucu kilidi

Oturum tam paketi kendisi koşmaz; entegrasyon koşucusu kuyruktaki teslimleri toplu koşar (kuyruk.py).
"""
from __future__ import annotations

import json

from komutlar._ortak import hata, oturum_id, sd_gerekli


def cmd_ekle(a):
    import kuyruk as K
    sd = sd_gerekli()
    oturum = a.oturum or oturum_id()
    try:
        k = K.ekle(sd, a.teslim or a.dal, oturum, a.dal, a.test)
    except K.KuyrukHatasi as e:
        hata(f"teslim kuyruk ekle: {e}")
    except TimeoutError as e:
        hata(f"teslim kuyruk ekle: kuyruk kilidi alınamadı ({e})")
    ek = " (karantinadan yeniden teslim)" if k.get("onceki") == "karantina" else ""
    print(f"kuyrukta sıra {k['sira']}: {k['teslim']} ({k['durum']}, önünde {k['onunde']} teslim){ek}")


def cmd_liste(a):
    import kuyruk as K
    sd = sd_gerekli()
    kayitlar = K.liste(sd, a.durum)
    kos = K.kosucu(sd)
    if a.json:
        print(json.dumps({"teslimler": kayitlar, "kosucu": kos}, ensure_ascii=False, indent=2))
        return
    for k in kayitlar:
        print(f"{k.get('sira')}\t{k.get('durum')}\t{k.get('teslim')}\t{k.get('dal')}\t"
              f"{str(k.get('oturum') or '-')[:8]}\ttest={k.get('test')}")
    durum = "yok" if not kos else f"{str(kos.get('sahip'))[:8]}{' (bayat)' if kos.get('bayat') else ''}"
    print(f"{len(kayitlar)} teslim; koşucu: {durum}")


def kaydet(alt):
    t = alt.add_parser("teslim", help="teslim kuyruğu: işi toplu entegrasyon koşusuna ver").add_subparsers(
        dest="alt", required=True)
    ku = t.add_parser("kuyruk", help="kuyruğa ekle ya da listele").add_subparsers(dest="kuyruk_alt", required=True)
    e = ku.add_parser("ekle", help="işi kuyruğa verir, sıra numarasını yazar")
    e.add_argument("--dal", required=True)
    e.add_argument("--teslim", help="teslim kimliği (varsayılan: dal adı)")
    e.add_argument("--oturum", help="oturum kimliği (varsayılan: CLAUDE_CODE_SESSION_ID)")
    e.add_argument("--test", default="gecti", choices=("gecti", "kaldi", "yok"), help="hedefli test sonucu")
    e.set_defaults(f=cmd_ekle)
    li = ku.add_parser("liste", help="teslimler ve koşucu kilidi")
    li.add_argument("--durum", choices=("bekliyor", "kosuyor", "birlesti", "karantina"))
    li.add_argument("--json", action="store_true")
    li.set_defaults(f=cmd_liste)
