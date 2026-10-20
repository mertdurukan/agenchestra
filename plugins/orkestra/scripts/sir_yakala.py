"""Sohbette yazılan açık atamayı (SERVIS_ANAHTAR=değer) kimlik klasörüne yazar (ADR-0011).

Yalnız açık atama tanınır; serbest metin taranmaz. Dönüş ve hata iletileri değer taşımaz.
"""
from __future__ import annotations

import os
import re

import kimlik as K

_SONEKLER = ("KEY", "TOKEN", "SECRET", "PASSWORD", "PASSWD", "PW", "USER", "USERNAME", "EMAIL")
_ATAMA = re.compile(
    r"(?m)^[ \t]*(?:(?P<servis>[A-Za-z][A-Za-z0-9_.-]*)[ \t]*:[ \t]*)?(?:export[ \t]+)?"
    r"(?P<anahtar>[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+)[ \t]*=[ \t]*(?P<deger>\"[^\"\r\n]+\"|'[^'\r\n]+'|[^\s\"']+)[ \t]*$")


def _anahtar_uygun(anahtar: str) -> bool:
    return anahtar.upper().rsplit("_", 1)[-1] in _SONEKLER


def yakala(metin: str) -> list[tuple[str, str, str]]:
    """[(servis, anahtar, değer)]; servis açıkça verilmediyse anahtarın ilk parçasından (küçük harf)."""
    sonuc = []
    for m in _ATAMA.finditer(metin or ""):
        anahtar = m.group("anahtar")
        if not _anahtar_uygun(anahtar):
            continue
        deger = m.group("deger").strip("\"'")
        servis = (m.group("servis") or anahtar.split("_", 1)[0]).lower()
        sonuc.append((servis, anahtar, deger))
    return sonuc


def kaydet(metin: str, proje: str | None = None) -> list[str]:
    """Bulunanları yazar; bağlama gidecek satırları döner (değer içermez)."""
    if os.environ.get("ORKESTRA_SIR_YAKALA", "1") == "0":
        return []
    satirlar = []
    for servis, anahtar, deger in yakala(metin):
        try:
            var = False
            try:
                var = anahtar in K.yukle(servis, proje)
            except K.KimlikHata:
                pass
            K.ekle(servis, anahtar, deger, proje)
            satirlar.append(f"kimlik {'güncellendi' if var else 'kaydedildi'}: {servis}.{anahtar}")
        except K.KimlikHata as e:
            satirlar.append(f"kimlik yazılamadı: {servis}.{anahtar} ({e})")
    return satirlar
