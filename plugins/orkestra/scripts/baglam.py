r"""Dosya yolundan 'Proje/Süreç/Görev' bağlamı çözümü. Yalnız stdlib; projeye özgü ad içermez.

Eşleme dosyası `<durum dizini>/baglam.json` (çalışma alanına özgü):
  {"surum":1, "projeler":[...], "surec_deseni":"^\d{2}_", "gorev_deseni":"^\d{3}-",
   "haric":[...], "dis_kokler":{"<mutlak yol>":"<bağlam>"}}
Eşleme yoksa ya da bozuksa bağlam hep ''.
"""
from __future__ import annotations

import json
import os
import posixpath
import re

AGIRLIK_YAZILAN = 3
AGIRLIK_OKUNAN = 1


def esleme_oku(sd: str) -> dict | None:
    try:
        with open(os.path.join(sd, "baglam.json"), encoding="utf-8-sig") as f:
            d = json.load(f)
    except Exception:
        return None
    return d if isinstance(d, dict) else None


def _duz(yol: str) -> str:
    return str(yol).replace("\\", "/")


def _mutlak_mi(p: str) -> bool:
    return p.startswith("/") or bool(re.match(r"^[A-Za-z]:/", p))


def _alt_yol(kok: str, yol: str) -> str | None:
    """yol, kok'un altındaysa göreli kısmı ('' = kökün kendisi); değilse None. Büyük/küçük harf gözetmez."""
    kok = kok.rstrip("/")
    if yol.casefold() == kok.casefold():
        return ""
    if yol.casefold().startswith(kok.casefold() + "/"):
        return yol[len(kok) + 1:]
    return None


def _desen_uyar(desen, ad: str) -> bool:
    try:
        return bool(desen) and re.search(desen, ad) is not None
    except re.error:
        return False


def yoldan(esleme: dict | None, proje: str | None, yol: str | None) -> str:
    if not esleme or not yol:
        return ""
    try:
        y = posixpath.normpath(_duz(yol))
        rel = None
        if _mutlak_mi(y):
            if proje:
                rel = _alt_yol(posixpath.normpath(_duz(proje)), y)
            if rel is None:
                for kok, deger in (esleme.get("dis_kokler") or {}).items():
                    if _alt_yol(posixpath.normpath(_duz(kok)), y) is not None:
                        return str(deger)
                return ""
        else:
            rel = y
        parcalar = [p for p in rel.split("/") if p and p != "."]
        if not parcalar or parcalar[0] == "..":
            return ""
        projeler = {str(p).casefold(): str(p) for p in esleme.get("projeler") or []}
        ad = projeler.get(parcalar[0].casefold())
        if not ad:
            return ""
        cikti = [ad]
        i = 1
        if len(parcalar) > 1:
            haric = {str(h).casefold() for h in esleme.get("haric") or []}
            p = parcalar[1]
            if p.casefold() in haric:
                return ad
            if len(parcalar) > 2 and _desen_uyar(esleme.get("surec_deseni"), p):
                cikti.append(p)
                i = 2
        if len(parcalar) > i + 1 and _desen_uyar(esleme.get("gorev_deseni"), parcalar[i]):
            cikti.append(parcalar[i])
        return "/".join(cikti)
    except Exception:
        return ""


_GLOB = re.compile(r"[*?\[]")
GOREV_DESENI = r"^\d{3}-"


def klasor_coz(esleme: dict | None, proje: str | None, yol: str | None):
    """Yazma alanı girdisini iş klasörüne çözer → (kök, görev) mutlak yollar ya da None.

    kök: proje[/süreç] klasörü; görev: kök altındaki görev klasörü (gorev_deseni) ya da None.
    Glob parçası ve sonrası atılır (öncesi klasördür). Mutlak yolda önce dis_kokler eşlemesi
    (eşlenen bağlam proje köküne göre kök olur), sonra proje kökü denenir. Çözülmezse None; asla hata vermez.
    """
    if not esleme or not yol or not proje:
        return None
    try:
        proje_d = posixpath.normpath(_duz(os.path.abspath(proje)))
        ham = _duz(str(yol)).strip()
        temiz, glob_var = [], False
        for x in ham.split("/"):
            if _GLOB.search(x):
                glob_var = True
                break
            temiz.append(x)
        if not "".join(temiz):
            return None
        y = posixpath.normpath("/".join(temiz))
        if _mutlak_mi(y):
            eslesen = None
            for kok, deger in (esleme.get("dis_kokler") or {}).items():
                kd = posixpath.normpath(_duz(kok))
                if _alt_yol(kd, y) is not None and (eslesen is None or len(kd) > len(eslesen[0])):
                    eslesen = (kd, str(deger))
            if eslesen:
                parca = [p for p in _duz(eslesen[1]).split("/") if p and p not in (".", "..")]
                if not parca:
                    return None
                return os.path.normpath(os.path.join(proje_d, *parca)), None
            rel = _alt_yol(proje_d, y)
            if rel is None:
                return None
        else:
            rel = y
        parcalar = [p for p in rel.split("/") if p and p != "."]
        if not parcalar or parcalar[0] == "..":
            return None
        son_klasor = (glob_var or ham.endswith("/") or "." not in parcalar[-1]
                      or os.path.isdir(os.path.join(proje_d, *parcalar)))
        dizinler = parcalar if son_klasor else parcalar[:-1]
        if not dizinler:
            return None
        projeler = {str(p).casefold(): str(p) for p in esleme.get("projeler") or []}
        ad = projeler.get(dizinler[0].casefold())
        if not ad:
            return None
        kok = [ad]
        i = 1
        if len(dizinler) > 1:
            haric = {str(h).casefold() for h in esleme.get("haric") or []}
            if dizinler[1].casefold() in haric:
                return os.path.normpath(os.path.join(proje_d, ad)), None
            if _desen_uyar(esleme.get("surec_deseni"), dizinler[1]):
                kok.append(dizinler[1])
                i = 2
        kok_yol = os.path.normpath(os.path.join(proje_d, *kok))
        gorev = None
        if len(dizinler) > i and _desen_uyar(esleme.get("gorev_deseni") or GOREV_DESENI, dizinler[i]):
            gorev = os.path.join(kok_yol, dizinler[i])
        return kok_yol, gorev
    except Exception:
        return None


def coz(esleme: dict | None, proje: str | None, yazilan: list, okunan: list) -> str:
    if not esleme:
        return ""
    oy: dict[str, list] = {}  # baglam -> [oy, son sıra]
    sira = 0
    for liste, agirlik in ((yazilan or [], AGIRLIK_YAZILAN), (okunan or [], AGIRLIK_OKUNAN)):
        for yol in liste:
            sira += 1
            b = yoldan(esleme, proje, yol)
            if not b:
                continue
            k = oy.setdefault(b, [0, 0])
            k[0] += agirlik
            k[1] = sira
    if not oy:
        return ""
    return max(oy.items(), key=lambda kv: (kv[1][0], kv[0].count("/"), kv[1][1]))[0]
