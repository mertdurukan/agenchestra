"""Kod kartı mevcut-durum notu doğrulaması (saf fonksiyon).

İşçi kodu değiştirmeden önce ilgili mevcut kodu okuduğunu ve ne yaptığını anladığını kanıtlar.
Sözleşme: {"okunan": [{"dosya": str, "satir": int>=1, "alinti": str>=6, "rol": str 10-300}] (en az 1),
           "yetenekler": [str] (en az 1: mevcut kodun yaptığı şeyler),
           "karar": "degistir" | "ekle" | "yeni",
           "neden": str 20-400,
           "etkilenenler": [str] (çağıranlar, testler; boş olabilir, anahtar zorunlu)}

Kanıt deterministiktir: dosya var, satır dosya içinde, `alinti` o satırın ±2 satırında geçer (okumadan uydurulamaz).
karar degistir/ekle ise okunan dosyalardan en az biri kartın yazma alanında olmalıdır (değiştirilecek kod okunmuştur).
"""
from __future__ import annotations

import os
import re

MIN_NEDEN, MAX_NEDEN = 20, 400
MIN_ROL, MAX_ROL = 10, 300
MIN_ALINTI = 6
PENCERE = 2
KARARLAR = ("degistir", "ekle", "yeni")


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def _coz(dosya: str, kokler: list[str]) -> str | None:
    """Dosyanın var olan mutlak yolu (göreli yol sırayla köklerde aranır); yoksa None."""
    if os.path.isabs(dosya):
        return dosya if os.path.isfile(dosya) else None
    for k in kokler:
        aday = os.path.join(k, dosya)
        if os.path.isfile(aday):
            return aday
    return None


def _satirlar(yol: str) -> list[str] | None:
    try:
        with open(yol, encoding="utf-8", errors="replace") as f:
            return f.read().splitlines()
    except OSError:
        return None


def _okunan_dogrula(i: int, o, kokler: list[str], hatalar: list, cozulen: list) -> None:
    on = f"okunan[{i}]"
    if not isinstance(o, dict):
        hatalar.append(f"{on}: nesne olmalı")
        return
    dosya, satir, alinti, rol = o.get("dosya"), o.get("satir"), o.get("alinti"), o.get("rol")
    if not isinstance(dosya, str) or not dosya.strip():
        hatalar.append(f"{on}.dosya: dolu metin olmalı")
        return
    if isinstance(rol, str) and MIN_ROL <= len(rol.strip()) <= MAX_ROL:
        pass
    else:
        hatalar.append(f"{on}.rol: {MIN_ROL}-{MAX_ROL} karakterlik metin olmalı (dosyanın bu kartla ilgili rolü)")
    yol = _coz(dosya.strip(), kokler)
    if yol is None:
        hatalar.append(f"{on}.dosya: bulunamadı ({dosya})")
        return
    cozulen.append(yol)
    if isinstance(satir, bool) or not isinstance(satir, int) or satir < 1:
        hatalar.append(f"{on}.satir: 1 veya büyük tamsayı olmalı")
        return
    if not isinstance(alinti, str) or len(_norm(alinti)) < MIN_ALINTI:
        hatalar.append(f"{on}.alinti: en az {MIN_ALINTI} karakter (satırdan birebir)")
        return
    satirlar = _satirlar(yol)
    if satirlar is None:
        hatalar.append(f"{on}.dosya: okunamadı ({dosya})")
        return
    if satir > len(satirlar):
        hatalar.append(f"{on}.satir: {satir} > dosya satır sayısı {len(satirlar)} ({dosya})")
        return
    pencere = _norm(" ".join(satirlar[max(0, satir - 1 - PENCERE):satir + PENCERE]))
    if _norm(alinti) not in pencere:
        hatalar.append(f"{on}.alinti: {dosya}:{satir} çevresinde (±{PENCERE} satır) bulunamadı; satırı oku ve birebir yaz")


def dogrula(nesne, kokler: list[str], yazma_eslesir=None) -> tuple[bool, list[str]]:
    """(tamam, hatalar). `kokler`: göreli dosya yollarının aranacağı kökler (çalışma ağacı, proje).
    `yazma_eslesir(mutlak_yol) -> bool`: dosya kartın yazma alanında mı; None ise yazma alanı kuralı atlanır."""
    if not isinstance(nesne, dict):
        return False, ["mevcut durum notu bir JSON nesnesi olmalı"]
    hatalar: list[str] = []
    cozulen: list[str] = []
    okunan = nesne.get("okunan")
    if not isinstance(okunan, list) or not okunan:
        hatalar.append("okunan: en az 1 öğeli liste olmalı (ilgili mevcut kod okunmadan not geçmez)")
    else:
        for i, o in enumerate(okunan):
            _okunan_dogrula(i, o, kokler, hatalar, cozulen)
    yet = nesne.get("yetenekler")
    if not isinstance(yet, list) or not yet:
        hatalar.append("yetenekler: en az 1 öğeli liste olmalı (mevcut kodun yaptığı şeyler)")
    else:
        for i, y in enumerate(yet):
            if not isinstance(y, str) or len(y.strip()) < MIN_ROL:
                hatalar.append(f"yetenekler[{i}]: en az {MIN_ROL} karakterlik metin olmalı")
    karar = nesne.get("karar")
    if karar not in KARARLAR:
        hatalar.append(f"karar: {' | '.join(KARARLAR)} olmalı")
    neden = nesne.get("neden")
    if not isinstance(neden, str):
        hatalar.append("neden: metin olmalı")
    elif not (MIN_NEDEN <= len(neden.strip()) <= MAX_NEDEN):
        hatalar.append(f"neden: {MIN_NEDEN}-{MAX_NEDEN} karakter olmalı (şimdi {len(neden.strip())})")
    et = nesne.get("etkilenenler")
    if not isinstance(et, list):
        hatalar.append("etkilenenler: liste olmalı (çağıranlar, testler; boş olabilir)")
    else:
        for i, x in enumerate(et):
            if not isinstance(x, str) or not x.strip():
                hatalar.append(f"etkilenenler[{i}]: dolu metin olmalı")
    if karar in ("degistir", "ekle") and yazma_eslesir is not None and cozulen and not hatalar:
        if not any(yazma_eslesir(y) for y in cozulen):
            hatalar.append(f"karar={karar}: okunan dosyalardan hiçbiri kartın yazma alanında değil; "
                           "değiştireceğin/ekleyeceğin mevcut dosyayı da oku")
    return not hatalar, hatalar
