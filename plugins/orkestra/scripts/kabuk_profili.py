"""Kullanıcı kabuğunun komut sözdizimini bağlama ekler ve yanıttaki ihlali günlüğe yazar (ADR-0102, P-043, K-006).

Metin tek kaynaktan okunur: `standartlar/kabuk_profili.md` bölümleri (profil adı = başlık). İki iş:
- UserPromptSubmit: oturumun ilk mesajında ve komut/terminal anan mesajlarda `ORKESTRA KABUK` satırı (`ana_ajan_metni`).
- Stop: yanıttaki `powershell`/`bash` vb. kod bloklarında profile yasak kalıp varsa ihlal adı döner (`yanit_ihlalleri`);
  hook bunu `gunluk.jsonl`'a `kural_ihlal / kabuk_sozdizimi` olarak yazar, engellemez (golge).
Model çağırmaz; hata olursa boş döner. Ayar: `ayarlar/kabuk_profili.json` + proje durum dizininde aynı adlı dosya
(anahtar bazında ezer); `ORKESTRA_KABUK_PROFILI=0` hepsini kapatır.
"""
from __future__ import annotations

import json
import os
import re
import sys

import ork_lib as L
import standart

_KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VARSAYILAN_YOL = os.path.join(_KOK, "ayarlar", "kabuk_profili.json")
PROJE_DOSYA = "kabuk_profili.json"
SAYAC_DOSYA = "kabuk_profili_oturum.json"
PROFILLER = ("powershell5", "powershell7", "bash", "cmd")
MODLAR = ("etkin", "kapali")
STOP_KIPLERI = ("golge", "kapali")
ANA_MAX = 700
TARAMA_MAX = 2000
SAYAC_OTURUM_MAX = 50
KURAL = "kabuk_sozdizimi"
# Bloğun hemen öncesindeki satır "yanlış örnek" diyorsa blok ihlal sayılmaz.
_ORNEK_RX = re.compile(r"yanlış|yanlis|çalışmaz|calismaz|hatalı|desteklemez|geçersiz|gecersiz|kötü örnek|ornek hata", re.I)
_BLOK_RX = re.compile(r"^```[ \t]*([A-Za-z0-9_+-]*)[^\n]*\n(.*?)^```[ \t]*$", re.S | re.M)


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
    if os.environ.get("ORKESTRA_KABUK_PROFILI") == "0":
        return "kapali"
    m = ayar.get("mod", "kapali")
    return m if m in MODLAR else "kapali"


def stop_kip(ayar: dict) -> str:
    if mod(ayar) == "kapali":
        return "kapali"
    k = ayar.get("stop_kip", "golge")
    return k if k in STOP_KIPLERI else "golge"


def profil_sec(ayar: dict) -> str:
    """Ayardaki profil; `auto` ya da geçersizse Windows'ta powershell5, diğerlerinde bash."""
    p = str(ayar.get("profil", "auto"))
    if p in PROFILLER:
        return p
    return "powershell5" if sys.platform == "win32" else "bash"


def _tr_kucuk(metin: str) -> str:
    return metin.replace("İ", "i").replace("I", "ı").lower()


def komut_anan_mi(metin, ayar: dict) -> bool:
    """Mesajda komut/terminal sözcüklerinden biri var mı (düz ve Türkçe küçültmeyle, sözcük başı eşleşmesi)."""
    sozcukler = [s for s in ayar.get("komut_sozcukleri") or [] if isinstance(s, str) and s]
    if not sozcukler or not isinstance(metin, str):
        return False
    kesit = metin[:TARAMA_MAX]
    rx = re.compile(r"(?<!\w)(?:" + "|".join(re.escape(s) for s in sozcukler) + ")")
    return bool(rx.search(kesit.lower()) or rx.search(_tr_kucuk(kesit)))


def _bolum(sd, baslik: str) -> str:
    metin = standart.oku("kabuk_profili", sd) or ""
    m = re.search(r"^##\s+" + re.escape(baslik) + r"\s*$(.*?)(?=^##\s|\Z)", metin, re.S | re.M)
    return " ".join(m.group(1).split()) if m else ""


