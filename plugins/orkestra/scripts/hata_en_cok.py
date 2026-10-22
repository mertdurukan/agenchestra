"""En çok tekrarlanan hatalar (ADR-0035): kaynakları OKUMA ANINDA imzaya göre birleştirir; hiçbir şey yazmaz.

Kaynaklar: hata.jsonl (hook, cli, ozet), gunluk.jsonl tur=hook-hatasi (hata.jsonl'de karşılığı olmayan eski satırlar),
gunluk.jsonl tur=kural_ihlal ve kart retleri (analitik.ret_kayitlari: kural_aday ile aynı tek ret kuralı).
Satır: {imza, kaynak, sayi, son_zaman, ornek}. Kart imzası kart:<sınıf>:<neden>, kural imzası kural:<kural>.
"""
from __future__ import annotations

import datetime
import os
import re

import ork_lib as L
import hata_kayit as HK

KAYNAKLAR = ("hook", "cli", "ozet", "kart", "kural")
ESLESME_SN = 10          # gunluk hook-hatasi ile hata.jsonl satırı aynı olay sayılma farkı
UYARI_GUN = 7
UYARI_ESIK = 3
UYARI_EN_COK = 120
_ERRNO = re.compile(r"\b(Errno|WinError) (\d+)")
_ERRNO_GERI = re.compile(r"\b(Errno|WinError) ~([a-j]+)")


def imza_goster(tur: str, ileti: str) -> str:
    """HK.imza ile aynı, yalnız [Errno 22] / [WinError 5] numarası korunur (farklı işletim sistemi hataları birleşmesin)."""
    ileti = _ERRNO.sub(lambda m: f"{m.group(1)} ~" + "".join(chr(97 + int(c)) for c in m.group(2)), str(ileti or ""))
    s = HK.imza(tur, ileti)
    return _ERRNO_GERI.sub(lambda m: f"{m.group(1)} " + "".join(str(ord(c) - 97) for c in m.group(2)), s)


def _an(z):
    try:
        t = datetime.datetime.fromisoformat(str(z or "").replace("Z", "+00:00"))
        return t if t.tzinfo else t.astimezone()
    except ValueError:
        return None


def _dict(x) -> list[dict]:
    return [r for r in x if isinstance(r, dict)]


def _topla(sayim: dict, kaynak: str, imza: str, zaman, ornek) -> None:
    g = sayim.setdefault((kaynak, imza), {"imza": imza, "kaynak": kaynak, "sayi": 0, "son_zaman": "", "ornek": ""})
    g["sayi"] += 1
    z = str(zaman or "")
    if z >= g["son_zaman"] or not g["ornek"]:
        g["son_zaman"] = max(z, g["son_zaman"])
        g["ornek"] = str(ornek or "")[:200]


def _hook_eski_satirlar(gunluk: list[dict], hata_satirlari: list[dict]) -> list[dict]:
    """gunluk hook-hatasi satırlarından hata.jsonl'de karşılığı (aynı olay, ±ESLESME_SN) olmayanlar; çift sayım olmaz."""
    adaylar = [(_an(h.get("zaman")), (h.get("baglam") or {}).get("yer") if isinstance(h.get("baglam"), dict) else None)
               for h in hata_satirlari if h.get("kaynak") == "hook"]
    kullanilan = [False] * len(adaylar)
    out = []
    for g in gunluk:
        if g.get("tur") != "hook-hatasi":
            continue
        t = _an(g.get("zaman"))
        eslesti = False
        for i, (ht, yer) in enumerate(adaylar):
            if not kullanilan[i] and t and ht and yer == g.get("olay") and abs((t - ht).total_seconds()) <= ESLESME_SN:
                kullanilan[i] = eslesti = True
                break
        if not eslesti:
            out.append(g)
    return out


def birlestir(sd: str, gun=0, kaynak: str | None = None) -> list[dict]:
    """Kaynakları imzaya göre toplar; sayıya göre azalan (eşitlikte imza) satır listesi. gun: son N takvim günü (0 = tümü)."""
    esik = L.gun_baslangici(gun) if gun else None

    def pencerede(z) -> bool:
        if esik is None:
            return True
        t = _an(z)
        return bool(t and t >= esik)

    sayim: dict = {}
    hatalar = _dict(L.jsonl_oku(os.path.join(sd, HK.DOSYA)))
    gunluk = _dict(L.jsonl_oku(os.path.join(sd, "gunluk.jsonl")))
    if kaynak in (None, "hook", "cli", "ozet"):
        for h in hatalar:
            k = h.get("kaynak")
            if k in ("hook", "cli", "ozet") and kaynak in (None, k) and pencerede(h.get("zaman")):
                _topla(sayim, k, h.get("imza") or imza_goster(h.get("tur"), h.get("ileti")),
                       h.get("zaman"), h.get("ileti"))
    if kaynak in (None, "hook"):
        for g in _hook_eski_satirlar(gunluk, hatalar):
            if pencerede(g.get("zaman")):
                tur, _, ileti = str(g.get("hata") or "").partition(": ")
                _topla(sayim, "hook", imza_goster(tur, ileti), g.get("zaman"), g.get("hata"))
    if kaynak in (None, "kural"):
        for g in gunluk:
            if g.get("tur") == "kural_ihlal" and pencerede(g.get("zaman")):
                _topla(sayim, "kural", f"kural:{g.get('kural') or '?'}", g.get("zaman"), g.get("dosya") or g.get("mod"))
    if kaynak in (None, "kart"):
        import analitik as AN
        for k, d, sinif, _bas, kod, _kok in AN.ret_kayitlari(L.kartlar(sd, derin=False)):
            if pencerede(d.get("zaman")):
                _topla(sayim, "kart", f"kart:{sinif}:{kod}", d.get("zaman"), k.get("id"))
    return sorted(sayim.values(), key=lambda r: (-r["sayi"], r["imza"], r["kaynak"]))


def satir_metni(r: dict) -> str:
    return f"{r['sayi']:>4}  [{r['kaynak']}] {r['imza']}  (son {r['son_zaman'][:16].replace('T', ' ')})"


def esik_satiri(sd: str, gun: int = UYARI_GUN, esik: int = UYARI_ESIK) -> str:
    """SessionStart uyarısı: son `gun` günde aynı imzadan `esik` ve üzeri varsa tek satır, yoksa ''. Asla istisna fırlatmaz.
    Kural ihlalleri (gölge kipte sürekli üretilir) uyarıya girmez; hata kaynakları (hook, cli, ozet, kart) girer."""
    try:
        for r in birlestir(sd, gun):
            if r["kaynak"] != "kural" and r["sayi"] >= esik:
                son = f" {r['sayi']} kez (orkestra hata en-cok)"
                ad = f"HATA: {r['imza']}"
                return ad[:max(0, UYARI_EN_COK - len(son))] + son
    except Exception:  # noqa: BLE001
        pass
    return ""
