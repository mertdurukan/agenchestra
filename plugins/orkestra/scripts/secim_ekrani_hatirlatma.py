"""Seçim ekranı hatırlatması (P-029): yanıt kullanıcıya düz metinle seçim yaptırıyorsa ve turda seçim ekranı aracı
çağrılmadıysa ihlal sayılır. Model çağrılmaz.

Kalıplar, kip ve araç adları kodda durmaz: `ayarlar/secim_ekrani_hatirlatma.json` (eklenti varsayılanı) ve proje durum
dizinindeki `secim_ekrani_hatirlatma.json` (anahtar bazında ezer). Bozuk/eksik dosya varsayılana düşer.
`ORKESTRA_SECIM_HATIRLATMA=0` hatırlatmayı kapatır.
"""
from __future__ import annotations

import json
import os
import re

_KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VARSAYILAN_YOL = os.path.join(_KOK, "ayarlar", "secim_ekrani_hatirlatma.json")
PROJE_DOSYA = "secim_ekrani_hatirlatma.json"
MODLAR = ("block", "golge", "kapali")
_OKUMA_SINIRI = 4_000_000  # transkriptin son baytları; tur bundan uzunsa muafiyet aranmaz


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
    """'block' (tur başına bir kez hatırlat), 'golge' (yalnız günlük) ya da 'kapali'; ortam değişkeni 0 ise kapalı."""
    if os.environ.get("ORKESTRA_SECIM_HATIRLATMA") == "0":
        return "kapali"
    m = ayar.get("mod", "kapali")
    return m if m in MODLAR else "kapali"


def _normallestir(metin: str) -> str:
    return (metin or "").replace("İ", "i").replace("I", "ı").lower()


def _kodsuz(metin: str) -> str:
    """Çit ve satır içi kod bloklarını atar: koddaki ya da alıntılanan cümle ihlal sayılmaz."""
    metin = re.sub(r"```.*?```", " ", metin, flags=re.S)
    return re.sub(r"`[^`\n]*`", " ", metin)


def _eslesir(kaliplar, metin: str) -> bool:
    for k in kaliplar or []:
        try:
            if re.search(k, metin):
                return True
        except re.error:
            continue
    return False


def yanit_ihlali(yanit, sd=None) -> bool:
    """Yanıtta düz metin seçtirme kalıbı var ve yanıt muaf kalıp taşımıyor mu?"""
    ayar = ayar_oku(sd)
    if mod(ayar) == "kapali":
        return False
    m = _normallestir(_kodsuz(yanit or ""))
    if not m.strip() or _eslesir(ayar.get("yanit_muaf_kaliplari"), m):
        return False
    return _eslesir(ayar.get("yanit_kaliplari"), m)


def _gercek_kullanici_mesaji(o: dict) -> bool:
    if o.get("type") != "user" or o.get("isSidechain") or o.get("isMeta"):
        return False
    icerik = (o.get("message") or {}).get("content")
    if isinstance(icerik, str):
        return bool(icerik.strip())
    return any(isinstance(b, dict) and b.get("type") == "text" for b in icerik or [])


def _buton_dolu(blok: dict, alanlar: dict) -> bool:
    """Araç çağrısı kullanıcıya düğme sunuyor mu? `buton_alanlari` bir aracın düğme taşıyan girdi alanını adlandırır; alan
    boşsa (ör. yalnız özet içeren kapanış kutusu) çağrı seçim ekranı sayılmaz. Alanı tanımsız araç çağrıldıysa yeter."""
    ad = next((a for a in alanlar if str(blok.get("name") or "").endswith(a)), None)
    if ad is None:
        return True
    girdi = blok.get("input")
    return bool(isinstance(girdi, dict) and girdi.get(alanlar[ad]))


def secim_ekrani_sunuldu(transkript, sd=None) -> bool:
    """Son kullanıcı mesajından sonra ayardaki seçim araçlarından biri düğmeleriyle çağrıldı mı? Okunamazsa False."""
    ayar = ayar_oku(sd)
    alanlar = ayar.get("buton_alanlari") if isinstance(ayar.get("buton_alanlari"), dict) else {}
    araclar = tuple(str(a) for a in (ayar.get("secim_araclari") or []))
    if not transkript or not araclar:
        return False
    try:
        with open(transkript, "rb") as f:
            f.seek(0, os.SEEK_END)
            boy = f.tell()
            f.seek(max(0, boy - _OKUMA_SINIRI))
            satirlar = f.read().splitlines()
    except Exception:
        return False
    bulundu = False
    for ham in satirlar:
        try:
            o = json.loads(ham)
        except Exception:
            continue
        if not isinstance(o, dict):
            continue
        if _gercek_kullanici_mesaji(o):
            bulundu = False
            continue
        if o.get("type") != "assistant" or o.get("isSidechain"):
            continue
        icerik = (o.get("message") or {}).get("content")
        for b in icerik if isinstance(icerik, list) else []:
            if isinstance(b, dict) and b.get("type") == "tool_use" and str(b.get("name") or "").endswith(araclar) and _buton_dolu(b, alanlar):
                bulundu = True
    return bulundu


def hatirlatma_metni(sd=None) -> str:
    return ayar_oku(sd).get("hatirlatma", "")


TUR_BASI_SINIR = 300  # yönerge her kullanıcı mesajında bağlama girer; bağlam maliyeti sınırı


