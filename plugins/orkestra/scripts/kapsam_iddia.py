"""Kısmi okumadan kapsam iddiası (ADR-0181): okuma anında önleme notu ve Stop'ta gölge ölçüm. Model çağrılmaz.

- `okuma_notu`: PreToolUse'ta Read `offset`/`limit` ile dosyanın bir kısmını okuyorsa oturum ve dosya başına bir kez
  kısa not döner: okunan aralık dışı için "yalnız/hiç/tümü" denmez; tamamı için tanım okunur ya da aranır.
- `tur_degerlendir`: turdaki her Read kısmi ve turda arama yoksa, yanıtta kapsam sözcüğü ile backtick kod adı aynı
  cümlede geçiyorsa bulgu döner. Hook bunu yalnız gölge kaydı olarak yazar (P-028); block yoktur.

Kapsam kalıpları tek kaynaktan gelir: `ayarlar/plan_dogrulama.json` `kapsam_kaliplari`. Diğer ayarlar
`ayarlar/kapsam_iddia.json` ve proje durum dizinindeki aynı adlı dosyadadır. `ORKESTRA_KAPSAM_KAPISI=0` kapatır.
Hatada sessiz geçer.
"""
from __future__ import annotations

import json
import os
import re

_KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VARSAYILAN_YOL = os.path.join(_KOK, "ayarlar", "kapsam_iddia.json")
PROJE_DOSYA = "kapsam_iddia.json"
DURUM_DOSYA = "kapsam_okuma.json"
KURAL = "kapsam_iddia"
_KOD = re.compile(r"`[^`\n]{2,}`")


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
        ayar.update(_json_oku(os.path.join(sd, PROJE_DOSYA)) or {})
    return ayar


def mod(ayar: dict) -> str:
    """'golge' ya da 'kapali'. Block yoktur: geçiş ölçülmüş kesinlik ≥%75 ve ayrı ADR ister (ayardaki 'block' gölge sayılır)."""
    if os.environ.get("ORKESTRA_KAPSAM_KAPISI") == "0":
        return "kapali"
    return "kapali" if ayar.get("mod") == "kapali" else "golge"


def kapsam_rx():
    import plan_dogrulama as PD
    return PD.kapsam_derleyici(PD.ayar().get("kapsam_kaliplari"))


def _satir_sayisi(yol: str, sinir: int) -> int | None:
    try:
        if os.path.getsize(yol) > sinir:
            return None
        with open(yol, "rb") as f:
            return f.read().count(b"\n") + 1
    except OSError:
        return None


def kismi_aralik(arac: str, girdi, cwd: str | None = None, sinir: int = 2_000_000):
    """Read kısmi okuma ise (bas, bit|None) döner; tam okuma ya da başka araç ise None. Dosya limit içinde tümüyle
    kalıyorsa (satır sayısı bilinir ve aralık kapsıyorsa) tam okuma sayılır."""
    if arac != "Read" or not isinstance(girdi, dict):
        return None
    ofs, lim = girdi.get("offset"), girdi.get("limit")
    if not ofs and not lim:
        return None
    try:
        bas = max(1, int(ofs or 1))
        bit = bas + int(lim) - 1 if lim else None
    except (TypeError, ValueError):
        return None
    yol = str(girdi.get("file_path") or "")
    n = _satir_sayisi(os.path.join(cwd or os.getcwd(), yol) if yol else "", sinir) if yol else None
    if n is not None and bas <= 1 and (bit is None or bit >= n):
        return None
    return bas, bit


def _gorulen(sd: str, oid: str, yol: str) -> bool:
    """Bu oturumda bu dosya için not verildi mi; verilmediyse kaydeder. Durum yalnız son oturumu tutar."""
    p = os.path.join(sd, DURUM_DOSYA)
    d = _json_oku(p) or {}
    if d.get("oturum") != oid:
        d = {"oturum": oid, "yollar": []}
    anahtar = os.path.normcase(os.path.abspath(yol))
    if anahtar in d["yollar"]:
        return True
    d["yollar"] = (d["yollar"] + [anahtar])[-200:]
    try:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
    except OSError:
        pass
    return False


