"""Jira Done yorumu: çalışma özetinden deterministik türetme (ADR-0091). `orkestra is jira-yorum` bunu kullanır.

Model ve ağ çağrısı yoktur; metin değiştirilmeden taşınır. Alan eşlemesi (standartlar/jira_yorum.md):
- Sonuç      = `**Durum:**` gövdesi + `**Ne yapıldı?**` ilk maddesi (etiket [..] dahil)
- Değişiklik, Test, Deploy, Geri alma = `**Teslim:**` bloğunun aynı adlı satırları
- Not        = `**Açık kalanlar:**` maddeleri (boşsa "Yok")
Alan ayrıştırması is_kaydi._alan_govdesi ile yapılır; ikinci ayrıştırıcı yoktur.
"""
from __future__ import annotations

import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import is_kaydi as IK  # noqa: E402

TESLIM = ("Değişiklik", "Test", "Deploy", "Geri alma")
_YORUM = re.compile(r"<!--.*?-->", re.S)
_MADDE = re.compile(r"^(\s*[-*]\s+)", re.M)
_AYRAC = ""  # özel kullanım karakteri: _alan_govdesi boşluk sanmaz, madde sınırını taşır


def ozet_dosyasi(klasor: str) -> str:
    """Klasördeki en yeni calisma_ozeti*.md ('' = yok)."""
    adaylar = sorted(glob.glob(os.path.join(klasor, "calisma_ozeti*.md"))) if klasor else []
    return adaylar[-1] if adaylar else ""


def _maddeler(metin: str, ad: str) -> list[str] | None:
    """Alanın madde listesi (metin aynen); alan yoksa None. Madde sınırı ayraçla işaretlenip _alan_govdesi'ye verilir."""
    govde = IK._alan_govdesi(_MADDE.sub(lambda m: m.group(1) + _AYRAC, metin), ad)
    if govde is None:
        return None
    return [p.strip() for p in govde.split(_AYRAC)[1:] if p.strip()]


def _teslim(metin: str) -> dict[str, str]:
    """`**Teslim:**` bloğunun dört alt satırı; olmayan ya da boş alt satır sözlükte yer almaz."""
    govde = IK._alan_govdesi(metin, "Teslim") or ""
    parca = re.split(r"\*\*(%s):\*\*" % "|".join(re.escape(a) for a in TESLIM), govde)
    out: dict[str, str] = {}
    for i in range(1, len(parca) - 1, 2):
        deger = parca[i + 1].strip()
        if deger and parca[i] not in out:
            out[parca[i]] = deger
    return out


def uret(metin: str) -> tuple[str | None, str | None]:
    """(yorum, None) ya da (None, neden). Neden: 'Durum' yoksa üretilmez; eksik alanlar 'eksik: A, B' ile adlandırılır."""
    metin = _YORUM.sub("", metin or "")
    durum = IK._alan_govdesi(metin, "Durum")
    if not durum:
        return None, "yorum üretilmedi: çalışma özetinde `**Durum:**` alanı yok ya da boş"
    yapilan = _maddeler(metin, "Ne yapıldı?") or []
    teslim = _teslim(metin)
    eksik = ([] if yapilan else ["Sonuç"]) + [a for a in TESLIM if a not in teslim]
    if eksik:
        return None, "eksik: " + ", ".join(eksik)
    acik = IK._alan_govdesi(metin, "Açık kalanlar") or ""
    satirlar = [("Sonuç", f"{durum} {yapilan[0]}")] + [(a, teslim[a]) for a in TESLIM] + [("Not", acik or "Yok")]
    return "\n".join(f"- **{ad}:** {deger}" for ad, deger in satirlar) + "\n", None
