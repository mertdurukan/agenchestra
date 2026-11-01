"""Karar sırası kapısı (ADR-0135, I-321): karar bekleyen bölüm yanıtın son bölümü olmalıdır.
Model çağrılmaz. Tespit yalnız yapıya bakar: bölüm başlığı (`#` başlığı ya da satır başındaki kalın etiket) ayardaki
`karar_basliklari` kalıplarından biriyse ve ardında içerik taşıyan başka bölüm varsa ihlaldir. Cümle düzeyi kalıp
(P-029 `teklif_sonu`) bu kapıya girmez. Belge bağlantı satırları (K-003) bölüm sayılmaz: hook onları yanıtın sonuna ekler.

Hook yanıt metnini değiştiremez: kip `block` ise tur başına bir kez yeniden yazma ister, ikinci denemede (`stop_hook_active`)
tur geçer, ihlal günlüğe yazılır ve kullanıcıya tek satır uyarı gider. Ayar `ayarlar/cikti_sirasi.json`, proje ezmesi
durum dizinindeki `cikti_sirasi.json`. `ORKESTRA_CIKTI_SIRASI=0` kapatır. Hatada sessiz geçer.
"""
from __future__ import annotations

import json
import os
import re

_KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VARSAYILAN_YOL = os.path.join(_KOK, "ayarlar", "cikti_sirasi.json")
PROJE_DOSYA = "cikti_sirasi.json"
KAPI = "cikti_sirasi"
MODLAR = ("golge", "block", "kapali")

_BASLIK = re.compile(r"^\s{0,3}#{1,6}\s+(?P<b>.+?)\s*#*\s*$")
_ETIKET = re.compile(r"^\s*(?:[-*]\s+)?\*\*(?P<b>[^*\n]{2,60}?)\*\*(?P<k>.*)$")
_BAGLANTI = re.compile(r"^\s*(?:[-*]\s+)?[^:\[\n]{2,60}:\s*\[[^\]]+\]\([^)]+\)\s*$")
_KOD_CITI = re.compile(r"^\s*(```|~~~)")


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
    if os.environ.get("ORKESTRA_CIKTI_SIRASI") == "0":
        return "kapali"
    m = ayar.get("mod", "kapali")
    return m if m in MODLAR else "kapali"


def _etiket_metni(b: str) -> str:
    return re.sub(r"[\s:.]+$", "", b.strip().strip("*").strip()).lower()


def bolumler(yanit: str) -> list[tuple[str, list[str]]]:
    """[(başlık, içerik satırları)]; ilk başlıktan önceki metin başlıksız ("") bölümdür. Kod çitleri içi başlık sayılmaz.
    Satır başı kalın etiketin aynı satırdaki devamı bölümün ilk içerik satırıdır."""
    sonuc: list[tuple[str, list[str]]] = [("", [])]
    kodda = False
    etiket_maddesi = None  # son bölüm satır başı etiketle açıldıysa: madde (True) ya da paragraf (False)
    for satir in (yanit or "").splitlines():
        if _KOD_CITI.match(satir):
            kodda = not kodda
            sonuc[-1][1].append(satir)
            continue
        if kodda:
            sonuc[-1][1].append(satir)
            continue
        m = _BASLIK.match(satir)
        if m:
            sonuc.append((_etiket_metni(m.group("b")), []))
            etiket_maddesi = None
            continue
        m = _ETIKET.match(satir)
        if m:
            sonuc.append((_etiket_metni(m.group("b")), [m.group("k").strip()] if m.group("k").strip() else []))
            etiket_maddesi = bool(re.match(r"\s*[-*]\s", satir))
            continue
        if etiket_maddesi is not None:
            # etiket bölümü maddeyse girintisiz satır, paragrafsa boş satır bölümü bitirir
            biter = (not satir.strip()) if not etiket_maddesi else (bool(satir.strip()) and not satir[:1].isspace())
            if biter:
                sonuc.append(("", []))
                etiket_maddesi = None
        sonuc[-1][1].append(satir)
    return sonuc


def _icerik_var(satirlar: list[str]) -> bool:
    return any(s.strip() and not _BAGLANTI.match(s) for s in satirlar)


def ihlal(yanit, ayar: dict) -> str:
    """Karar bölümü sonda değilse o bölümün başlığını, yoksa boş metin döner."""
    kaliplar = [re.compile(k, re.IGNORECASE) for k in ayar.get("karar_basliklari") or []]
    if not kaliplar or not (yanit or "").strip():
        return ""
    parcalar = bolumler(yanit)
    for i, (baslik, _satirlar) in enumerate(parcalar):
        if baslik and any(k.search(baslik) for k in kaliplar):
            if any(_icerik_var(s) for _b, s in parcalar[i + 1:]):
                return baslik
    return ""