def okuma_notu(sd, oid, arac: str, girdi, cwd: str | None = None) -> str:
    """Kısmi Read için oturum ve dosya başına bir kez not; yoksa boş."""
    try:
        ayar = ayar_oku(sd)
        if mod(ayar) == "kapali" or ayar.get("okuma_notu") is False:
            return ""
        aralik = kismi_aralik(arac, girdi, cwd, int(ayar.get("satir_sayimi_bayt", 2_000_000)))
        if not aralik:
            return ""
        yol = str(girdi.get("file_path") or "")
        if sd and oid and _gorulen(sd, str(oid), os.path.join(cwd or os.getcwd(), yol)):
            return ""
        ad = os.path.basename(yol) or "dosya"
        bit = str(aralik[1]) if aralik[1] else "son"
        metin = str(ayar.get("not_metni") or "").format(ad=ad, bas=aralik[0], bit=bit)
        return metin[: int(ayar.get("not_azami", 220))]
    except Exception:
        return ""


def _aramali(cagrilar, ayar: dict) -> bool:
    araclar = set(ayar.get("arama_araclari") or [])
    kaliplar = [re.compile(k, re.I) for k in (ayar.get("arama_komut_kaliplari") or [])]
    for ad, g in cagrilar:
        if ad in araclar:
            return True
        komut = str((g or {}).get("command") or "") if isinstance(g, dict) else ""
        if komut and any(k.search(komut) for k in kaliplar):
            return True
    return False


def _cumleler(yanit: str):
    for parca in re.split(r"(?<=[.!?])\s+|\n+", yanit or ""):
        p = parca.strip()
        if p:
            yield p


def tur_degerlendir(tur: dict, ayar: dict, rx=None) -> dict | None:
    """Bulgu {cumle, sozcuk, okuma} ya da None. Koşul: turda en az bir Read, hepsi kısmi, arama yok, yanıtta kapsam
    sözcüğü + backtick kod adı aynı cümlede."""
    cagrilar = tur.get("cagrilar") or []
    okumalar = [g for ad, g in cagrilar if ad == "Read"]
    if not okumalar or _aramali(cagrilar, ayar):
        return None
    # transkriptte dosya satır sayısı bilinmez: girdide offset/limit varsa kısmi
    if not all(isinstance(g, dict) and (g.get("offset") or g.get("limit")) for g in okumalar):
        return None
    rx = rx or kapsam_rx()
    if rx is None:
        return None
    import plan_dogrulama as PD
    for c in _cumleler(tur.get("yanit") or ""):
        if not _KOD.search(c):
            continue
        s = PD.kapsam_sozcugu(c, rx)
        if s:
            return {"cumle": c[:240], "sozcuk": s, "okuma": len(okumalar)}
    return None


def degerlendir(transcript_path, sd=None) -> dict | None:
    try:
        ayar = ayar_oku(sd)
        if mod(ayar) == "kapali":
            return None
        import kanit_olcum as K
        tur = K.son_tur(transcript_path, int(ayar.get("kuyruk_bayt", 2_000_000)))
        return tur_degerlendir(tur, ayar) if tur else None
    except Exception:
        return None


def olc(dosyalar, sd=None, ornek: int = 20) -> dict:
    """Gerçek dökümlerde isabet sayımı: {transkript, tur, kismi_tur, bulgu, ornekler[]}."""
    import kanit_olcum as K
    ayar, rx = ayar_oku(sd), kapsam_rx()
    say = {"transkript": 0, "tur": 0, "kismi_tur": 0, "bulgu": 0, "ornekler": []}
    for yol in dosyalar:
        say["transkript"] += 1
        try:
            for tur in K.turlar(yol):
                say["tur"] += 1
                if any(ad == "Read" and isinstance(g, dict) and (g.get("offset") or g.get("limit"))
                       for ad, g in tur.get("cagrilar") or []):
                    say["kismi_tur"] += 1
                b = tur_degerlendir(tur, ayar, rx)
                if b:
                    say["bulgu"] += 1
                    if len(say["ornekler"]) < ornek:
                        say["ornekler"].append(dict(b, transkript=os.path.basename(yol)))
        except Exception:
            continue
    return say
