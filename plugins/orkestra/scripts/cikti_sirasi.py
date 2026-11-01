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


def uyari_metni(baslik: str, ayar: dict) -> str:
    return (ayar.get("uyari") or "Orkestra (ADR-0135): karar bekleyen bölüm yanıtın en sonunda olmalı: '{baslik}' bölümünün "
            "ardında içerik var. Bölümü yanıtın son bölümüne taşı; karar yoksa bölümü sil.").replace("{baslik}", baslik)


def kullanici_uyarisi(baslik: str, ayar: dict) -> str:
    return (ayar.get("kullanici_uyarisi") or "Uyarı: '{baslik}' bölümü yanıtın sonunda değil (ADR-0135).").replace("{baslik}", baslik)