def tur_basi_metni(sd=None) -> str:
    """Tur başında ana ajanın bağlamına konan düğme yönergesi (`tur_basi_yonerge`): karar cümlesi yazılmadan önce görünür.
    Kip 'kapali' (ya da ortam değişkeni 0) ise boş döner; en çok `TUR_BASI_SINIR` karakter."""
    ayar = ayar_oku(sd)
    if mod(ayar) == "kapali":
        return ""
    metin = ayar.get("tur_basi_yonerge")
    return metin.strip()[:TUR_BASI_SINIR] if isinstance(metin, str) else ""


def yapisal_mod(ayar: dict) -> str:
    """Yapısal kapının kipi (`yapisal_mod` anahtarı): 'golge' (yalnız günlük), 'block' ya da 'kapali'. Kalıp kapısının `mod`
    anahtarından bağımsızdır (P-028: yeni kapı önce gölgede); ortam değişkeni 0 ise kapalı."""
    if os.environ.get("ORKESTRA_SECIM_HATIRLATMA") == "0":
        return "kapali"
    m = ayar.get("yapisal_mod", "kapali")
    return m if m in MODLAR else "kapali"


def _tur_arac_cagrilari(transkript):
    """Son kullanıcı mesajından sonraki ana ajan `tool_use` blokları (yan zincir hariç); okunamazsa boş liste."""
    if not transkript:
        return []
    try:
        with open(transkript, "rb") as f:
            f.seek(0, os.SEEK_END)
            boy = f.tell()
            f.seek(max(0, boy - _OKUMA_SINIRI))
            satirlar = f.read().splitlines()
    except Exception:
        return []
    bloklar = []
    for ham in satirlar:
        try:
            o = json.loads(ham)
        except Exception:
            continue
        if not isinstance(o, dict):
            continue
        if _gercek_kullanici_mesaji(o):
            bloklar = []
            continue
        if o.get("type") != "assistant" or o.get("isSidechain"):
            continue
        icerik = (o.get("message") or {}).get("content")
        bloklar += [b for b in icerik if isinstance(b, dict) and b.get("type") == "tool_use"] if isinstance(icerik, list) else []
    return bloklar


def tur_degisiklik_var(transkript, sd=None) -> bool:
    """Son kullanıcı mesajından sonra ayardaki `degisiklik_araclari` araçlarından biri çağrıldı mı? Okunamazsa False."""
    araclar = tuple(str(a) for a in (ayar_oku(sd).get("degisiklik_araclari") or []))
    if not araclar:
        return False
    return any(str(b.get("name") or "").endswith(araclar) for b in _tur_arac_cagrilari(transkript))


def tur_ask_dolu_actions_bos(transkript, sd=None) -> bool:
    """Turda seçim aracı (`buton_alanlari`) kullanıcıya soru (`ask`) sordu ama düğme alanı boş mu? Yalnız özet içeren
    kapanış kutusu (ask da boş) karar istemediği için sayılmaz. Okunamazsa False."""
    ayar = ayar_oku(sd)
    alanlar = ayar.get("buton_alanlari") if isinstance(ayar.get("buton_alanlari"), dict) else {}
    for b in _tur_arac_cagrilari(transkript):
        ad = next((a for a in alanlar if str(b.get("name") or "").endswith(a)), None)
        girdi = b.get("input")
        if ad is not None and isinstance(girdi, dict) and str(girdi.get("ask") or "").strip() and not girdi.get(alanlar[ad]):
            return True
    return False


def teklif_sonu(yanit, sd=None) -> bool:
    """Yanıtın SON cümlesi kullanıcıdan karar ister ya da eylem teklif eder mi? Kalıp listesi değil kapanış yapısına bakar:
    soru işaretiyle bitiş ya da 1. tekil teklif eki (`teklif_sonu_kaliplari`, ör. 'açarım', 'yapayım'). Kod blokları atılır."""
    ayar = ayar_oku(sd)
    m = _normallestir(_kodsuz(yanit or "")).strip()
    if not m or _eslesir(ayar.get("yanit_muaf_kaliplari"), m):
        return False
    son = re.split(r"(?<=[.!?:])\s+|\n+", m)[-1].strip(" \t\"'“”*_)")
    if not son:
        return False
    return son.endswith("?") or _eslesir(ayar.get("teklif_sonu_kaliplari"), son)


GOZLEM_TETIKLERI = ("degisiklik",)  # ihlal değil gözlem: tur dosya değiştirdi ama karar istenmedi


def yapisal_tetik(transkript, yanit=None, sd=None) -> str:
    """Yapısal kapının tetiği: 'ask_butonsuz' (kapanış kutusu soru sordu, düğme yok), 'teklif_sonu' (yanıt kapanışı teklif/soru,
    düğme yok), 'degisiklik' (tur dosya değiştirdi, karar istenmedi: gözlem, ihlal değil) ya da ''. Turda dolu düğme sunulduysa
    boş. Karar anı yapıdan okunur; dosya değişikliği tek başına karar anı değildir."""
    if yapisal_mod(ayar_oku(sd)) == "kapali" or secim_ekrani_sunuldu(transkript, sd):
        return ""
    if tur_ask_dolu_actions_bos(transkript, sd):
        return "ask_butonsuz"
    if teklif_sonu(yanit, sd):
        return "teklif_sonu"
    return "degisiklik" if tur_degisiklik_var(transkript, sd) else ""


def yapisal_ihlal(transkript, sd=None, yanit=None) -> bool:
    """Kapanış karar istiyor (kutu sorusu ya da teklif/soru cümlesi) ama kullanıcıya düğmeli seçim ekranı sunulmadı mı?"""
    return yapisal_tetik(transkript, yanit, sd) not in ("",) + GOZLEM_TETIKLERI
