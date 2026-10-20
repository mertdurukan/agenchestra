"""Sohbette yazılan sırrı kimlik klasörüne yazar (ADR-0011, serbest metin genişlemesi ADR-0020).

İki yol vardır:
- Açık atama (`SERVIS_ANAHTAR=değer`): servis ve anahtar adı mesajda yazılıdır; mevcut kayıt güncellenir.
- Serbest metin: parolalı bağlantı dizesi, bilinen belirteç biçimleri ve "parola: değer" satırı. Servis adı
  mesajdaki kısa etiketten (`Cosmos yusuf` → `cosmos_yusuf`) ya da şema/belirteç önekinden türetilir.
  Mevcut kayıt ezilmez: değer aynıysa dokunulmaz, farklıysa yeni ad önerilir.

Kalıplar kodda durmaz: `ayarlar/sir_kaliplari.json`. Dönüş ve hata iletileri değer taşımaz.
`ORKESTRA_SIR_YAKALA=0` yakalamayı kapatır.
"""
from __future__ import annotations

import json
import os
import re

import kimlik as K

_KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AYAR_YOL = os.path.join(_KOK, "ayarlar", "sir_kaliplari.json")
_TR = str.maketrans("ıİğĞüÜşŞöÖçÇ", "iigguussoocc")

_SONEKLER = ("KEY", "TOKEN", "SECRET", "PASSWORD", "PASSWD", "PW", "USER", "USERNAME", "EMAIL")
_ATAMA = re.compile(
    r"(?m)^[ \t]*(?:(?P<servis>[A-Za-z][A-Za-z0-9_.-]*)[ \t]*:[ \t]*)?(?:export[ \t]+)?"
    r"(?P<anahtar>[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+)[ \t]*=[ \t]*(?P<deger>\"[^\"\r\n]+\"|'[^'\r\n]+'|[^\s\"']+)[ \t]*$")

UYARI = ("kimlik değeri sohbet kaydında kaldı: yanıtta, belgede ya da hafızada değeri tekrar etme, "
         "yalnız servis.ANAHTAR adını an; parolayı yenilemek istersen kullanıcıya söyle")


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


