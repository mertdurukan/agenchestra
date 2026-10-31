"""Proje bilgi grafiği şeması ve doğrulayıcı (ADR-0112, I-296; model çağırmaz).

Katmanlar (git'te dosya): kenar listesi `kenarlar.jsonl` ve konu kartları `kartlar/<konu>.md`.
Kenar: {kaynak, iliski, hedef, koken, guven, kanit, hash, dogrulama_zamani}. Alanlar ve değer kümeleri
`ayarlar/harita_iliski.json`'dan gelir (projeye özgü ad kodda yok, P-022).
Kural (K2): kökeni `llm` olan kenar, kanıtı statik doğrulanmadıkça `guven: dusuk` taşır.
Konu kartı: ayarlardaki her bölüm başlığı (`## <Bölüm>`) var ve gövdesi boş olmamalıdır.
Mevcut `harita.py` katmanlarına ve kayıt biçimine dokunmaz.
"""
from __future__ import annotations

import json
import os
import re

AYAR_YOLU = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ayarlar", "harita_iliski.json")
KANIT_SATIR = re.compile(r"^.+:\d+$")


def ayar() -> dict:
    with open(AYAR_YOLU, encoding="utf-8") as f:
        return json.load(f)


def kenar_hatalari(k: dict, a: dict | None = None) -> list[str]:
    """Kenar sözlüğündeki şema ihlallerinin listesi; boşsa geçerli."""
    a = a or ayar()
    if not isinstance(k, dict):
        return ["kenar sözlük değil"]
    h = [f"zorunlu alan boş ya da yok: {z}" for z in a["kenar_zorunlu"] if not str(k.get(z, "")).strip()]
    if k.get("iliski") and k["iliski"] not in a["iliskiler"]:
        h.append(f"bilinmeyen ilişki: {k['iliski']}")
    if k.get("koken") and k["koken"] not in a["kokenler"]:
        h.append(f"bilinmeyen köken: {k['koken']}")
    if k.get("guven") and k["guven"] not in a["guvenler"]:
        h.append(f"bilinmeyen güven: {k['guven']}")
    kanit = str(k.get("kanit", "")).strip()
    if kanit and k.get("koken") in a["kanit_satirli_kokenler"] and not KANIT_SATIR.match(kanit):
        h.append(f"{k['koken']} kenarı kanıtı dosya:satır olmalı: {kanit}")
    if k.get("koken") == "llm" and k.get("guven") and k["guven"] != "dusuk" and not KANIT_SATIR.match(kanit):
        h.append("llm kenarı statik kanıtsız yalnız guven=dusuk olabilir")
    return h


def kart_hatalari(metin: str, a: dict | None = None) -> list[str]:
    """Konu kartında eksik ya da boş bölüm listesi; boşsa geçerli."""
    a = a or ayar()
    govdeler: dict[str, str] = {}
    ad = None
    for s in metin.splitlines():
        m = re.match(r"^##\s+(.+?)\s*$", s)
        if m:
            ad = m.group(1)
            govdeler[ad] = ""
        elif ad is not None:
            govdeler[ad] += s + "\n"
    h = []
    for b in a["kart_bolumleri"]:
        if b not in govdeler:
            h.append(f"bölüm yok: {b}")
        elif not govdeler[b].strip():
            h.append(f"bölüm boş: {b}")
    return h


def kenarlari_oku(yol: str) -> tuple[list[dict], list[str]]:
    """JSONL kenar dosyasını okur; (geçerli kenarlar, `satır N: hata` listesi) döner."""
    a, gecerli, hatalar = ayar(), [], []
    with open(yol, encoding="utf-8") as f:
        for n, s in enumerate(f, 1):
            if not s.strip():
                continue
            try:
                k = json.loads(s)
            except ValueError:
                hatalar.append(f"satır {n}: JSON değil")
                continue
            e = kenar_hatalari(k, a)
            if e:
                hatalar += [f"satır {n}: {x}" for x in e]
            else:
                gecerli.append(k)
    return gecerli, hatalar
