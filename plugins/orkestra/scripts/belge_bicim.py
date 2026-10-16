"""Okunacak belgelerin (plan, todo, özet, bulgu, jira_onerisi, rapor) K-005 biçimi ve K-003 bağlantı satırı kontrolü.

Saf Python; model çağrılmaz. Kurallar ve mod `ayarlar/belge_bicim.json` (eklenti varsayılanı) ve proje durum
dizinindeki `belge_bicim.json` (alan alan ezer) içinden okunur. Bozuk ya da eksik dosya varsayılana düşer.

Yazım anı kapısı (`yazim_ihlalleri`): PreToolUse içinde yazılacak metni tarar; ihlalli içerik diske inmeden bilinir.
Bağlantı kapısı (`baglantisiz_belgeler`): Stop içinde dokunulan belgelerin yanıtta bağlantısı var mı bakar.
Kapsam dışı (kullanıcı kararı bekliyor, rapor Ö7): tablo satırları, kod blokları ve Given/When/Then satırları sayılmaz.
"""
from __future__ import annotations

import json
import os
import re

_KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VARSAYILAN_YOL = os.path.join(_KOK, "ayarlar", "belge_bicim.json")
PROJE_DOSYA = "belge_bicim.json"
MODLAR = ("golge", "ihlal")

_SATIR_ICI_KOD = re.compile(r"`[^`\n]*`")
_BAGLANTI_HEDEFI = re.compile(r"\]\([^)\n]*\)")
_HARF_ISARETI = re.compile(r"\((?:[a-zA-Z]|\d{1,2})\)")
_LISTE_MADDESI = re.compile(r"^\s*(?:[-*]|\d+[.)])\s")


