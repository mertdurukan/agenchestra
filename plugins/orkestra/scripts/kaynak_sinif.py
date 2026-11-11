"""Soru tarafı kaynak sınıfı (ADR-0178, I-226 P7/P8); model çağrılmaz.

Kullanıcı mesajı (yanıt değil) dört kaynak sınıfından birine eşlenir: yerel, gecmis_oturum, urun_belgesi, canli_bulut.
Eşleşen sınıf için bağlama tek satır gider: sınıfın ilk aracı ve "araç sonucundan önce olgu cümlesi yazma" sözleşmesi
(P1 KAYNAK satırının yerini alır). Aynı dosya kullanıcı itirazını (`ilk_cevap_itiraz`) tanır: itiraz kalıbı + önceki
asistan turunda kanıt aracı yok.

Kalıplar, sıra, satır şablonu ve eşikler kodda durmaz: `ayarlar/kaynak_sinif.json` (eklenti varsayılanı) ve proje durum
dizinindeki aynı adlı dosya (anahtar bazında ezer). Bozuk/eksik dosya varsayılana düşer.
"""
from __future__ import annotations

import json
import os
import re

_KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VARSAYILAN_YOL = os.path.join(_KOK, "ayarlar", "kaynak_sinif.json")
PROJE_DOSYA = "kaynak_sinif.json"


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


def _ayar(sd_ya_da_ayar) -> dict:
    return sd_ya_da_ayar if isinstance(sd_ya_da_ayar, dict) else ayar_oku(sd_ya_da_ayar)


def _normallestir(metin) -> str:
    import soru_sinif
    return soru_sinif._normallestir(metin or "")


def _eslesir(kaliplar, metin: str) -> bool:
    for k in kaliplar or []:
        try:
            if re.search(k, metin):
                return True
        except re.error:
            continue
    return False


def _kes(metin, ayar: dict) -> str:
    """Kalıp girişini `giris_max_karakter`e keser: uzun ve boşluksuz girdide düzenli ifade süresi sınırlı kalır."""
    sinir = int(ayar.get("giris_max_karakter") or 0)
    m = (metin or "").strip()
    return m[:sinir] if sinir > 0 else m


def sinif(metin, sd=None):
    """Mesajın kaynak sınıfı (`sira`daki ilk eşleşen) ya da None. `sd` durum dizini ya da hazır ayar sözlüğü.
    Bir sınıfın `cipa_kaliplari` (somut çıpa: yol, kimlik, gösterme) her zaman sınıflar; `kaliplar` (genel sözcük)
    sınıfta `kavram_haric` açıksa kavram sorusunda (`kavram_kaliplari`) sınıflamaz."""
    ayar = _ayar(sd)
    m = _normallestir(_kes(metin, ayar))
    if not m:
        return None
    kavram = None
    siniflar = ayar.get("siniflar") or {}
    for ad in ayar.get("sira") or []:
        s = siniflar.get(ad)
        if not isinstance(s, dict):
            continue
        if _eslesir(s.get("cipa_kaliplari"), m):
            return ad
        if _eslesir(s.get("kaliplar"), m):
            if s.get("kavram_haric"):
                if kavram is None:
                    kavram = _eslesir(ayar.get("kavram_kaliplari"), m)
                if kavram:
                    continue
            return ad
    return None


def yonlendirme(metin, sd=None) -> str:
    """Sınıf eşleşirse tek satırlık ilk araç sözleşmesi; eşleşmez ya da `max_karakter`'i aşarsa boş."""
    ayar = _ayar(sd)
    ad = sinif(metin, ayar)
    if not ad:
        return ""
    s = (ayar.get("siniflar") or {}).get(ad) or {}
    satir = str(ayar.get("satir_sablonu") or "").replace("{ad}", str(s.get("ad") or ad)) \
        .replace("{ilk_arac}", str(s.get("ilk_arac") or ""))
    satir = " ".join(satir.split())
    sinir = ayar.get("max_karakter")
    return satir if satir and (not sinir or len(satir) <= sinir) else ""


def kapsamda_mi(istem, sd=None) -> bool:
    """Sınıf kapısı ve kapsam ölçümü yalnız `kapsam_turleri` (varsayılan: bilgi sorusu) turlarında çalışır."""
    import soru_sinif
    ayar = _ayar(sd)
    return soru_sinif.tur(_kes(istem, ayar), sd if not isinstance(sd, dict) else None) in (ayar.get("kapsam_turleri") or [])


def itiraz_kalibi(metin, onceki_yanit, sd=None):
    """Mesaj önceki asistan yanıtına olgu hatası atfı mı? Eşleşen kalıp kimliği ya da None (garanti değil, kalıp).
    Hatalı eşleşmeyi azaltma: kısa komut (`min_karakter` altı) ve `haric_kaliplari` (övgü, komut, özet) sayılmaz.
    Atıf kalıbı önceki yanıta göndermeyi hata işaretiyle birlikte ister. Başlangıç kalıbı `isaret_gerekir` ise mesajda
    `baslangic_hata_isareti` de aranır; önceki yanıt soruyla bitiyorsa (soruya verilen yanıt) başlangıç kalıbı sayılmaz."""
    ayar = _ayar(sd)
    it = ayar.get("itiraz") or {}
    if not it.get("acik"):
        return None
    m = _normallestir(_kes(metin, ayar))
    if len(m) < int(it.get("min_karakter") or 0) or _eslesir(it.get("haric_kaliplari"), m):
        return None
    import olay_duzeltme
    kid = olay_duzeltme.eslesen(m, olay_duzeltme.derle({"duzeltme_kaliplari": it.get("atif_kaliplari")}))
    if kid:
        return kid
    if it.get("soru_yanitini_atla") and str(onceki_yanit or "").rstrip().endswith("?"):
        return None
    for k in it.get("baslangic_kaliplari") or []:
        if not isinstance(k, dict) or not olay_duzeltme.eslesen(m, olay_duzeltme.derle({"duzeltme_kaliplari": [k]})):
            continue
        if k.get("isaret_gerekir") and not _eslesir(it.get("baslangic_hata_isareti"), m):
            continue
        return str(k.get("id"))
    return None


def ilk_cevap_itiraz(istem, onceki_tur, sd=None, r=None):
    """Kullanıcı itirazı + önceki asistan turunda kanıt aracı yok → {'kalip', 'sinif'}; yoksa None.
    `onceki_tur` kanit_olcum tur sözlüğüdür (istem, cagrilar, yanit); `r` kanıt rubriği (verilmezse okunur)."""
    if not onceki_tur or not str(onceki_tur.get("yanit") or "").strip():
        return None
    kid = itiraz_kalibi(istem, onceki_tur.get("yanit"), sd)
    if not kid:
        return None
    import kanit_olcum as K
    if r is None:
        r = K.rubrik_oku(sd if not isinstance(sd, dict) else None)
    if K.kanitli_mi(onceki_tur, r):
        return None
    return {"kalip": kid, "sinif": sinif(onceki_tur.get("istem"), sd)}
