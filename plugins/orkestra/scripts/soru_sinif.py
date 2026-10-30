"""Soru sınıflayıcı (G-120): kullanıcı mesajı bilgi sorusuysa tek satırlık not üretir; model çağrılmaz.

Kalıplar ve eşikler kodda durmaz: `ayarlar/soru_sinif.json` (eklenti varsayılanı) ve proje durum
dizinindeki `soru_sinif.json` (anahtar bazında ezer) içinden okunur. Bozuk/eksik dosya varsayılana düşer.
"""
from __future__ import annotations

import json
import os
import re

_KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VARSAYILAN_YOL = os.path.join(_KOK, "ayarlar", "soru_sinif.json")
PROJE_DOSYA = "soru_sinif.json"


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


def _normallestir(metin: str) -> str:
    return metin.replace("İ", "i").replace("I", "ı").lower()


def _eslesir(kaliplar, metin: str) -> bool:
    for k in kaliplar or []:
        try:
            if re.search(k, metin):
                return True
        except re.error:
            continue
    return False


def _onay_mesaji(metin) -> bool:
    try:
        import is_onay
        return is_onay.onay_mesaji_mi(metin or "")
    except Exception:
        return False


def _is_fiil(ayar: dict, m: str) -> bool:
    """İş fiili (emir/istek kipi) kalıbı; '?' taşıyan mesajda geçersiz (soru cümlesi, I-138 P1)."""
    return "?" not in m and _eslesir(ayar.get("is_fiil_kaliplari"), m)


def bilgi_sorusu_mu(metin, ayar: dict) -> bool:
    m = _normallestir((metin or "").strip())
    if not m:
        return False
    if len(m) > ayar.get("uzun_max_karakter", 0):
        return False
    if _eslesir(ayar.get("eylem_kaliplari"), m) or _is_fiil(ayar, m):
        return False
    if m.endswith("?") and len(m) <= ayar.get("kisa_max_karakter", 0):
        return True
    if _eslesir(ayar.get("soru_kaliplari"), m):
        return True
    eki = ayar.get("soru_eki_regex")
    return bool(eki) and _eslesir([eki], m)


def not_metni(metin, sd=None) -> str:
    ayar = ayar_oku(sd)
    return ayar.get("not", "") if bilgi_sorusu_mu(metin, ayar) else ""


def kaynak_metni(metin, sd=None) -> str:
    """ADR-0085: boş olmayan her kullanıcı mesajına kaynak türü sözleşmesi (canlı durum ve ürün iddiasına bak ya da
    'doğrulanmadı' yaz). Metin ve boy sınırı ayardan; sınırı aşan metin bağlamı şişirmesin diye verilmez."""
    if not _normallestir((metin or "").strip()):
        return ""
    ayar = ayar_oku(sd)
    m = " ".join(str(ayar.get("kaynak_sozlesmesi") or "").split())
    sinir = ayar.get("kaynak_max_karakter")
    return m if not sinir or len(m) <= sinir else ""


def yol_kapsami_mi(metin, ayar: dict) -> bool:
    """Yol notu kapsamı (I-273 K2): `tur()` sonucundan bağımsız; boş, çok kısa, selam/onay/devam mesajı hariç."""
    m = _normallestir((metin or "").strip())
    if not m or len(m) < ayar.get("yol_min_karakter", 0):
        return False
    return not (_eslesir(ayar.get("yol_haric_kaliplari"), m) or _onay_mesaji(metin))


def yol_metni(metin, sd=None) -> str:
    """ADR-0103: kapsamdaki mesaja aday yol taraması sözleşmesi (skill, MCP, kod/kayıt, resmi belge). Metin, boy sınırı
    ve kapsam ayardan; sınırı aşan metin verilmez. `ORKESTRA_YOL_NOTU=0` ya da boş `yol_sozlesmesi` kapatır."""
    if os.environ.get("ORKESTRA_YOL_NOTU") == "0":
        return ""
    ayar = ayar_oku(sd)
    m = " ".join(str(ayar.get("yol_sozlesmesi") or "").split())
    sinir = ayar.get("yol_max_karakter")
    if not m or not sinir or len(m) > sinir or not yol_kapsami_mi(metin, ayar):
        return ""
    return m


def tur(metin, sd=None) -> str:
    """Hız için model yok: 'soru' (bilgi sorusu), 'devam' (kısa/atıflı mesaj) ya da 'is'. Kararsızsa 'devam'."""
    ayar = ayar_oku(sd)
    m = _normallestir((metin or "").strip())
    if _is_fiil(ayar, m):  # I-138 P1: iş fiili soru kalıbından önce ("neden" geçse de iştir)
        return "is"
    if bilgi_sorusu_mu(metin, ayar):
        return "soru"
    if len(m) <= ayar.get("devam_max_karakter", 0) or _eslesir(ayar.get("devam_kaliplari"), m):
        return "devam"
    return "is"


def bagli_tur(metin, sd=None) -> str:
    """Bağlı oturum için sınıf (I-061 P1): 'soru' (muaf), 'devam' (açıkça devam: zayıf olmayan devam kalıbı ya da
    çok kısa mesaj) ya da 'belirsiz' (iş metniyle karşılaştırılır). Zayıf kalıplar ('bunu', 'bunlar') tek başına
    geçiş vermez: yeni konunun ilk mesajı da öyle başlar. Model çağrılmaz."""
    ayar = ayar_oku(sd)
    if bilgi_sorusu_mu(metin, ayar):
        return "soru"
    m = _normallestir((metin or "").strip())
    if not m:
        return "devam"
    if _onay_mesaji(metin):  # I-138 P16: onay sözcüğüyle başlayan mesaj (P15 ölçütü) açıkça devamdır
        return "devam"
    zayif = set(ayar.get("devam_zayif_kaliplari") or [])
    guclu = [k for k in ayar.get("devam_kaliplari") or [] if k not in zayif]
    if len(m) <= ayar.get("devam_kisa_max_karakter", 0) or _eslesir(guclu, m):
        return "devam"
    return "belirsiz"


def yanit_ihlali(yanit, sd=None) -> bool:
    """Yanıtta konu dışı öneri/"ister misin" kalıbı var mı (regex; model yok, ek token yok)."""
    return _eslesir(ayar_oku(sd).get("yanit_yasak_kaliplari"), _normallestir(yanit or ""))
