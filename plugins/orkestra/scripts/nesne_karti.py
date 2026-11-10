"""Nesne kartı doğrulayıcısı (ADR-0177): tablo, kolon, prosedür gibi bir nesneyi anlatan kartta her iddia derece
(KESİN / GÜÇLÜ / DOĞRULANMADI) ve yeniden çalıştırılabilir kaynakça taşır. Model çağrılmaz; yalnız biçimi ve kaynak
hiyerarşisini denetler, iddianın doğruluğunu denetlemez (doğruluk için kart ayrı denetçiyle kaynağıyla eşlenir).

Kart biçimi:
    - [KESİN] metin (K1, K2)
    - [DOĞRULANMADI] metin (K3)
      - Neden: ...
      - Kapatma: ...
    - K1: tür=Veritabanı kataloğu; komut=SELECT ... | yol=...; ortam=kopya; saat=10.11.2026 14:39

Türler, hiyerarşi, alan listeleri ve sır kalıpları `ayarlar/nesne_karti.json`'dadır (proje durum dizinindeki aynı adlı
dosya anahtar bazında ezer). Bulgu: {'tur', 'satir', 'ayrinti'}.
"""
from __future__ import annotations

import json
import os
import re

_KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VARSAYILAN_YOL = os.path.join(_KOK, "ayarlar", "nesne_karti.json")
PROJE_DOSYA = "nesne_karti.json"
MODLAR = ("golge", "kapali")

_ALANLAR = ("tür", "tur", "komut", "yol", "ortam", "saat")
_AYIRAC = re.compile(r"\s*[;|]\s*(?=(?:%s)=)" % "|".join(_ALANLAR), re.I)
_DEGER = re.compile(r"^\s*[-*]\s*\[([^\]]+)\]\s*(.*?)\s*$")
_KAYNAK = re.compile(r"^\s*[-*]\s*(K\d+)\s*:\s*(.*?)\s*$")
_ATIF = re.compile(r"\(\s*(K\d+(?:\s*,\s*K\d+)*)\s*\)\s*$")


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
        proje = _json_oku(os.path.join(sd, PROJE_DOSYA))
        if proje:
            ayar.update(proje)
    return ayar


def mod(ayar: dict) -> str:
    if os.environ.get("ORKESTRA_NESNE_KARTI") == "0":
        return "kapali"
    m = ayar.get("mod", "kapali")
    return m if m in MODLAR else "golge" if m else "kapali"


def norm(metin) -> str:
    """Türkçe büyük/küçük harf ve aksan farkını giderir (KESİN = kesin = KESIN)."""
    s = (metin or "").replace("İ", "i").replace("I", "ı").lower()
    return s.translate(str.maketrans("ıöüşğç", "iousgc"))


def _bosluk(metin) -> str:
    return " ".join((metin or "").split()).casefold()


def _ayristir(satirlar):
    """(iddialar, kaynaklar, serbest_madde). iddia: {'satir','derece','metin','atif','alt'}; kaynak: {'satir','kimlik','alan'}."""
    iddialar, kaynaklar, hatali = [], {}, []
    son = None
    for no, ham in enumerate(satirlar, 1):
        if not ham.strip():
            continue
        girinti = len(ham) - len(ham.lstrip())
        if girinti >= 2 and son is not None:
            m = re.match(r"^\s*[-*]\s*([^:]+):\s*(.*)$", ham)
            if m:
                son["alt"][norm(m.group(1)).strip()] = m.group(2).strip()
            continue
        if not re.match(r"^\s*[-*]\s", ham):
            continue
        k = _KAYNAK.match(ham)
        if k:
            alanlar = {}
            for parca in _AYIRAC.split(k.group(2)):
                ad, _, deger = parca.partition("=")
                alanlar[norm(ad).strip()] = deger.strip()
            kaynaklar[k.group(1)] = {"satir": no, "kimlik": k.group(1), "alan": alanlar, "ham": k.group(2)}
            son = None
            continue
        d = _DEGER.match(ham)
        if d:
            metin, atif = d.group(2), []
            a = _ATIF.search(metin)
            if a:
                atif = [x.strip() for x in a.group(1).split(",")]
                metin = metin[: a.start()].strip()
            son = {"satir": no, "derece_ham": d.group(1).strip(), "metin": metin, "atif": atif, "alt": {}}
            iddialar.append(son)
            continue
        hatali.append((no, ham.strip()))
        son = None
    return iddialar, kaynaklar, hatali