def _ayar() -> dict:
    try:
        with open(AYAR_YOL, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _etiket_adayi(satir: str, ayar: dict) -> str | None:
    """Satır kısa bir ad mı (en çok N sözcük, harf/rakam)? Evetse temizlenmiş halini döner."""
    s = satir.strip().rstrip(":= ").strip()
    if not s or "://" in s:
        return None
    sozcukler = s.split()
    if len(sozcukler) > int(ayar.get("en_cok_sozcuk", 3)):
        return None
    desen = re.compile(ayar.get("sozcuk_deseni", r"^[^\W_]+$"))
    en_uzun = int(ayar.get("en_cok_sozcuk_uzunlugu", 24))
    if any(len(w) > en_uzun or not desen.match(w) for w in sozcukler):
        return None
    return " ".join(sozcukler)


def _ad(etiket: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", etiket.translate(_TR).lower()).strip("_")


def _etiket_bul(satirlar: list[str], bas_satir: int, bit_satir: int, sutun: int, kullanilan: set, ayar: dict) -> str | None:
    """Aday sıra: aynı satırda önek, hemen üstteki satır, altta ilk dolu satır (arada boş satır olabilir)."""
    onek = _etiket_adayi(satirlar[bas_satir][:sutun], ayar) if sutun else None
    if onek:
        return onek
    if bas_satir > 0 and (bas_satir - 1) not in kullanilan:
        ust = _etiket_adayi(satirlar[bas_satir - 1], ayar)
        if ust:
            kullanilan.add(bas_satir - 1)
            return ust
    j = bit_satir + 1
    while j < len(satirlar) and not satirlar[j].strip():
        j += 1
    if j < len(satirlar) and j not in kullanilan:
        alt = _etiket_adayi(satirlar[j], ayar)
        if alt:
            kullanilan.add(j)
            return alt
    return None


def _kalip(ayar: dict, bolum: str, alan: str = "desen") -> re.Pattern | None:
    try:
        return re.compile(ayar[bolum][alan])
    except Exception:
        return None


def yakala_serbest(metin: str) -> list[dict]:
    """Serbest metindeki sırlar: [{servis, anahtar, deger, tur}]; ad etiketten ya da önekten türetilir."""
    metin = (metin or "").replace("\r\n", "\n")
    ayar = _ayar()
    if not metin or not ayar:
        return []
    satirlar = metin.split("\n")
    baslar = [0]
    for s in satirlar[:-1]:
        baslar.append(baslar[-1] + len(s) + 1)

    def konum(i: int) -> tuple[int, int]:
        sat = metin.count("\n", 0, i)
        return sat, i - baslar[sat]

    dolu = [m.span() for m in _ATAMA.finditer(metin) if _anahtar_uygun(m.group("anahtar"))]
    adaylar = []  # (bas, son, deger, tur, varsayilan_servis, anahtar_son)

    def ekle(bas, son, deger, tur, servis, anahtar_son):
        if any(bas < b and a < son for a, b in dolu):
            return
        dolu.append((bas, son))
        adaylar.append((bas, son, deger, tur, servis, anahtar_son))

    uri = _kalip(ayar, "uri")
    yer_tutucu = _kalip(ayar, "uri", "yer_tutucu")
    if uri:
        for m in uri.finditer(metin):
            if yer_tutucu and yer_tutucu.match(m.group("parola")):
                continue
            deger = m.group(0).rstrip(".,;)>\"'")
            ekle(m.start(), m.start() + len(deger), deger, "uri", m.group("sema").split("+")[0].lower(),
                 ayar["uri"].get("anahtar_son", "CONNECTION_STRING"))
    for b in ayar.get("belirecler", []):
        try:
            kalip = re.compile(b["desen"])
        except Exception:
            continue
        for m in kalip.finditer(metin):
            gr = "deger" if "deger" in kalip.groupindex else 0
            ekle(m.start(), m.end(), m.group(gr), "belirec", b.get("servis", ""), b.get("anahtar_son", "TOKEN"))
    parola = _kalip(ayar, "parola_satiri")
    if parola:
        for m in parola.finditer(metin):
            if yer_tutucu and yer_tutucu.match(m.group("deger")):
                continue
            ekle(m.start(), m.end(), m.group("deger"), "parola", "", ayar["parola_satiri"].get("anahtar_son", "PASSWORD"))

    adaylar.sort()
    kullanilan: set[int] = set()
    sonuc, gorulen = [], set()
    for bas, son, deger, tur, servis_varsayilan, anahtar_son in adaylar:
        bas_satir, sutun = konum(bas)
        bit_satir, _ = konum(son)
        etiket = _etiket_bul(satirlar, bas_satir, bit_satir, sutun, kullanilan, ayar.get("etiket", {}))
        servis = _ad(etiket) if etiket else ""
        if not servis:
            servis = re.sub(r"[^a-z0-9]+", "_", servis_varsayilan.lower()).strip("_")
        if not servis:
            continue  # parola satırı etiketsiz tahmin edilmez
        anahtar = f"{servis.upper()}_{anahtar_son}"
        if (servis, anahtar, deger) in gorulen:
            continue
        gorulen.add((servis, anahtar, deger))
        sonuc.append({"servis": servis, "anahtar": anahtar, "deger": deger, "tur": tur})
    return sonuc


def _bos_ad(servis: str, proje: str | None) -> str:
    n = 2
    while K.yol(f"{servis}_{n}", proje):
        n += 1
    return f"{servis}_{n}"


def _serbest_yaz(k: dict, proje: str | None) -> str:
    """Serbest metin kaydı: yoksa yazar, aynıysa dokunmaz, farklıysa ezmez ve yeni ad önerir."""
    servis, anahtar, deger = k["servis"], k["anahtar"], k["deger"]
    try:
        try:
            mevcut = K.yukle(servis, proje)
        except K.KimlikHata:
            mevcut = {}
        for ad, v in mevcut.items():
            if v == deger:
                return f"kimlik aynı, değişiklik yok: {servis}.{ad}"
        if anahtar in mevcut:
            return f"kimlik farklı değer, yazılmadı: {servis}.{anahtar}; yeni ad önerisi: {_bos_ad(servis, proje)}"
        K.ekle(servis, anahtar, deger, proje)
        return f"kimlik kaydedildi: {servis}.{anahtar}"
    except K.KimlikHata as e:
        return f"kimlik yazılamadı: {servis}.{anahtar} ({e})"


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
    serbest = yakala_serbest(metin)
    satirlar.extend(_serbest_yaz(k, proje) for k in serbest)
    if serbest:
        satirlar.append(UYARI)
    return satirlar
