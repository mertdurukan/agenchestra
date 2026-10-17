"""orkestra komutları: model politikası (goster)."""
from __future__ import annotations

import json
import sys

import model_politika as MP  # noqa: E402


def cmd_goster(a) -> int:
    cfg = MP.yukle(getattr(a, "sd", None))
    if a.json:
        print(json.dumps(cfg, ensure_ascii=False, indent=2))
        return 0
    print(f"Model politikası ({MP.AYAR_DOSYASI})")
    print(f"ana ajan varsayılan: {(cfg.get('ana_ajan') or {}).get('varsayilan')}")
    print(f"yasak: {', '.join(cfg.get('yasak') or []) or '-'}")
    for b, v in (cfg.get("basamak") or {}).items():
        print(f"{b}: model={v.get('model')} effort={v.get('effort')}")
    print(f"karar eşikleri: {json.dumps(cfg.get('karar') or {}, ensure_ascii=False)}")
    print(f"yükseltme sırası: {' > '.join(cfg.get('yukseltme_sirasi') or [])}")
    return 0


def kaydet(alt):
    """Bu modülün alt komutlarını ana ayrıştırıcıya ekler."""
    p = alt.add_parser("politika", help="model politikası: goster (ayarlar/model_politikasi.json)")
    s = p.add_subparsers(dest="politika_komut", required=True)
    g = s.add_parser("goster", help="basamak→model/effort tablosu, yasak model, karar eşikleri")
    g.add_argument("--json", action="store_true")
    g.add_argument("--sd")
    g.set_defaults(f=lambda a: sys.exit(cmd_goster(a)))
