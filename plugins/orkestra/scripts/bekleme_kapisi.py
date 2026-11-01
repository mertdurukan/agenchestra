"""Sınırsız bekleme döngüsü kapısı (ADR-0138): Bash komutunda zaman sınırı, sayaç ya da süreç canlılığı kontrolü olmayan
bekleme döngüsü komut koşmadan yakalanır; sınırsız döngü arka plan görevi olarak sonsuza dek açık kalır. Model çağrılmaz.

Kalıplar, ret/uyarı metni ve mod kodda durmaz: `ayarlar/bekleme_kapisi.json` (eklenti varsayılanı) ve proje durum
klasöründeki `bekleme_kapisi.json` (anahtar bazında ezer). Mod `kapi_mod` ile okunur (golge | ihlal); kapatma
ORKESTRA_BEKLEME_KAPISI=0. Tırnak içi metin ve heredoc gövdesi veridir, analizden çıkarılır (bu yüzden `timeout N bash -c '...'`
sarması ve `python -c "..."` içindeki metin döngü sayılmaz). Dosya var mı testi tek başına sınır değildir.
"""
from __future__ import annotations

import json
import os
import re

KAPI = "bekleme_kapisi"
_KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VARSAYILAN_YOL = os.path.join(_KOK, "ayarlar", KAPI + ".json")
_TIRNAK = re.compile(r'"(?:\\.|[^"\\])*"|\'[^\']*\'')
_HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n.*?\n\s*\2(?=\s|$)", re.S)


def _json_oku(yol: str):
    try:
        with open(yol, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except Exception:
        return None


def ayar_oku(cwd: str | None = None) -> dict:
    ayar = _json_oku(VARSAYILAN_YOL) or {}
    if cwd:
        try:
            import ork_lib as L
            sd = L.durum_dizini(cwd)
        except Exception:
            sd = None
        if sd:
            proje = _json_oku(os.path.join(sd, KAPI + ".json"))
            if proje:
                ayar.update(proje)
    return ayar


def acik_mi() -> bool:
    return os.environ.get("ORKESTRA_BEKLEME_KAPISI") != "0"


def _var(kaliplar, metin: str) -> bool:
    for k in kaliplar or []:
        try:
            if re.search(k, metin):
                return True
        except re.error:
            continue
    return False


def _veri_disi(komut: str) -> str:
    """Heredoc gövdesi ve tırnak içi metin atılır (veri, komut değil)."""
    return _TIRNAK.sub('""', _HEREDOC.sub(" ", komut))


def sinirsiz_donguler(komut, ayar: dict) -> list[str]:
    """Bekleme (`bekleme_kaliplari`) içeren ama sınırı (`sinir_kaliplari`; ya da sayaç artırımı + karşılaştırma birlikte)
    olmayan döngü blokları (özgün yazımıyla, ilk 120 karakter)."""
    if not isinstance(komut, str) or not komut.strip():
        return []
    temiz = _veri_disi(komut)
    sonuc = []
    for kalip in ayar.get("dongu_kaliplari") or []:
        try:
            eslesmeler = list(re.finditer(kalip, temiz, re.S))
        except re.error:
            continue
        for m in eslesmeler:
            blok = m.group(0)
            if not _var(ayar.get("bekleme_kaliplari"), blok):
                continue
            if _var(ayar.get("sinir_kaliplari"), blok):
                continue
            if _var(ayar.get("surec_sinir_kaliplari"), blok) and not _surec_sinir_gecersiz(blok, ayar):
                continue
            if _var(ayar.get("sayac_artirim_kaliplari"), blok) and _var(ayar.get("sayac_karsilastirma_kaliplari"), blok):
                continue
            sonuc.append(" ".join(blok.split())[:120])
    return sonuc


def karar(komut, cwd: str | None = None) -> tuple[str, str, str] | None:
    """Kapının sonucu: None (geç) ya da (mod, mesaj, ihlalli_parça). Kayıt ve ret çağıranındır."""
    if not acik_mi():
        return None
    ayar = ayar_oku(cwd)
    donguler = sinirsiz_donguler(komut, ayar)
    if not donguler:
        return None
    import kapi_mod
    m = kapi_mod.mod(KAPI, cwd)
    mesaj = ayar.get("ret_metni" if m == "ihlal" else "uyari_metni", "")
    return m, str(mesaj), donguler[0]
