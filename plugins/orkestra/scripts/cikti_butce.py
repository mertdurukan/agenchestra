"""Kullanıcı çıktısı bütçesi (P-001, ADR-0075): turun sohbet metni ölçülür, sınır aşımı gölge modda günlüğe yazılır.
Model çağrılmaz. Tur tanımı tektir (rapor da bunu kullanır): gerçek kullanıcı mesajından sonraki ana ajan `text`
bloklarının karakter toplamı, yan ajan hariç; kapanış = kutu aracından (wrap_up) sonraki metin.

Sınırlar ve kip `ayarlar/cikti_butce.json` (eklenti varsayılanı) ve proje durum dizinindeki `cikti_butce.json` (anahtar
bazında ezer) dosyasındadır. `ORKESTRA_CIKTI_BUTCE=0` kapatır. Hatada sessiz geçer, turu engellemez.
"""
from __future__ import annotations

import json
import os
import re

_KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VARSAYILAN_YOL = os.path.join(_KOK, "ayarlar", "cikti_butce.json")
PROJE_DOSYA = "cikti_butce.json"
KAPI = "cikti_butce"
_OKUMA_SINIRI = 4_000_000  # transkriptin son baytları


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


def acik(ayar: dict) -> bool:
    return os.environ.get("ORKESTRA_CIKTI_BUTCE") != "0" and ayar.get("mod", "kapali") != "kapali"


def _gercek_kullanici_mesaji(o: dict) -> bool:
    if o.get("type") != "user" or o.get("isSidechain") or o.get("isMeta"):
        return False
    icerik = (o.get("message") or {}).get("content")
    if isinstance(icerik, str):
        return bool(icerik.strip())
    return any(isinstance(b, dict) and b.get("type") == "text" for b in icerik or [])


def tur_olc(transkript, kutu_araclari=("wrap_up",), son_mesaj=None) -> dict | None:
    """Son turun ölçümü: {'toplam': karakter, 'kapanis': kutudan sonraki metin karakteri ya da None}.
    Transkript okunamaz ya da turda metin yoksa None. `son_mesaj` transkripte henüz yazılmamış son yanıttır."""
    if not transkript:
        return None
    try:
        with open(transkript, "rb") as f:
            f.seek(0, os.SEEK_END)
            boy = f.tell()
            f.seek(max(0, boy - _OKUMA_SINIRI))
            satirlar = f.read().splitlines()
    except Exception:
        return None
    toplam, kapanis, kutu_goruldu, son_metin = 0, None, False, ""
    for ham in satirlar:
        try:
            o = json.loads(ham)
        except Exception:
            continue
        if not isinstance(o, dict):
            continue
        if _gercek_kullanici_mesaji(o):
            toplam, kapanis, kutu_goruldu, son_metin = 0, None, False, ""
            continue
        if o.get("type") != "assistant" or o.get("isSidechain"):
            continue
        icerik = (o.get("message") or {}).get("content")
        for b in icerik if isinstance(icerik, list) else []:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "tool_use" and str(b.get("name") or "").endswith(tuple(kutu_araclari)):
                kutu_goruldu = True
            elif b.get("type") == "text" and str(b.get("text") or "").strip():
                n = len(b["text"])
                toplam += n
                son_metin = b["text"]
                if kutu_goruldu:
                    kapanis = (kapanis or 0) + n
    if son_mesaj and son_mesaj.strip() and son_mesaj != son_metin:
        toplam += len(son_mesaj)
        if kutu_goruldu:
            kapanis = (kapanis or 0) + len(son_mesaj)
    return {"toplam": toplam, "kapanis": kapanis} if toplam else None


def asimlar(olcum: dict, ayar: dict) -> list[str]:
    """Sınırı aşan ölçüler, gölge kaydının nedeni olarak."""
    nedenler = []
    ts = ayar.get("tur_siniri") or 800
    ks = ayar.get("kapanis_siniri") or 300
    if olcum["toplam"] > ts:
        nedenler.append(f"tur {olcum['toplam']} karakter (sınır {ts})")
    if olcum.get("kapanis") is not None and olcum["kapanis"] > ks:
        nedenler.append(f"kutudan sonraki kapanış {olcum['kapanis']} karakter (sınır {ks})")
    return nedenler


def son_kullanici_mesaji(transkript) -> str:
    """Transkriptteki son gerçek kullanıcı mesajının metni; okunamazsa boş."""
    if not transkript:
        return ""
    try:
        with open(transkript, "rb") as f:
            f.seek(0, os.SEEK_END)
            boy = f.tell()
            f.seek(max(0, boy - _OKUMA_SINIRI))
            satirlar = f.read().splitlines()
    except Exception:
        return ""
    son = ""
    for ham in satirlar:
        try:
            o = json.loads(ham)
        except Exception:
            continue
        if isinstance(o, dict) and _gercek_kullanici_mesaji(o):
            icerik = (o.get("message") or {}).get("content")
            son = icerik if isinstance(icerik, str) else " ".join(
                str(b.get("text") or "") for b in icerik or [] if isinstance(b, dict) and b.get("type") == "text")
    return son


def muaf(mesaj: str, ayar: dict) -> bool:
    """Kullanıcı kapsamlı inceleme/uzun yanıt istiyorsa (P-001 istisnası) uzunluk kapısı block vermez."""
    return any(re.search(k, mesaj or "", re.IGNORECASE) for k in ayar.get("muafiyet_kaliplari") or [])


def mod(ayar: dict) -> str:
    """'block' (aşımda tur başına bir kez kısaltma ister), 'golge' ya da 'kapali'."""
    if os.environ.get("ORKESTRA_CIKTI_BUTCE") == "0":
        return "kapali"
    m = ayar.get("mod", "kapali")
    return m if m in ("golge", "block", "kapali") else "kapali"