def _json_oku(yol: str):
    try:
        with open(yol, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except Exception:
        return None


def ayar_oku(sd=None) -> dict:
    ayar = _json_oku(VARSAYILAN_YOL) or {}
    proje = _json_oku(os.path.join(sd, PROJE_DOSYA)) if sd else None
    for kapi, deger in (proje or {}).items():
        if isinstance(deger, dict) and isinstance(ayar.get(kapi), dict):
            ayar[kapi] = {**ayar[kapi], **deger}
        else:
            ayar[kapi] = deger
    return ayar


def mod(ayar: dict, kapi: str) -> str:
    m = (ayar.get(kapi) or {}).get("mod", "golge")
    return m if m in MODLAR else "golge"


def belge_mi(yol: str, kapi_ayari: dict) -> bool:
    """Okunacak belge adı (.md; plan/todo/bulgu/jira_onerisi/rapor/özet) ve hariç tutulanlardan değil."""
    if not yol:
        return False
    yol = yol.replace("\\", "/")
    ad = os.path.basename(yol).lower()
    if not ad.endswith(".md"):
        return False
    try:
        if re.search(kapi_ayari.get("haric_ad_kalibi") or r"(?!x)x", ad):
            return False
        if re.search(kapi_ayari.get("haric_yol_kalibi") or r"(?!x)x", yol):
            return False
        return bool(re.search(kapi_ayari.get("belge_adi_kalibi") or r"(?!x)x", ad))
    except re.error:
        return False


def _temizle(metin: str) -> str:
    """Sayımda satır içi kod ve bağlantı hedefi yok sayılır (içindeki ;, · ve ** bağlantıyı bozmaz)."""
    return _BAGLANTI_HEDEFI.sub("]", _SATIR_ICI_KOD.sub("``", metin))


def _bloklar(metin: str, yok_say: re.Pattern | None):
    """(ilk_satır_no, metin, tur) — tur: liste | paragraf. Başlık, tablo, kod bloğu ve yok sayılan satırlar atlanır."""
    cikti, tampon, bas, kod = [], [], None, False

    def bosalt():
        nonlocal tampon, bas
        if tampon:
            cikti.append((bas, " ".join(tampon), "paragraf"))
        tampon, bas = [], None

    for no, ham in enumerate(metin.split("\n"), 1):
        s = ham.rstrip("\r")
        if s.strip().startswith("```"):
            bosalt()
            kod = not kod
            continue
        if kod:
            continue
        if not s.strip():
            bosalt()
            continue
        if s.lstrip().startswith("#") or s.lstrip().startswith("|") or s.lstrip().startswith("<!--"):
            bosalt()
            continue
        if yok_say and yok_say.search(s):
            bosalt()
            continue
        if _LISTE_MADDESI.match(s):
            bosalt()
            cikti.append((no, s.strip(), "liste"))
            continue
        if bas is None:
            bas = no
        tampon.append(s.strip())
    bosalt()
    return cikti


def yazim_ihlalleri(metin: str, dosya_adi: str, ayar: dict) -> list[dict]:
    """Yazılacak metindeki K-005 ihlalleri: [{satir, kural, ayrinti}]. Satır, metnin kendi içinde 1'den sayılır."""
    k = ayar.get("yazim_kapisi") or {}
    if not metin:
        return []
    bastirma = k.get("bastirma_isareti") or "<!-- biçim-tamam -->"
    try:
        yok_say = re.compile(k["yok_say_satir_kalibi"]) if k.get("yok_say_satir_kalibi") else None
        etiket = re.compile(k.get("etiket_kalibi") or r"\*\*[^*\n]{1,40}?:?\*\*:?")
    except re.error:
        return []
    paragraf_azami = int(k.get("paragraf_azami") or 300)
    todo_azami = int(k.get("todo_madde_azami") or 200)
    en_az = int(k.get("sikisik_liste_en_az") or 2)
    noktali_en_az = int(k.get("noktali_virgul_en_az") or 3)  # düz cümlede iki ; olağan; üç ve üzeri liste
    todo = "todo" in os.path.basename(dosya_adi).lower()
    ihlaller = []
    for no, blok, tur in _bloklar(metin, yok_say):
        if bastirma in blok:
            continue
        t = _temizle(blok)
        if len(etiket.findall(t)) >= 2:
            ihlaller.append({"satir": no, "kural": "coklu_etiket",
                             "ayrinti": "bir paragrafta birden çok etiket; her etiketli alan ayrı paragrafa"})
        if t.count(";") >= noktali_en_az or t.count(" · ") >= en_az or len(_HARF_ISARETI.findall(t)) >= en_az:
            ihlaller.append({"satir": no, "kural": "sikisik_liste",
                             "ayrinti": "satır içi liste (;, ·, (a)(b)); her maddeyi ayrı satıra, madde işaretiyle yaz"})
        todo_maddesi = todo and tur == "liste"
        azami = todo_azami if todo_maddesi else paragraf_azami
        if len(blok) > azami:
            ihlaller.append({"satir": no, "kural": "uzun_todo_madde" if todo_maddesi else "uzun_paragraf",
                             "ayrinti": f"{len(blok)} karakter, en çok {azami}; "
                                        + ("ayrıntıyı plan.md ya da özete yaz" if todo_maddesi else "kısa paragraflara böl")})
    return ihlaller


def ozet_satiri(dosya_adi: str, ihlaller: list[dict], en_cok: int = 3) -> str:
    """Tek satırlık uyarı: ilk ihlaller satır numarasıyla."""
    parca = ", ".join(f"satır {i['satir']} {i['kural']}" for i in ihlaller[:en_cok])
    ek = f" (+{len(ihlaller) - en_cok})" if len(ihlaller) > en_cok else ""
    return f"Orkestra biçim (K-005, gölge): {dosya_adi}: {parca}{ek}. Ayrıntı: {ihlaller[0]['ayrinti']}."


def baglantisiz_belgeler(dokunulan, yanit: str, ayar: dict) -> list[str]:
    """Dokunulan okunacak belgelerden yanıtta bağlantısı (`](…<dosya adı>…)`) olmayanlar; yol sırası korunur."""
    k = ayar.get("baglanti_kapisi") or {}
    yanit = (yanit or "").replace("\\", "/")
    sonuc, gorulen = [], set()
    for yol in dokunulan or []:
        tam = str(yol).replace("\\", "/")
        if tam in gorulen or not belge_mi(tam, k):
            continue
        gorulen.add(tam)
        ad = os.path.basename(tam)
        if not re.search(r"\]\([^)\n]*" + re.escape(ad) + r"[^)\n]*\)", yanit):
            sonuc.append(tam)
    return sonuc
