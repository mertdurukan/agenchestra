"""Seçim ekranı hatırlatması (P-029): yanıt kullanıcıya düz metinle seçim yaptırıyorsa ve turda seçim ekranı aracı
çağrılmadıysa ihlal sayılır. Model çağrılmaz.

Kalıplar, kip ve araç adları kodda durmaz: `ayarlar/secim_ekrani_hatirlatma.json` (eklenti varsayılanı) ve proje durum
dizinindeki `secim_ekrani_hatirlatma.json` (anahtar bazında ezer). Bozuk/eksik dosya varsayılana düşer.
`ORKESTRA_SECIM_HATIRLATMA=0` hatırlatmayı kapatır.
"""
from __future__ import annotations

import json
import os
import re

_KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VARSAYILAN_YOL = os.path.join(_KOK, "ayarlar", "secim_ekrani_hatirlatma.json")
PROJE_DOSYA = "secim_ekrani_hatirlatma.json"
MODLAR = ("block", "golge", "kapali")
_OKUMA_SINIRI = 4_000_000  # transkriptin son baytları; tur bundan uzunsa muafiyet aranmaz


def _json_oku(yol: str):
    try:
        with open(yol, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except Exception:
        return None


def ayar_oku(sd=None) -> dict:
    ayar = _json_oku(VARSAYILAN_YOL) or {}
    if sd:
        proje = _json_oku(os.path.join(sd, PROJE_DOSYA))
        if proje:
            ayar.update(proje)
    return ayar


def mod(ayar: dict) -> str:
    """'block' (tur başına bir kez hatırlat), 'golge' (yalnız günlük) ya da 'kapali'; ortam değişkeni 0 ise kapalı."""
    if os.environ.get("ORKESTRA_SECIM_HATIRLATMA") == "0":
        return "kapali"
    m = ayar.get("mod", "kapali")
    return m if m in MODLAR else "kapali"


def _normallestir(metin: str) -> str:
    return (metin or "").replace("İ", "i").replace("I", "ı").lower()


def _kodsuz(metin: str) -> str:
    """Çit ve satır içi kod bloklarını atar: koddaki ya da alıntılanan cümle ihlal sayılmaz."""
    metin = re.sub(r"```.*?```", " ", metin, flags=re.S)
    return re.sub(r"`[^`\n]*`", " ", metin)


def _eslesir(kaliplar, metin: str) -> bool:
    for k in kaliplar or []:
        try:
            if re.search(k, metin):
                return True
        except re.error:
            continue
    return False


def yanit_ihlali(yanit, sd=None) -> bool:
    """Yanıtta düz metin seçtirme kalıbı var ve yanıt muaf kalıp taşımıyor mu?"""
    ayar = ayar_oku(sd)
    if mod(ayar) == "kapali":
        return False
    m = _normallestir(_kodsuz(yanit or ""))
    if not m.strip() or _eslesir(ayar.get("yanit_muaf_kaliplari"), m):
        return False
    return _eslesir(ayar.get("yanit_kaliplari"), m)


def _gercek_kullanici_mesaji(o: dict) -> bool:
    if o.get("type") != "user" or o.get("isSidechain") or o.get("isMeta"):
        return False
    icerik = (o.get("message") or {}).get("content")
    if isinstance(icerik, str):
        return bool(icerik.strip())
    return any(isinstance(b, dict) and b.get("type") == "text" for b in icerik or [])


def _buton_dolu(blok: dict, alanlar: dict) -> bool:
    """Araç çağrısı kullanıcıya düğme sunuyor mu? `buton_alanlari` bir aracın düğme taşıyan girdi alanını adlandırır; alan
    boşsa (ör. yalnız özet içeren kapanış kutusu) çağrı seçim ekranı sayılmaz. Alanı tanımsız araç çağrıldıysa yeter."""
    ad = next((a for a in alanlar if str(blok.get("name") or "").endswith(a)), None)
    if ad is None:
        return True
    girdi = blok.get("input")
    return bool(isinstance(girdi, dict) and girdi.get(alanlar[ad]))


def secim_ekrani_sunuldu(transkript, sd=None) -> bool:
    """Son kullanıcı mesajından sonra ayardaki seçim araçlarından biri düğmeleriyle çağrıldı mı? Okunamazsa False."""
    ayar = ayar_oku(sd)
    alanlar = ayar.get("buton_alanlari") if isinstance(ayar.get("buton_alanlari"), dict) else {}
    araclar = tuple(str(a) for a in (ayar.get("secim_araclari") or []))
    if not transkript or not araclar:
        return False
    try:
        with open(transkript, "rb") as f:
            f.seek(0, os.SEEK_END)
            boy = f.tell()
            f.seek(max(0, boy - _OKUMA_SINIRI))
            satirlar = f.read().splitlines()
    except Exception:
        return False
    bulundu = False
    for ham in satirlar:
        try:
            o = json.loads(ham)
        except Exception:
            continue
        if not isinstance(o, dict):
            continue
        if _gercek_kullanici_mesaji(o):
            bulundu = False
            continue
        if o.get("type") != "assistant" or o.get("isSidechain"):
            continue
        icerik = (o.get("message") or {}).get("content")
        for b in icerik if isinstance(icerik, list) else []:
            if isinstance(b, dict) and b.get("type") == "tool_use" and str(b.get("name") or "").endswith(araclar) and _buton_dolu(b, alanlar):
                bulundu = True
    return bulundu


def hatirlatma_metni(sd=None) -> str:
    return ayar_oku(sd).get("hatirlatma", "")
