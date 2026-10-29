"""Panel /araclar: MCP listesi ve aç/kapat (ADR-0098).

Açık = kullanıcı kapsamında kayıtlı (`claude mcp add --scope user`), kapalı = kayıtsız (`claude mcp remove`).
Yazma yalnız belgelenmiş `claude mcp` CLI'si ile yapılır; `~/.claude.json` yalnız okunur. Yalnız kayıttaki
(`ayarlar/mcp_kimlik.json`) adlar kabul edilir. Hiçbir çıktı sır değeri taşımaz (kimlik durumu yalnız ad).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

_BURASI = os.path.dirname(os.path.abspath(__file__))
if _BURASI not in sys.path:
    sys.path.insert(0, _BURASI)

from komutlar import mcp as KM  # noqa: E402

DURUMLAR = ("acik", "kapali")
# Dosya sistemi, kabuk ya da masaüstü denetimi veren MCP'ler: sayfada uyarı rozeti alır.
YUKSEK_YETKI = frozenset({"desktop-commander", "windows-mcp", "filesystem"})


class AraclarHata(ValueError):
    """İstemciye gösterilebilir doğrulama hatası (sır içermez)."""


def kullanici_ayar_yolu() -> str:
    return os.environ.get("ORKESTRA_CLAUDE_JSON") or os.path.join(os.path.expanduser("~"), ".claude.json")


def kayitli_adlar(yol: str | None = None) -> set:
    """Kullanıcı kapsamında kayıtlı MCP adları. Dosya yoksa ya da bozuksa boş küme (yalnız okunur)."""
    try:
        with open(yol or kullanici_ayar_yolu(), encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return set()
    m = d.get("mcpServers") if isinstance(d, dict) else None
    return set(m) if isinstance(m, dict) else set()


def _kayit() -> dict:
    MK = KM._mk()
    try:
        return MK.kayit_oku()
    except MK.KayitHata as e:
        raise AraclarHata(f"MCP kaydı okunamadı: {e}") from e


def liste(kayit: dict | None = None, kayitli: set | None = None, yukle=None, bul=shutil.which) -> list:
    """Kayıttaki her MCP için: ad, aciklama, durum (acik|kapali), kimlik, eksik_gerek, yuksek_yetki."""
    kayit = _kayit() if kayit is None else kayit
    kayitli = kayitli_adlar() if kayitli is None else kayitli
    if yukle is None:
        import kimlik as K
        yukle = K.yukle
    return [{
        "ad": ad,
        "aciklama": kayit[ad].get("aciklama", ""),
        "durum": "acik" if ad in kayitli else "kapali",
        "kimlik": KM.kimlik_durumu(kayit[ad], yukle),
        "eksik_gerek": KM.eksik_gerek(kayit[ad], bul),
        "yuksek_yetki": ad in YUKSEK_YETKI,
    } for ad in sorted(kayit)]


def degistir(ad, durum, kayit: dict | None = None, calistir=subprocess.run, kayitli_oku=kayitli_adlar,
             bul=shutil.which) -> dict:
    """MCP'yi açar (kayıt ekler) ya da kapatır (kayıt siler); sonucu kayıttan yeniden okuyarak doğrular."""
    kayit = _kayit() if kayit is None else kayit
    if not isinstance(ad, str) or ad not in kayit:
        raise AraclarHata("kayıtta olmayan MCP")
    if durum not in DURUMLAR:
        raise AraclarHata("durum acik ya da kapali olmalı")
    if not bul("claude"):
        raise AraclarHata("claude komutu bulunamadı")
    if durum == "acik":
        if ad not in kayitli_oku():
            KM.kur([ad], calistir=calistir, kayit=kayit, hepsi=False, bul=bul)
    elif ad in kayitli_oku():
        calistir(KM._calistirilabilir(["claude", "mcp", "remove", "--scope", "user", ad]), capture_output=True)
    gercek = "acik" if ad in kayitli_oku() else "kapali"
    return {"ad": ad, "istenen": durum, "durum": gercek, "tamam": gercek == durum}
