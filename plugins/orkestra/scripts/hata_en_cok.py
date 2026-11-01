"""En çok tekrarlanan hatalar (ADR-0035): kaynakları OKUMA ANINDA imzaya göre birleştirir; hiçbir şey yazmaz.

Kaynaklar: hata.jsonl (hook, cli, ozet), gunluk.jsonl tur=hook-hatasi (hata.jsonl'de karşılığı olmayan eski satırlar),
gunluk.jsonl tur=kural_ihlal ve kart retleri (analitik.ret_kayitlari: kural_aday ile aynı tek ret kuralı).
Satır: {imza, kaynak, sayi, son_zaman, ornek}; `arac` satırı ayrıca `durum` taşır (acik | cozuldu | yeniden_acildi, ADR-0141). Kart imzası kart:<sınıf>:<neden>, kural imzası kural:<kural>.
"""
from __future__ import annotations

import datetime
import json
import os
import re

import ork_lib as L
import hata_kayit as HK

KAYNAKLAR = ("hook", "cli", "ozet", "kart", "kural", "davranis", "arac")
SAYILAN = ("hook", "cli", "ozet", "davranis", "arac")   # hata.jsonl'den okunan kaynaklar
KOK_DURUM_DOSYA = "kok_durum.json"
DURUM_ETIKET = {"acik": "açık", "cozuldu": "çözüldü", "yeniden_acildi": "yeniden açıldı"}
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


def birlestir(sd: str, gun=0, kaynak: str | None = None, kural_haric: bool = False) -> list[dict]:
    """Kaynakları imzaya göre toplar; sayıya göre azalan (eşitlikte imza) satır listesi. gun: son N takvim günü (0 = tümü).
    kural_haric: kaynak verilmemişken kural ihlallerini dışlar (CLI varsayılanı; kural bir hata değil uyum sayacıdır)."""
    esik = L.gun_baslangici(gun) if gun else None

    def pencerede(z) -> bool:
        if esik is None:
            return True
        t = _an(z)
        return bool(t and t >= esik)

    sayim: dict = {}
    hatalar = _dict(L.jsonl_oku(os.path.join(sd, HK.DOSYA)))
    gunluk = _dict(L.jsonl_oku(os.path.join(sd, "gunluk.jsonl")))
    if kaynak is None or kaynak in SAYILAN:  # davranis: ajanın kod dışı hataları (ADR-0037); arac: başarısız araç çağrısı (ADR-0141)
        for h in hatalar:
            k = h.get("kaynak")
            if k in SAYILAN and kaynak in (None, k) and pencerede(h.get("zaman")):
                im = imza_goster(h.get("tur"), h.get("ileti")) if h.get("tur") else h.get("imza") or "?"
                _topla(sayim, k, im, h.get("zaman"), h.get("ileti"))
    if kaynak in (None, "hook"):
        for g in _hook_eski_satirlar(gunluk, hatalar):
            if pencerede(g.get("zaman")):
                tur, _, ileti = str(g.get("hata") or "").partition(": ")
                _topla(sayim, "hook", imza_goster(tur, ileti), g.get("zaman"), g.get("hata"))
    if kaynak == "kural" or (kaynak is None and not kural_haric):
        for g in gunluk:
            if g.get("tur") == "kural_ihlal" and pencerede(g.get("zaman")):
                _topla(sayim, "kural", f"kural:{g.get('kural') or '?'}", g.get("zaman"), g.get("dosya") or g.get("mod"))
    if kaynak in (None, "kart"):
        import analitik as AN
        for k, d, sinif, _bas, kod, _kok in AN.ret_kayitlari(L.kartlar(sd, derin=False)):
            if pencerede(d.get("zaman")):
                _topla(sayim, "kart", f"kart:{sinif}:{kod}", d.get("zaman"), k.get("id"))
    satirlar = sorted(sayim.values(), key=lambda r: (-r["sayi"], r["imza"], r["kaynak"]))
    cozumler = kok_durum_oku(sd)
    for r in satirlar:
        if r["kaynak"] == "arac":
            r["durum"] = durum_bul(cozumler, r["imza"], r["son_zaman"])
    return satirlar


def kok_durum_oku(sd: str) -> dict:
    """{imza: {"zaman": çözüm anı}}; dosya yok ya da bozuksa boş sözlük."""
    try:
        with open(os.path.join(sd, KOK_DURUM_DOSYA), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def durum_bul(cozumler: dict, imza: str, son_zaman: str) -> str:
    """acik: çözüm kaydı yok; cozuldu: son tekrar çözümden önce ya da aynı an; yeniden_acildi: çözümden sonra yeni satır var."""
    kayit = cozumler.get(imza)
    z = kayit.get("zaman") if isinstance(kayit, dict) else None
    if not z:
        return "acik"
    return "cozuldu" if str(son_zaman or "") <= str(z) else "yeniden_acildi"


def coz(sd: str, imza: str) -> bool:
    """İmzayı çözüldü işaretler (şimdiki an); hata.jsonl'e dokunmaz. Yazılamazsa False."""
    cozumler = kok_durum_oku(sd)
    cozumler[imza] = {"zaman": L.simdi()}
    try:
        L.atomik_yaz(os.path.join(sd, KOK_DURUM_DOSYA), json.dumps(cozumler, ensure_ascii=False, indent=1))
        return True
    except Exception:  # noqa: BLE001
        return False


def satir_metni(r: dict) -> str:
    durum = f" [{DURUM_ETIKET.get(r['durum'], r['durum'])}]" if r.get("durum") else ""
    return f"{r['sayi']:>4}  [{r['kaynak']}] {r['imza']}  (son {r['son_zaman'][:16].replace('T', ' ')}){durum}"


def esik_satiri(sd: str, gun: int = UYARI_GUN, esik: int = UYARI_ESIK) -> str:
    """SessionStart uyarısı: son `gun` günde aynı imzadan `esik` ve üzeri varsa tek satır, yoksa ''. Asla istisna fırlatmaz.
    Kural ihlalleri (gölge kipte sürekli üretilir) uyarıya girmez; hata kaynakları (hook, cli, ozet, kart) girer."""
    try:
        for r in birlestir(sd, gun):
            if r["kaynak"] != "kural" and r.get("durum") != "cozuldu" and r["sayi"] >= esik:
                son = f" {r['sayi']} kez (orkestra hata en-cok)"
                ad = f"HATA: {r['imza']}"
                return ad[:max(0, UYARI_EN_COK - len(son))] + son
    except Exception:  # noqa: BLE001
        pass
    return ""
