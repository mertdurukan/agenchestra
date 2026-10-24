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


# Ret bağlamı (I-224, R7): hook reddi kaydına araç, hedef dosya, ajan, deneme sayısı, maskeli metin parçası ve R1–R9
# sınıfı. Alanlar opsiyoneldir; verilmeyen satır eski biçimdedir. Okuyucular ret_baglami() ile eksik alanı None alır.
RET_ALANLARI = ("kapi", "arac", "dosya", "ajan", "deneme", "metin200", "ret_sinif")
METIN_EN_COK = 200
_DENEME_PENCERE = 256 * 1024   # deneme sayımı için hata.jsonl'in yalnız son 256 KB'ı okunur (hook hızlı kalır)


def kapi_kimligi(ileti: str):
    """İletideki ilk kapı kimliği (K-nnn, P-nnn, ADR-nnnn); yoksa None."""
    m = _KAPI_KIMLIGI.search(ileti or "")
    return m.group(0) if m else None


def _onceki_ret(sd, oturum: str, kapi) -> int:
    """Aynı oturumda aynı kapının hata.jsonl'deki önceki ret sayısı; okunamazsa 0. Eski (kapisiz) satırlar sayılmaz."""
    if not kapi:
        return 0
    try:
        with open(os.path.join(sd, DOSYA), "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - _DENEME_PENCERE))
            veri = f.read().decode("utf-8", errors="replace")
    except OSError:
        return 0
    n = 0
    for s in veri.splitlines():
        if f'"{kapi}"' not in s:
            continue
        try:
            k = json.loads(s)
        except ValueError:
            continue   # pencerenin başında yarım kalan satır
        if isinstance(k, dict) and k.get("kapi") == kapi and k.get("oturum") == oturum:
            n += 1
    return n


def _ret_alanlari(sd, oturum: str, ileti: str, kapi, arac, dosya, ajan, metin) -> dict:
    kapi = kapi or kapi_kimligi(ileti)
    return {"kapi": kapi, "arac": arac, "dosya": dosya,
            "ajan": ajan if ajan in ("ana", "alt") else None,
            "deneme": _onceki_ret(sd, oturum, kapi) + 1,
            "metin200": L.maskele(str(metin))[:METIN_EN_COK] if metin else None,   # önce maske: kesim sırrı bölmesin
            "ret_sinif": RN.ret_sinifi(kapi)}


def ret_baglami(satir: dict) -> dict:
    """Satırın ret bağlamı; eski biçimli satırda alanlar None (okuyucular bu yardımcıyla iki biçimi de okur)."""
    satir = satir if isinstance(satir, dict) else {}
    return {k: satir.get(k) for k in RET_ALANLARI}


def kaydet(sd, kaynak: str, tur: str, ileti: str, baglam=None, ek=None, *, kapi=None, arac=None, dosya=None,
           ajan=None, metin=None) -> None:
    """sd/hata.jsonl'e tek satır ekler; hiçbir koşulda istisna fırlatmaz. `ek`: satıra eklenen ek alanlar.

    Ret bağlamı (opsiyonel): kapi, arac, dosya, ajan ('ana'|'alt'), metin (ret edilen metin; maskelenip ilk 200
    karakteri yazılır). Biri verilirse satır RET_ALANLARI'nın hepsini taşır; hiçbiri verilmezse satır eski biçimdir.
    """
    try:
        ileti = str(ileti or "")
        oturum = _oturum()
        satir = {"kaynak": kaynak, "imza": imza(tur, ileti), "tur": tur,
                 "ileti": ileti[:ILETI_EN_COK], "zaman": L.simdi(), "oturum": oturum}
        if baglam:
            satir["baglam"] = baglam
        if ek:
            satir.update(ek)
        if any(v is not None for v in (kapi, arac, dosya, ajan, metin)):
            satir.update(_ret_alanlari(sd, oturum, ileti, kapi, arac, dosya, ajan, metin))
        L.jsonl_ekle(os.path.join(sd, DOSYA), satir)
    except Exception as e:  # noqa: BLE001
        try:
            print(f"orkestra: hata kaydı yazılamadı ({type(e).__name__})", file=sys.stderr)
        except Exception:
            pass


def davranis(sd, tur: str, ileti: str, baglam=None, **ret) -> None:
    """Davranış hatası satırı: kaynak `davranis`, `sinif: "davranis"` ve kök neden alanı. İstisna fırlatmaz.

    `ret`: kaydet()'in ret bağlamı kwargs'ı (kapi, arac, dosya, ajan, metin); hook-red çağrısı bunları geçirebilir.
    """
    kaydet(sd, "davranis", tur, ileti, baglam, {"sinif": "davranis", "kok": kok_neden(tur, str(ileti or ""))}, **ret)