def dogrula(metin: str, ayar: dict | None = None, dokum: str | None = None) -> list:
    """Kart metnini denetler. Bulgu türleri: derece_yok, kesin_ikincil_kaynak, kaynakca_eksik, kaynakca_sir,
    kaynak_okunmadi (yalnız dokum verilince), dogrulanmadi_eksik, kart_bos."""
    ayar = ayar if ayar is not None else ayar_oku()
    iddialar, kaynaklar, hatali = _ayristir((metin or "").splitlines())
    bulgu = []

    def ekle(tur, satir, ayrinti):
        bulgu.append({"tur": tur, "satir": satir, "ayrinti": ayrinti})

    dereceler = {norm(d): d for d in ayar.get("dereceler") or []}
    kesin = norm(ayar.get("kesin_derece", "KESİN"))
    dogr = norm(ayar.get("dogrulanmadi_derece", "DOĞRULANMADI"))
    birincil = {norm(t) for t in ayar.get("birincil_turler") or []}
    ikincil = {norm(t) for t in ayar.get("ikincil_turler") or []}
    zorunlu = [norm(a) for a in ayar.get("kaynak_zorunlu_alanlar") or []]
    komut_yol = [norm(a) for a in ayar.get("kaynak_komut_ya_yol") or []]
    sir = [k for k in ayar.get("sir_kaliplari") or []]

    if not iddialar and not hatali:
        ekle("kart_bos", 0, "kartta [DERECE] taşıyan iddia satırı yok")
        return bulgu
    for no, ham in hatali:
        ekle("derece_yok", no, "iddia satırı [KESİN|GÜÇLÜ|DOĞRULANMADI] ile başlamıyor: " + ham[:80])

    for kid, k in kaynaklar.items():
        a, no = k["alan"], k["satir"]
        eksik = [z for z in zorunlu if not a.get(z)]
        if komut_yol and not any(a.get(x) for x in komut_yol):
            eksik.append("/".join(komut_yol))
        if eksik:
            ekle("kaynakca_eksik", no, f"{kid}: eksik alan: {', '.join(eksik)}")
        tur = norm(a.get("tur", ""))
        if tur and tur not in birincil and tur not in ikincil:
            ekle("kaynakca_eksik", no, f"{kid}: bilinmeyen kaynak türü: {a.get('tur')}")
        for kalip in sir:
            try:
                if re.search(kalip, k["ham"]):
                    ekle("kaynakca_sir", no, f"{kid}: sır değeri kalıbı (değer yazılmaz)")
                    break
            except re.error:
                continue

    okunacak = []
    for i in iddialar:
        d = dereceler.get(norm(i["derece_ham"]))
        if d is None:
            ekle("derece_yok", i["satir"], f"bilinmeyen derece [{i['derece_ham']}]")
            continue
        dn = norm(d)
        if dn == dogr:
            for ad in ayar.get("dogrulanmadi_alanlari") or []:
                if not i["alt"].get(norm(ad)):
                    ekle("dogrulanmadi_eksik", i["satir"], f"DOĞRULANMADI iddiası '{ad}' satırı taşımıyor")
            continue
        if not i["atif"]:
            ekle("kaynakca_eksik", i["satir"], f"{d} iddia kaynak atfı (K<n>) taşımıyor")
            continue
        tanimli = [x for x in i["atif"] if x in kaynaklar]
        for x in i["atif"]:
            if x not in kaynaklar:
                ekle("kaynakca_eksik", i["satir"], f"{x} kaynakçada tanımlı değil")
        if dn == kesin:
            if not any(norm(kaynaklar[x]["alan"].get("tur", "")) in birincil for x in tanimli):
                ekle("kesin_ikincil_kaynak", i["satir"], "KESİN iddia birincil kaynağa dayanmıyor")
            okunacak += tanimli

    if dokum is not None:
        d = _bosluk(dokum)
        for x in dict.fromkeys(okunacak):
            a = kaynaklar[x]["alan"]
            degerler = [_bosluk(a[y]) for y in komut_yol if a.get(y)]
            if degerler and not any(v in d for v in degerler):
                ekle("kaynak_okunmadi", kaynaklar[x]["satir"], f"{x}: komut/yol dökümde tam eşleşmiyor")
    return bulgu[: int(ayar.get("max_bulgu", 10) or 10)]


def kart_var(metin: str, ayar: dict | None = None) -> bool:
    """Metinde en az bir geçerli [DERECE] iddia satırı var mı (gölge kapı için)."""
    ayar = ayar if ayar is not None else ayar_oku()
    dereceler = {norm(d) for d in ayar.get("dereceler") or []}
    for ham in (metin or "").splitlines():
        d = _DEGER.match(ham)
        if d and norm(d.group(1)) in dereceler and not ham.startswith(" "):
            return True
    return False
