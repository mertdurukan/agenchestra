"""Hata defteri yazıcısı (ADR-0035): hook, CLI ve özet hataları durum klasöründeki hata.jsonl'e imzalı satır olur.

İmza = hata türü + iletinin normalleştirilmiş hâli (sayı, tam yol, geçici dosya adı, onaltılık kimlik çıkarılır).
kaydet() asla istisna fırlatmaz: yazılamazsa stderr'e tek satır yazar.

Davranış hatası (ADR-0037): ajanın yanlış klasör, yanlış kabuk, kapı ihlali gibi kod dışı hataları `davranis()` ile
`sinif: "davranis"` ve `kok` (kaynak, önlenebilir, çözüm) alanlarıyla yazılır; `sinif` alanı olmayan satır kod hatasıdır.
"""
from __future__ import annotations

import os
import re
import sys

import ork_lib as L

DOSYA = "hata.jsonl"
ILETI_EN_COK = 300

_TMP = re.compile(r"\.?tmp_[A-Za-z0-9_]+", re.IGNORECASE)
_YOL_WIN = re.compile(r"[A-Za-z]:[\\/][^\s'\"<>|]*")
_YOL_POSIX = re.compile(r"(?<![\w.])/(?:[\w.\-~]+/)+[\w.\-~]*")
_HEX = re.compile(r"\b(?=[0-9a-fA-F]*\d)[0-9a-fA-F]{8,}\b")
_SAYI = re.compile(r"\d+")
_BOSLUK = re.compile(r"\s+")


# Davranış hatası türleri: kök neden kaynağı (kural|sablon|skill|betik|istem|arac|belirsiz), kaynakta çözümün var olup
# olmadığı (None = mekanik bilinemez; K-006 sorusu insan/denetimle yanıtlanır) ve çözümün yeri.
TURLER = {
    "is-klasoru-yanlis": ("betik", True, "`is ac` başka işin kaydını içeren klasörü reddeder; yeni alt klasör açılır"),
    "kabuk-sozdizimi": ("istem", None, "oturum bağlamında kabuk ayrımı: Bash=POSIX, PowerShell=Windows cmdlet'i"),
    "hook-red": ("kural", None, "reddin kapı kimliğindeki kuralın kaynağı (ilk yazımda uyum) ya da hook mesajı"),
}
_KAPI_KIMLIGI = re.compile(r"\b(?:[KP]-\d{3}|ADR-\d{4})\b")


def kok_neden(tur: str, ileti: str = "") -> dict:
    """Tür tablosundan kök neden alanı; hook-red'de kapı kimliği yoksa kaynak `betik` (kural değil, kod kapısı)."""
    kaynak, onlenebilir, cozum = TURLER.get(tur, ("belirsiz", None, ""))
    if tur == "hook-red" and not _KAPI_KIMLIGI.search(ileti or ""):
        kaynak = "betik"
    return {"kaynak": kaynak, "onlenebilir": onlenebilir, "cozum": cozum}


def imza(tur: str, ileti: str) -> str:
    """Aynı hata aynı imzayı verir; tür ve tırnaklı değerler (KeyError: 'x') korunur."""
    s = str(ileti or "")
    s = _TMP.sub("<tmp>", s)
    s = _YOL_WIN.sub("<yol>", s)
    s = _YOL_POSIX.sub("<yol>", s)
    s = _HEX.sub("<id>", s)
    s = _SAYI.sub("N", s)
    s = _BOSLUK.sub(" ", s).strip()
    return f"{tur}: {s}"[:200]


def _oturum() -> str:
    return os.environ.get("CLAUDE_CODE_SESSION_ID") or os.environ.get("CLAUDE_SESSION_ID") or "-"


def kaydet(sd, kaynak: str, tur: str, ileti: str, baglam=None, ek=None) -> None:
    """sd/hata.jsonl'e tek satır ekler; hiçbir koşulda istisna fırlatmaz. `ek`: satıra eklenen ek alanlar."""
    try:
        ileti = str(ileti or "")
        satir = {"kaynak": kaynak, "imza": imza(tur, ileti), "tur": tur,
                 "ileti": ileti[:ILETI_EN_COK], "zaman": L.simdi(), "oturum": _oturum()}
        if baglam:
            satir["baglam"] = baglam
        if ek:
            satir.update(ek)
        L.jsonl_ekle(os.path.join(sd, DOSYA), satir)
    except Exception as e:  # noqa: BLE001
        try:
            print(f"orkestra: hata kaydı yazılamadı ({type(e).__name__})", file=sys.stderr)
        except Exception:
            pass


def davranis(sd, tur: str, ileti: str, baglam=None) -> None:
    """Davranış hatası satırı: kaynak `davranis`, `sinif: "davranis"` ve kök neden alanı. İstisna fırlatmaz."""
    kaydet(sd, "davranis", tur, ileti, baglam, {"sinif": "davranis", "kok": kok_neden(tur, str(ileti or ""))})