def _kes(metin: str, sinir: int) -> str:
    if len(metin) <= sinir:
        return metin
    return metin[:sinir - 1].rsplit(" ", 1)[0] + "…"


def _oturum_ilk_mi(sd, oturum_id) -> bool:
    """Oturumun ilk çağrısıysa True ve oturumu işaretler; yazılamazsa False (her mesaja ekleme riskine girme)."""
    yol = os.path.join(sd, SAYAC_DOSYA)
    veri = _json_oku(yol) or {}
    anahtar = str(oturum_id or "?")
    ilk = anahtar not in veri
    veri.pop(anahtar, None)
    veri[anahtar] = 1
    while len(veri) > SAYAC_OTURUM_MAX:
        veri.pop(next(iter(veri)))
    try:
        gecici = yol + ".tmp"
        with open(gecici, "w", encoding="utf-8") as f:
            json.dump(veri, f)
        os.replace(gecici, yol)
    except Exception:
        return False
    return ilk


def _gunluk(sd, oturum_id, nokta: str, profil: str) -> None:
    try:
        L.jsonl_ekle(os.path.join(sd, "gunluk.jsonl"), {"zaman": L.simdi(), "oturum": oturum_id,
                                                         "tur": "kabuk_enjekte", "nokta": nokta, "profil": profil})
    except Exception:
        pass


def ana_ajan_metni(metin, sd=None, oturum_id=None) -> str:
    """Oturumun ilk mesajında ya da komut anan mesajda profil satırı, değilse boş."""
    try:
        if not sd:
            return ""
        ayar = ayar_oku(sd)
        if mod(ayar) == "kapali":
            return ""
        ilk = _oturum_ilk_mi(sd, oturum_id)
        if not ilk and not komut_anan_mi(metin, ayar):
            return ""
        profil = profil_sec(ayar)
        govde = _bolum(sd, profil)
        if not govde:
            return ""
        _gunluk(sd, oturum_id, "ilk" if ilk else "komut", profil)
        return _kes(ayar.get("onek", "") + govde, ANA_MAX)
    except Exception:
        return ""


def _bloklar(yanit: str, etiketler: set):
    """(etiket, gövde, öncesi satır) üçlüleri; yalnız ayardaki kabuk etiketli bloklar."""
    for m in _BLOK_RX.finditer(yanit):
        etiket = m.group(1).lower()
        if etiket not in etiketler:
            continue
        oncesi = yanit[:m.start()].rstrip().rsplit("\n", 1)[-1]
        yield etiket, m.group(2), oncesi


def yanit_ihlalleri(yanit, sd=None) -> list:
    """Yanıttaki kabuk bloklarında profile yasak kalıp eşleşmeleri (kalıp metinleri, tekrarsız).
    Yorum satırları (#, ::, REM) ve 'yanlış/çalışmaz' diye anılan örnek bloklar atlanır."""
    try:
        if not isinstance(yanit, str) or "```" not in yanit:
            return []
        ayar = ayar_oku(sd)
        if stop_kip(ayar) == "kapali":
            return []
        yasak = (ayar.get("yasak") or {}).get(profil_sec(ayar)) or []
        etiketler = {e.lower() for e in ayar.get("kod_etiketleri") or [] if isinstance(e, str)}
        if not yasak or not etiketler:
            return []
        bulunan = []
        for _etiket, govde, oncesi in _bloklar(yanit, etiketler):
            if _ORNEK_RX.search(oncesi):
                continue
            satirlar = [s for s in govde.splitlines() if not s.lstrip().startswith(("#", "::", "REM "))]
            temiz = "\n".join(satirlar)
            for desen in yasak:
                try:
                    if re.search(desen, temiz) and desen not in bulunan:
                        bulunan.append(desen)
                except re.error:
                    continue
        return bulunan
    except Exception:
        return []
