"""Kanıtsız iddia kapısı (ADR-0085, P-021): bilgi sorusu turunda kanıt aracı çağrılmadan, kaynak türü anılmadan yazılmış
olgu iddiasını yakalar. Model çağrılmaz.

Tetik kalıpları ve eşikler kodda durmaz: `ayarlar/kanitsiz_iddia.json` (eklenti varsayılanı) ve proje durum dizinindeki
aynı adlı dosya (anahtar bazında ezer) kullanılır; kanıt sayılan araçlar `ayarlar/kanit_rubrik.json`'dadır. Kapı sınırlı
duyarlılıklı bir algılayıcıdır: başarı ölçüsü kapının sayısı değil `orkestra kanit olc` ana ölçüsüdür.
`ORKESTRA_KANIT_KAPISI=0` kapıyı kapatır. Hatada sessiz geçer.
"""
from __future__ import annotations

import json
import os
import re

_KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VARSAYILAN_YOL = os.path.join(_KOK, "ayarlar", "kanitsiz_iddia.json")
PROJE_DOSYA = "kanitsiz_iddia.json"
MODLAR = ("block", "golge", "kapali")
KURAL = "kanitsiz_iddia"


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
    """'block' (tur başına bir kez durdur), 'golge' (günlük; uyarı yalnız `uyari_acik` ise) ya da 'kapali'."""
    if os.environ.get("ORKESTRA_KANIT_KAPISI") == "0":
        return "kapali"
    m = ayar.get("mod", "kapali")
    return m if m in MODLAR else "kapali"


def _normallestir(metin: str) -> str:
    return (metin or "").replace("İ", "i").replace("I", "ı").lower()


def _eslesir(kaliplar, metin: str) -> bool:
    for k in kaliplar or []:
        try:
            if re.search(k, metin):
                return True
        except re.error:
            continue
    return False


def cumleler(yanit: str):
    """Yanıtı cümlelere böler (kod blokları atılır; madde işareti ve satır sonu ayraçtır)."""
    govde = re.sub(r"```.*?```", " ", yanit or "", flags=re.S)
    for parca in re.split(r"(?<=[.!?])\s+|\n+", govde):
        p = " ".join(parca.split()).strip("-*• ")
        if p:
            yield p


def ilk_eslesme(yanit: str, ayar: dict):
    """Tetik kalıbına uyan ilk cümle (alıntı için kısaltılmış), yoksa None. Yanıtın herhangi bir yerinde kaynak türü
    işareti (ayardaki muaf kalıplar) varsa kapı susar: iddia işaretlenmiş sayılır."""
    if _eslesir(ayar.get("muaf_kaliplari"), _normallestir(yanit)):
        return None
    sinir = ayar.get("alinti_max_karakter", 0) or 0
    for c in cumleler(yanit):
        if _eslesir(ayar.get("tetik_kaliplari"), _normallestir(c)):
            return c[:sinir] if sinir and len(c) > sinir else c
    return None


def degerlendir(transcript_path, yanit=None, sd=None):
    """Son tur bilgi sorusu mu, turda kanıt aracı çağrılmadı mı, yanıtta işaretsiz tetik cümlesi var mı?
    Dönüş {'alinti': cümle} ya da None (kapı sessiz). Hatada None."""
    try:
        import kanit_olcum as K
        import soru_sinif
        ayar = ayar_oku(sd)
        if mod(ayar) == "kapali":
            return None
        tur = K.son_tur(transcript_path, ayar.get("kuyruk_bayt", 2_000_000))
        if not tur or soru_sinif.tur(tur["istem"], sd) != "soru":
            return None
        if K.kanitli_mi(tur, K.rubrik_oku(sd)):
            return None
        alinti = ilk_eslesme(yanit if yanit else tur["yanit"], ayar)
        return {"alinti": alinti} if alinti else None
    except Exception:
        return None


def uyari_acik(ayar: dict) -> bool:
    """Kullanıcıya deterministik uyarı gösterilir mi? Holdout kesinliği eşiği geçtiğinde ayarda `uyari_acik` true yapılır;
    block kipinde uyarı her zaman gösterilir (kullanıcı durdurmanın nedenini görür)."""
    return ayar.get("uyari_acik") is True or mod(ayar) == "block"


def uyari_metni(alinti: str, ayar: dict) -> str:
    """Model çağrılmadan üretilen sabit uyarı; yalnız alıntı değişir."""
    return str(ayar.get("uyari_sablonu", "")).replace("{alinti}", alinti or "")
