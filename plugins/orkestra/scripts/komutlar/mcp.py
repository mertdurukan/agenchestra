"""orkestra komutları: mcp (MCP kaydı ve config; ADR-0096). Hiçbir komut sır değeri yazmaz.

`orkestra mcp liste`                         kayıtlı MCP'ler ve kimlik durumu (var/yok; değer yok)
`orkestra mcp config [--mcp AD] [--hedef H]` config üretir: `json` (mcpServers, Claude Desktop/.mcp.json biçimi)
                                            ya da `claude-code` (claude mcp add komutları); yalnız sarmalayıcı komutunu taşır
`orkestra mcp kur [--mcp AD | --hepsi]`      `claude mcp add --scope user` ile kaydeder (`--kuru`: yalnız komutu göster)
"""
from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys

from komutlar._ortak import hata

_BETIK = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "mcp_kimlik.py"))


def _mk():
    sys.path.insert(0, os.path.dirname(_BETIK))
    import mcp_kimlik as MK
    return MK


def betik_yolu() -> str:
    """Config'e yazılan sarmalayıcı yolu; eklenti güncellemesinde değişen önbellek yolu yerine ORKESTRA_MCP_BETIK ile sabitlenebilir."""
    return os.environ.get("ORKESTRA_MCP_BETIK") or _BETIK


def sunucu_girdisi(ad: str) -> dict:
    """Tek MCP'nin config girdisi: yalnız sarmalayıcı komutu ve MCP adı. Kayıttaki hiçbir alan (ortam dâhil) buraya geçmez."""
    return {"command": "python", "args": [betik_yolu().replace("\\", "/"), ad]}


def config_json(kayit: dict, adlar: list) -> dict:
    return {"mcpServers": {ad: sunucu_girdisi(ad) for ad in adlar}}


def ekle_komutu(ad: str) -> list:
    g = sunucu_girdisi(ad)
    return ["claude", "mcp", "add", "--scope", "user", ad, "--", g["command"], *g["args"]]


def kimlik_durumu(girdi: dict, yukle) -> str:
    """'gerekmez', 'var' ya da 'yok: servis.ANAHTAR,...' (yalnız ad; değer okunmaz yazılmaz)."""
    ortam = girdi.get("ortam") or {}
    if not ortam:
        return "gerekmez"
    try:
        d = yukle(girdi["kimlik_servisi"])
    except Exception:
        d = {}
    eksik = [f"{girdi['kimlik_servisi']}.{a}" for a in ortam.values() if a not in d]
    return "var" if not eksik else "yok: " + ", ".join(eksik)


def _kayit():
    MK = _mk()
    try:
        return MK.kayit_oku()
    except MK.KayitHata as e:
        hata(str(e))


def _adlar(a, kayit: dict) -> list:
    if getattr(a, "hepsi", False) or not getattr(a, "mcp", None):
        return sorted(kayit)
    yok = [x for x in a.mcp if x not in kayit]
    if yok:
        hata(f"kayıtta olmayan MCP: {', '.join(yok)} (kayıtlı: {', '.join(sorted(kayit))})")
    return list(a.mcp)


def cmd_liste(a):
    kayit = _kayit()
    import kimlik as K
    for ad in sorted(kayit):
        print(f"{ad}: kimlik {kimlik_durumu(kayit[ad], K.yukle)}; komut {kayit[ad]['komut'][0]}")


def cmd_config(a):
    kayit = _kayit()
    adlar = _adlar(a, kayit)
    if a.hedef == "claude-code":
        for ad in adlar:
            print(" ".join(shlex.quote(x) for x in ekle_komutu(ad)))
    else:
        print(json.dumps(config_json(kayit, adlar), indent=2, ensure_ascii=False))


def kur(adlar: list, calistir=subprocess.run, kuru: bool = False) -> list:
    """(ad, durum) listesi. Zaten kayıtlıysa dokunmaz ('zaten kayıtlı'); `calistir` testte yerine konur."""
    sonuc = []
    for ad in adlar:
        komut = ekle_komutu(ad)
        if kuru:
            sonuc.append((ad, "kuru: " + " ".join(shlex.quote(x) for x in komut)))
            continue
        if calistir(["claude", "mcp", "get", ad], capture_output=True).returncode == 0:
            sonuc.append((ad, "zaten kayıtlı"))
            continue
        r = calistir(komut, capture_output=True)
        sonuc.append((ad, "eklendi" if r.returncode == 0 else f"hata (çıkış kodu {r.returncode})"))
    return sonuc


def cmd_kur(a):
    kayit = _kayit()
    adlar = _adlar(a, kayit)
    if not a.kuru and not shutil.which("claude"):
        hata("claude komutu bulunamadı (Claude Code kurulu ve PATH'te olmalı)")
    sonuc = kur(adlar, kuru=a.kuru)
    for ad, durum in sonuc:
        print(f"{ad}: {durum}")
    if any(d.startswith("hata") for _, d in sonuc):
        raise SystemExit(1)


def kaydet(alt):
    p = alt.add_parser("mcp", help="MCP kaydı: kimlikli sarmalayıcı config'i üret ve kur (değer yazmaz)").add_subparsers(dest="alt", required=True)
    p.add_parser("liste", help="kayıtlı MCP'ler ve kimlik durumu").set_defaults(f=cmd_liste)
    c = p.add_parser("config", help="config üret (yalnız sarmalayıcı komutu; sır yok)")
    c.add_argument("--mcp", action="append", help="MCP adı (tekrarlanabilir; yoksa hepsi)")
    c.add_argument("--hedef", choices=["json", "claude-code"], default="json")
    c.set_defaults(f=cmd_config)
    k = p.add_parser("kur", help="claude mcp add --scope user ile kaydet")
    k.add_argument("--mcp", action="append", help="MCP adı (tekrarlanabilir)")
    k.add_argument("--hepsi", action="store_true", help="kayıttaki hepsi")
    k.add_argument("--kuru", action="store_true", help="komutu çalıştırmadan göster")
    k.set_defaults(f=cmd_kur)