_MADDE = re.compile(r"^(?:[-*]|\d+[.)])\s+")
_BOS_SATIR = re.compile(r"^\W*(yok|yoktur|hiç)\W*$", re.IGNORECASE)


def _kalip(ayar: dict, anahtar: str, varsayilan=()):
    return [re.compile(k, re.IGNORECASE) for k in ayar.get(anahtar) or varsayilan]


def _yuva_maddeleri(satirlar: list[str]) -> list[str]:
    """Yuva içeriğini maddelere böler: madde işaretli satır yeni maddedir, girintili/devam satırı öncekine eklenir;
    madde işareti yoksa paragraf bir maddedir. Belge bağlantı satırları ve boş satırlar atlanır."""
    maddeler: list[str] = []
    for s in satirlar:
        if not s.strip() or _BAGLANTI.match(s):
            continue
        if _MADDE.match(s.strip()) and not s[:1].isspace():
            maddeler.append(s.strip())
        elif maddeler:
            maddeler[-1] += " " + s.strip()
        else:
            maddeler.append(s.strip())
    return maddeler


def _kanitsiz_madde(madde: str, ayar: dict) -> bool:
    """Madde `kanit_etiketi` ("Denendi:") sonrası içerik taşımıyorsa True; "Yok" maddesi yuvayı boş sayar."""
    govde = _MADDE.sub("", madde).strip()
    if _BOS_SATIR.match(govde):
        return False
    etiket = ayar.get("kanit_etiketi") or "Denendi:"
    i = govde.lower().find(etiket.lower())
    if i < 0:
        return True
    kalan = re.sub(r"^[\s*_]+|[\s*_.]+$", "", govde[i + len(etiket):])
    bos = [re.compile(k, re.IGNORECASE) for k in ayar.get("bos_kanit_kaliplari") or []]
    return not kalan or any(b.match(kalan) for b in bos)


def siniflandir(yanit, ayar: dict, auto: bool) -> tuple[str, str]:
    """(sınıf, başlık/madde). Sınıf: "" | "sahip" | "sira" | "kanit". Auto değilse yalnız eski sıra denetimi ("sira").
    Auto'da: kesin sınır yuvası ("Kullanıcıya kalanlar") dışındaki karar başlığı "sahip"; yuva ortadaysa "sira"; yuvadaki
    her madde `Denendi:` kanıtı taşımıyorsa "kanit" (ADR-0137)."""
    if not auto or ayar.get("auto_sinif") is False:
        b = ihlal(yanit, ayar)
        return ("sira", b) if b else ("", "")
    if not (yanit or "").strip():
        return "", ""
    yuva = _kalip(ayar, "kesin_sinir_basliklari")
    yasak = _kalip(ayar, "karar_basliklari") + _kalip(ayar, "auto_yasak_basliklar")
    parcalar = bolumler(yanit)
    for i, (baslik, satirlar) in enumerate(parcalar):
        if not baslik:
            continue
        if any(k.search(baslik) for k in yuva):
            if any(_icerik_var(s) for _b, s in parcalar[i + 1:]):
                return "sira", baslik
            for madde in _yuva_maddeleri(satirlar):
                if _kanitsiz_madde(madde, ayar):
                    return "kanit", madde[:80]
        elif any(k.search(baslik) for k in yasak):
            return "sahip", baslik
    return "", ""


def uyari_metni(baslik: str, ayar: dict, sinif: str = "sira") -> str:
    if sinif in ("sahip", "kanit"):
        ozel = ayar.get("uyari_" + sinif)
        if ozel:
            return ozel.replace("{baslik}", baslik)

    return (ayar.get("uyari") or "Orkestra (ADR-0135): karar bekleyen bölüm yanıtın en sonunda olmalı: '{baslik}' bölümünün "
            "ardında içerik var. Bölümü yanıtın son bölümüne taşı; karar yoksa bölümü sil.").replace("{baslik}", baslik)


def kullanici_uyarisi(baslik: str, ayar: dict, sinif: str = "sira") -> str:
    if sinif in ("sahip", "kanit") and ayar.get("kullanici_uyarisi_" + sinif):
        return ayar["kullanici_uyarisi_" + sinif].replace("{baslik}", baslik)
    return (ayar.get("kullanici_uyarisi") or "Uyarı: '{baslik}' bölümü yanıtın sonunda değil (ADR-0135).").replace("{baslik}", baslik)
