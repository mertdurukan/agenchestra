"""Hafıza düzeltme notu tekrarı denetimi.

Düzeltilen bir iddia, hafızada kaynak kayıtta bir kez yeniden yazılır; aynı düzeltme notu birden çok yere eklenmez.
Bu modül birebir aynı (normalleştirilmiş) düzeltme notunun birden çok kez geçmesini bulur:

- `tara(klasor)`: klasördeki hafıza `.md` dosyalarında tekrar eden notlar (salt okunur; CLI `perspektif duzeltme-tara`).
- `yazim_ihlali(yol, onceki, sonraki)`: bir yazımın tekrarı artırıp artırmadığı (PreToolUse kapısı).

Not: parantezli ya da köşeli (`[[bağlantı]]` hariç) bir parça, `ayarlar/hafiza_duzeltme.json` `isaret_kokleri`nden birini
taşıyorsa ve en az `min_uzunluk` karakterse düzeltme notudur. Saf Python, model çağırmaz.
"""
from __future__ import annotations

import glob
import json
import os
import re

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VARSAYILAN = {"mod": "ihlal", "esik": 2, "min_uzunluk": 12,
              "isaret_kokleri": ["düzeltme", "düzeltil", "düzeltmiş", "yanlıştı", "yanlış çıktı", "çürütüldü",
                                 "correction", "corrected", "retracted"],
              "hafiza_yolu": r"/\.claude/projects/[^/]+/memory/(?:.+/)?[^/]+\.md$"}
MODLAR = ("ihlal", "golge", "kapali")

_PAREN = re.compile(r"\(([^()\n]*)\)")
_KOSELI = re.compile(r"(?<!\[)\[([^\[\]\n]+)\](?!\])")


def acik() -> bool:
    return os.environ.get("ORKESTRA_HAFIZA_DUZELTME") != "0"


def ayar() -> dict:
    veri = dict(VARSAYILAN)
    try:
        with open(os.path.join(KOK, "ayarlar", "hafiza_duzeltme.json"), encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict):
            veri.update({k: d[k] for k in VARSAYILAN if k in d})
    except (OSError, ValueError):
        pass
    if veri["mod"] not in MODLAR:
        veri["mod"] = "ihlal"
    return veri


def hafiza_yolu_mu(yol: str, a: dict | None = None) -> bool:
    """`.claude/projects/<ad>/memory/**/*.md` mi (yol ayraçları normalleştirilir)."""
    d = (a or ayar()).get("hafiza_yolu") or VARSAYILAN["hafiza_yolu"]
    try:
        return bool(re.search(d, os.path.abspath(yol).replace("\\", "/"), re.I))
    except re.error:
        return False


def _norm(s: str) -> str:
    s = s.replace("İ", "i").replace("I", "ı").lower()
    s = re.sub(r"\s+", " ", s)
    return s.strip(" \t.,;:!-–—*_`")


def notlar(metin: str, a: dict | None = None) -> list[tuple[int, str]]:
    """[(satır no (1 tabanlı), normalleştirilmiş not)]: işaret kökü taşıyan parantezli/köşeli parçalar."""
    a = a or ayar()
    kokler = [k.lower() for k in a["isaret_kokleri"]]
    en_az = int(a["min_uzunluk"])
    cikti = []
    for no, satir in enumerate((metin or "").splitlines(), 1):
        for rx in (_PAREN, _KOSELI):
            for m in rx.finditer(satir):
                n = _norm(m.group(1))
                if len(n) >= en_az and any(k in n for k in kokler):
                    cikti.append((no, n))
    return cikti


def _sayim(metinler, a: dict) -> dict[str, int]:
    toplam: dict[str, int] = {}
    for m in metinler:
        for _, n in notlar(m, a):
            toplam[n] = toplam.get(n, 0) + 1
    return toplam


