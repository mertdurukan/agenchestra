"""Serbest yol anmaları için varlık denetimi: plan.md ve mevcut_durum.md içindeki `backtick` yollar diskte var mı.

Saf Python, model çağırmaz. Yalnız uyarı üretir; plan kararını değiştirmez (oluşturulacak dosya adı yanlış alarm verir).

Atlananlar: kod çiti ve yorum içi, `Kanıt:` satırları (plan_dogrulama zaten sınar), joker ya da yer tutucu içeren desenler
(`*`, `<>`, `{}`, `$`), URL, boşluklu ifade, ayırıcısız ad (`hook.py`) ve "yeni" işaretli satırlar (yazılır, eklenir,
oluşturulur, üretilir, silinir).
"""
from __future__ import annotations

import os
import re

_YORUM = re.compile(r"<!--.*?-->", re.S)
_CIT = re.compile(r"^\s*(```|~~~)")
_KOD = re.compile(r"`([^`\n]+)`")
_KANIT = re.compile(r"^\s*[-*]\s+Kanıt:")
_YENI = re.compile(r"\b(yeni|yazılır|eklenir|eklemesi|oluşturul\w*|üretil\w*|silinir|silinecek)\b", re.I)
_YER_TUTUCU = re.compile(r"[*<>{}$|?]|://|\s")
_UZANTI = re.compile(r"\.[A-Za-z0-9]{1,5}$")
_SATIR_SONEKI = re.compile(r":\d+(-\d+)?$")


def temiz_satirlar(metin: str) -> list[str]:
    """Yorum ve kod çiti içini boşaltır; satır numaraları korunur."""
    metin = _YORUM.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), metin.replace("\r\n", "\n"))
    cikti, cit = [], False
    for s in metin.split("\n"):
        if _CIT.match(s):
            cit = not cit
            cikti.append("")
        else:
            cikti.append("" if cit else s)
    return cikti


def yol_adayi(parca: str) -> str | None:
    """Backtick içeriği denetlenecek bir yol mu; öyleyse sade yolu (satır soneki atılmış) döndürür."""
    p = _SATIR_SONEKI.sub("", parca.strip())
    if not p or _YER_TUTUCU.search(p):
        return None
    if "/" not in p and "\\" not in p:
        return None
    if p.startswith("-"):
        return None
    if not (_UZANTI.search(p) or p.endswith(("/", "\\"))):
        return None
    return p


def _var_mi(yol: str, kokler: list[str]) -> bool:
    if os.path.isabs(yol):
        return os.path.exists(yol)
    return any(os.path.exists(os.path.join(k, yol)) for k in kokler)


def denetle_metin(metin: str, kokler: list[str]) -> list[dict]:
    """[{satir (1 tabanlı), yol, var}] - tekrar eden yol bir kez sayılır."""
    sonuc, gorulen = [], set()
    for i, s in enumerate(temiz_satirlar(metin), start=1):
        if not s.strip() or _KANIT.match(s) or _YENI.search(s):
            continue
        for m in _KOD.finditer(s):
            yol = yol_adayi(m.group(1))
            if yol is None or yol in gorulen:
                continue
            gorulen.add(yol)
            sonuc.append({"satir": i, "yol": yol, "var": _var_mi(yol, kokler)})
    return sonuc


def denetle_dosyalar(dosyalar: list[str], kokler: list[str]) -> list[dict]:
    """Her dosya için denetle_metin; sonuca 'dosya' (taban ad) eklenir. Okunamayan dosya atlanır."""
    sonuc = []
    for d in dosyalar:
        try:
            with open(d, encoding="utf-8", errors="replace") as f:
                metin = f.read()
        except OSError:
            continue
        for k in denetle_metin(metin, kokler):
            k["dosya"] = os.path.basename(d)
            sonuc.append(k)
    return sonuc


def bulunamayanlar(sonuc: list[dict]) -> list[str]:
    return [f"{k['dosya']}:{k['satir']} `{k['yol']}`" for k in sonuc if not k["var"]]