def tekrarlar(metinler: dict[str, str], a: dict | None = None) -> list[dict]:
    """metinler: {yol: metin}. Dönüş: [{not, adet, yerler: [(yol, satır)]}], adet >= esik, çoktan aza."""
    a = a or ayar()
    gruplar: dict[str, list[tuple[str, int]]] = {}
    for yol, metin in metinler.items():
        for no, n in notlar(metin, a):
            gruplar.setdefault(n, []).append((yol, no))
    sonuc = [{"not": n, "adet": len(y), "yerler": y} for n, y in gruplar.items() if len(y) >= int(a["esik"])]
    return sorted(sonuc, key=lambda g: (-g["adet"], g["not"]))


def klasor_metinleri(klasor: str) -> dict[str, str]:
    metinler = {}
    for yol in sorted(glob.glob(os.path.join(glob.escape(klasor), "**", "*.md"), recursive=True)):
        try:
            with open(yol, encoding="utf-8", errors="replace") as f:
                metinler[os.path.abspath(yol)] = f.read()
        except OSError:
            pass
    return metinler


def tara(klasor: str, a: dict | None = None) -> list[dict]:
    return tekrarlar(klasor_metinleri(klasor), a)


def yazim_ihlali(yol: str, onceki: str, sonraki: str, klasor: str | None = None, a: dict | None = None) -> str | None:
    """Yazım, birebir aynı düzeltme notunun adedini artırıp eşiğe ulaştırıyorsa ileti, yoksa None.

    `onceki`/`sonraki`: hedef dosyanın yazımdan önceki ve sonraki metni. Klasördeki öteki dosyalar diskten okunur."""
    a = a or ayar()
    if a["mod"] == "kapali" or not hafiza_yolu_mu(yol, a):
        return None
    hedef = os.path.abspath(yol)
    digerleri = [m for p, m in klasor_metinleri(klasor or os.path.dirname(hedef)).items() if p != hedef]
    sabit = _sayim(digerleri, a)
    once, sonra = _sayim([onceki], a), _sayim([sonraki], a)
    for n, adet in sorted(sonra.items(), key=lambda kv: -kv[1]):
        yeni, eski = adet + sabit.get(n, 0), once.get(n, 0) + sabit.get(n, 0)
        if yeni >= int(a["esik"]) and yeni > eski:
            return (f"hafızada birebir aynı düzeltme notu {yeni} kez olur: «{n[:90]}». Düzeltilen iddia kaynak kayıtta "
                    "olgu cümlesi olarak bir kez yeniden yazılır; diğer geçişlerde olguyu doğru yaz ya da cümleyi silip "
                    "[[kaynak]] bağlantısı ver (eski yanlış ifade tarihçe olarak en çok bir yerde, bağlantıyla). "
                    "Bilerek tekrarlıyorsan notun sözcüklerini farklılaştır ya da ORKESTRA_HAFIZA_DUZELTME=0 ile kapat.")
    return None


def yazim_sonrasi(arac: str, girdi: dict, onceki: str) -> str | None:
    """Write/Edit/MultiEdit aracının uygulanmış sonucu (dosya metni). Uygulanamıyorsa (eşleşme yok) None: araç kendi hatasını verir."""
    if arac == "Write":
        c = girdi.get("content")
        return c if isinstance(c, str) else None
    if arac == "Edit":
        parcalar = [girdi]
    elif arac == "MultiEdit":
        parcalar = girdi.get("edits") or []
    else:
        return None
    metin = onceki
    for p in parcalar:
        eski, yeni = p.get("old_string"), p.get("new_string")
        if not isinstance(eski, str) or not isinstance(yeni, str):
            return None
        if eski == "":  # boş old_string: dosya yoksa/boşsa yeni metin dosyanın tamamıdır
            metin = yeni if not metin else metin
            continue
        if eski not in metin:
            return None
        metin = metin.replace(eski, yeni) if p.get("replace_all") else metin.replace(eski, yeni, 1)
    return metin
