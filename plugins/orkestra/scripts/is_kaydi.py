"""Kalıcı 'iş' katmanı: bir iş birden çok sohbete/karta yayılır.

Merkezi dizin: <durum dizini>/isler.json; iş klasöründe is.json.
Kilit ve atomik yazım ork_lib'den gelir.
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ork_lib as L  # noqa: E402

DURUMLAR = ("acik", "beklemede", "kapandi")
_ID = re.compile(r"^I-(\d+)$")
_TODO_ACIK = re.compile(r"^\s*[-*]\s*\[ \]\s*(.*)$")
_TODO_BITEN = re.compile(r"^\s*[-*]\s*\[[xX]\]\s*(.*)$")
_BOS = {"sayac": 0, "isler": {}}


def _merkez(sd: str) -> str:
    return os.path.join(sd, "isler.json")


_DENEME = 8
_BEKLEME_S = 0.01


def _oku(yol: str, varsayilan):
    if not os.path.exists(yol):
        return json.loads(json.dumps(varsayilan))
    for deneme in range(_DENEME):
        try:
            with open(yol, encoding="utf-8") as f:
                return json.load(f)
        except (PermissionError, json.JSONDecodeError):
            if deneme == _DENEME - 1:
                raise
            time.sleep(_BEKLEME_S * 2 ** deneme)


def _yaz(yol: str, veri) -> None:
    """Atomik yazım; Windows'ta hedef anlık tutulursa os.replace PermissionError verir.
    Artan beklemeyle yeniden dener, başarısızlıkta geçici dosyayı siler."""
    metin = json.dumps(veri, ensure_ascii=False, indent=2) + "\n"
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    fd, gecici = tempfile.mkstemp(dir=os.path.dirname(yol), prefix=".tmp_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(metin)
        for deneme in range(_DENEME):
            try:
                os.replace(gecici, yol)
                return
            except PermissionError:
                if deneme == _DENEME - 1:
                    raise
                time.sleep(_BEKLEME_S * 2 ** deneme)
    finally:
        if os.path.exists(gecici):
            try:
                os.remove(gecici)
            except OSError:
                pass


def is_no(is_id: str) -> int:
    m = _ID.match(is_id or "")
    if not m:
        raise ValueError(f"geçersiz iş kimliği: {is_id!r}")
    return int(m.group(1))


def is_sirala(ids) -> list[str]:
    return sorted(ids, key=is_no)


def yeni_is_id(sd: str) -> str:
    """Kilitli sayaç artırımı; I-999 sonrası I-1000."""
    yol = _merkez(sd)
    with L.kilit(yol):
        veri = _oku(yol, _BOS)
        veri["sayac"] = int(veri.get("sayac", 0)) + 1
        veri.setdefault("isler", {})
        _yaz(yol, veri)
        return f"I-{veri['sayac']:03d}"


def _is_json_yolu(klasor: str) -> str:
    return os.path.join(klasor, "is.json")


_SABLON = {
    "plan.md": "# {baslik}\n\n## Amaç\n\n## Kararlar\n",
    "todo.md": "# Yapılacaklar — {baslik}\n\n- [ ] \n",
    "oturumlar.md": "# Oturumlar — {baslik}\n\n",
}


def is_ac(sd: str, baslik: str, klasor: str, etiketler=None) -> dict:
    klasor = os.path.abspath(klasor)
    os.makedirs(klasor, exist_ok=True)
    for ad, sablon in _SABLON.items():
        yol = os.path.join(klasor, ad)
        if not os.path.exists(yol):  # var olan asla ezilmez
            try:
                with open(yol, "x", encoding="utf-8", newline="\n") as f:
                    f.write(sablon.format(baslik=baslik))
            except FileExistsError:  # var-mı kontrolü ile yazma arası yarış
                pass
    is_id = yeni_is_id(sd)
    an = L.simdi()
    kayit = {
        "id": is_id, "baslik": baslik, "durum": "acik", "klasor": klasor,
        "olusturma": an, "guncelleme": an, "etiketler": list(etiketler or []),
        "kartlar": [], "oturumlar": [], "gecmis": [{"zaman": an, "olay": "acildi"}],
    }
    with L.kilit(_is_json_yolu(klasor)):
        _yaz(_is_json_yolu(klasor), kayit)
    yol = _merkez(sd)
    with L.kilit(yol):
        veri = _oku(yol, _BOS)
        veri.setdefault("isler", {})[is_id] = {
            "klasor": klasor, "baslik": baslik, "durum": "acik", "olusturma": an}
        _yaz(yol, veri)
    return kayit


def is_al(sd: str, is_id: str) -> dict | None:
    giris = _oku(_merkez(sd), _BOS).get("isler", {}).get(is_id)
    if not giris:
        return None
    return _oku(_is_json_yolu(giris["klasor"]), None)


def is_liste(sd: str, durum: str | None = None) -> list[dict]:
    isler = _oku(_merkez(sd), _BOS).get("isler", {})
    out = []
    for i in is_sirala(isler):
        g = dict(isler[i])
        g["id"] = i
        if durum is None or g.get("durum") == durum:
            out.append(g)
    return out


def _degistir(sd: str, is_id: str, islem) -> dict:
    giris = _oku(_merkez(sd), _BOS).get("isler", {}).get(is_id)
    if not giris:
        raise KeyError(f"iş yok: {is_id}")
    yol = _is_json_yolu(giris["klasor"])
    with L.kilit(yol):
        kayit = _oku(yol, None)
        if kayit is None:
            raise KeyError(f"is.json yok: {yol}")
        islem(kayit)
        kayit["guncelleme"] = L.simdi()
        _yaz(yol, kayit)
    return kayit


def is_durum(sd: str, is_id: str, durum: str) -> dict:
    if durum not in DURUMLAR:
        raise ValueError(f"geçersiz durum: {durum}")

    def islem(k):
        k["durum"] = durum
        k.setdefault("gecmis", []).append({"zaman": L.simdi(), "olay": f"durum:{durum}"})

    kayit = _degistir(sd, is_id, islem)
    yol = _merkez(sd)
    with L.kilit(yol):
        veri = _oku(yol, _BOS)
        if is_id in veri.get("isler", {}):
            veri["isler"][is_id]["durum"] = durum
            _yaz(yol, veri)
    return kayit


def is_kart_ekle(sd: str, is_id: str, kart_id: str) -> dict:
    def islem(k):
        if kart_id not in k.setdefault("kartlar", []):
            k["kartlar"].append(kart_id)
            k.setdefault("gecmis", []).append({"zaman": L.simdi(), "olay": f"kart:{kart_id}"})

    return _degistir(sd, is_id, islem)


_JIRA_ONEK = re.compile(r"^[A-Z]{2,}[A-Z0-9]*-\d+:?\s+")
_ADIM = re.compile(r"^(G\d+[a-z]?(?:-[A-Za-z]\d+|/[A-Za-z]?\d+)*)(?=[:\s]|$)")


def adim_coz(baslik) -> str | None:
    """Başlıktaki plan adımı öneki ('PE-636 G7-A1: x' -> 'G7-A1'); yoksa None."""
    b = _JIRA_ONEK.sub("", (baslik or "").strip(), count=1)
    m = _ADIM.match(b)
    return m.group(1) if m else None


def _klasor_anahtari(klasor: str) -> str:
    return os.path.normcase(os.path.normpath(os.path.abspath(klasor))).casefold()


def is_klasorle_bul(sd: str, klasor: str, kapali_dahil: bool = False) -> str | None:
    """isler.json'da klasörü eşleşen ilk AÇIK (kapanmamış) iş kimliği; kapali_dahil=True ise durumdan bağımsız."""
    hedef = _klasor_anahtari(klasor)
    for g in is_liste(sd):
        if not g.get("klasor") or _klasor_anahtari(g["klasor"]) != hedef:
            continue
        if kapali_dahil or g.get("durum") != "kapandi":
            return g["id"]
    return None


def is_oturum_bagla(sd: str, is_id: str, oturum: str) -> dict:
    def islem(k):
        if not any(o.get("oturum") == oturum for o in k.setdefault("oturumlar", [])):
            an = L.simdi()
            k["oturumlar"].append({"oturum": oturum, "baglanma": an})
            k.setdefault("gecmis", []).append({"zaman": an, "olay": f"oturum:{oturum}"})

    return _degistir(sd, is_id, islem)


def todo_ozet(klasor: str) -> dict:
    yol = os.path.join(klasor, "todo.md")
    biten, acik = 0, []
    if os.path.exists(yol):
        with open(yol, encoding="utf-8", errors="replace") as f:
            for satir in f:
                if _TODO_BITEN.match(satir):
                    biten += 1
                else:
                    m = _TODO_ACIK.match(satir)
                    if m and m.group(1).strip():
                        acik.append(m.group(1).strip())
    return {"toplam": biten + len(acik), "biten": biten, "acik_maddeler": acik}


_TODO_KUTU = re.compile(r"^[-*]\s*\[( |x|X|~)\]\s*(.*)$")
_TODO_ALT = re.compile(r"^\s+[-*]\s+(?:\[[ xX~]\]\s*)?(.*)$")
_TODO_ADIM = re.compile(r"(?<![\w-])G\d+[a-z]?(?:-[A-Za-z]\d+|/[A-Za-z]?\d+|-G\d+)*(?![\w])")
_TODO_TARIH = re.compile(r"\s*\(\d{1,2}\.\d{1,2}[^)]*\)\s*$")


def _todo_dosyasi(klasor: str) -> str | None:
    if not os.path.isdir(klasor):
        return None
    for ad in sorted(os.listdir(klasor)):
        if ad.lower() == "todo.md":
            return os.path.join(klasor, ad)
    return None


def _todo_metin(ham: str) -> str:
    t = ham.replace("**", "").replace("`", "")
    t = t.split(" → ", 1)[0].strip()
    while True:
        y = _TODO_TARIH.sub("", t)
        if y == t:
            break
        t = y
    t = t.strip()
    return t if len(t) <= 100 else t[:99] + "…"


def todo_maddeleri(klasor: str) -> list[dict]:
    """TODO.md'nin üst düzey onay kutulu maddeleri (dosya sırası)."""
    yol = _todo_dosyasi(klasor)
    if not yol:
        return []
    out, bolum, son = [], "", None
    with open(yol, encoding="utf-8-sig", errors="replace") as f:
        for satir in f:
            satir = satir.rstrip("\r\n")
            if satir.startswith("##"):
                bolum = satir.lstrip("#").strip()
                son = None
                continue
            m = _TODO_KUTU.match(satir)
            if not m:
                a = _TODO_ALT.match(satir)
                if a and son is not None and len(son["alt"]) < 8:
                    t = _todo_metin(a.group(1))
                    if t:
                        son["alt"].append(t)
                elif satir.strip() and not satir[0].isspace():
                    son = None
                continue
            ham = m.group(2).replace("**", "").replace("`", "")
            if not ham.strip():
                son = None
                continue  # boş şablon maddesi
            adimlar = []
            for a in _TODO_ADIM.findall(ham):
                if a not in adimlar:
                    adimlar.append(a)
            out.append({"durum": {" ": "acik", "~": "suruyor"}.get(m.group(1), "bitti"),
                        "metin": _todo_metin(m.group(2)), "adimlar": adimlar, "bolum": bolum,
                        "alt": []})
            son = out[-1]
    return out


_KOVA = {"teslim": "yapildi", "isleniyor": "simdi", "denetimde": "simdi", "onaylandi": "simdi",
         "planlandi": "sirada", "beklemede": "sirada", "reddedildi": "sirada", "iptal": "iptal"}


def _eslesir(madde_adim: str, kart_adim: str) -> bool:
    return (madde_adim == kart_adim or kart_adim.startswith(madde_adim + "-")
            or madde_adim.startswith(kart_adim + "-"))


def _kart_no(k: dict):
    m = re.search(r"\d+", str(k.get("id", "")))
    return (int(m.group()) if m else 0, str(k.get("id", "")))


def is_serit(sd: str, is_id: str, alt: bool = False) -> dict:
    """Bir iş için yapıldı/şimdi/sırada/planda-kart-yok/iptal kovaları (deterministik)."""
    kayit = is_al(sd, is_id)
    giris = next((g for g in is_liste(sd) if g["id"] == is_id), None)
    if not kayit or not giris:
        raise KeyError(f"iş yok: {is_id}")
    klasor = giris["klasor"]
    maddeler = todo_maddeleri(klasor)
    kartlar = sorted((k for k in L.kartlar(sd) if k.get("is") == is_id), key=_kart_no)
    durumlar = {k.get("id"): k.get("durum") for k in L.kartlar(sd)}
    kovalar = {"yapildi": [], "simdi": [], "sirada": [], "planda_kart_yok": [], "iptal": []}
    kart_adimlari = [(k["adim"], k.get("durum")) for k in kartlar if k.get("adim")]
    for md in maddeler:
        esl = [d for a in md["adimlar"] for ka, d in kart_adimlari if _eslesir(a, ka)]
        if md["durum"] == "bitti":
            if any(d != "iptal" for d in esl):
                continue
        else:
            # bitmemiş kart yalnız metni o adımla BAŞLAYAN açık/süren maddeyi gizler
            esl_bas = [d for a in md["adimlar"] if md["metin"].startswith(a)
                       for ka, d in kart_adimlari if _eslesir(a, ka)]
            if any(d not in ("teslim", "iptal") for d in esl_bas):
                continue
        kova = {"bitti": "yapildi", "suruyor": "simdi"}.get(md["durum"], "planda_kart_yok")
        oge = {"tur": "madde", "metin": md["metin"], "adimlar": md["adimlar"],
               "bolum": md["bolum"], "durum": md["durum"]}
        if alt:  # yalnız panel /isler.json; CLI çıktısı değişmez
            oge["alt"] = list(md.get("alt") or [])
        kovalar[kova].append(oge)
    for k in kartlar:
        kova = _KOVA.get(k.get("durum"))
        if not kova:
            continue
        bek = [b for b in (k.get("bagimliliklar") or [])
               if durumlar.get(b) not in ("teslim", "onaylandi")]
        kovalar[kova].append({"tur": "kart", "kart": k["id"], "adim": k.get("adim"),
                              "metin": (k.get("teslim_ozeti") if k.get("durum") == "teslim" else None)
                              or k.get("baslik", ""),
                              "durum": k.get("durum"), "bekledigi": bek})
    biten = sum(1 for m in maddeler if m["durum"] == "bitti")
    return {"is": {"id": is_id, "baslik": giris.get("baslik", ""), "durum": giris.get("durum"),
                   "klasor": klasor},
            "ilerleme": {"biten": biten, "toplam": len(maddeler)}, **kovalar}


_IS_ONEK = re.compile(r"^(?:\d{1,4}-)?\d{8}-")


def is_adi(baslik) -> str:
    """Okunur iş adı: 'NNN-YYYYMMDD-' öneki atılır, kalan '-' boşluk olur (Jira kodu tireli kalır).
    Öneksiz başlık aynen döner."""
    b = baslik or ""
    if not _IS_ONEK.match(b):
        return b
    kalan = _IS_ONEK.sub("", b, count=1)
    m = re.match(r"^([A-Z][A-Z0-9]+-\d+)(?:-(.*))?$", kalan)
    if m:
        return m.group(1) + (" " + m.group(2).replace("-", " ") if m.group(2) else "")
    return kalan.replace("-", " ")


def onar(sd: str, ek_klasorler=None, uygula: bool = False) -> dict:
    """Merkez isler.json'u iş klasörlerindeki is.json kayıtlarından yeniden kurar.

    Bilinen klasörler: merkezdeki girişler + ek_klasorler. is.json okunamayan klasör atlanır
    (merkezdeki girişi silinmez). Sayaç düşmez: max(mevcut sayaç, en büyük I-NNN).
    Varsayılan kuru koşu: dosya yazmaz. Dönüş: {"farklar": [metin], "uyarilar": [metin], "yazildi": bool}.
    """
    yol = _merkez(sd)
    with (L.kilit(yol) if uygula else contextlib.nullcontext()):  # kuru koşu kilit/dosya oluşturmaz
        var_mi = os.path.exists(yol)
        mevcut = _oku(yol, _BOS)
        isler = {i: dict(g) for i, g in (mevcut.get("isler") or {}).items()}
        klasorler = []
        for g in isler.values():
            if g.get("klasor"):
                klasorler.append(os.path.abspath(g["klasor"]))
        klasorler += [os.path.abspath(k) for k in (ek_klasorler or [])]
        farklar, uyarilar = [], []
        gorulen = set()
        for k in klasorler:
            if k in gorulen:
                continue
            gorulen.add(k)
            try:
                kayit = _oku(_is_json_yolu(k), None)
            except (OSError, ValueError):
                kayit = None
            if not isinstance(kayit, dict) or not _ID.match(str(kayit.get("id", ""))):
                uyarilar.append(f"atlandı (geçerli is.json yok): {k}")
                continue
            i = kayit["id"]
            yeni = {"klasor": k, "baslik": kayit.get("baslik", ""), "durum": kayit.get("durum", "acik"),
                    "olusturma": kayit.get("olusturma", "")}
            eski = isler.get(i)
            if eski is None:
                farklar.append(f"{i}: merkezde eksik, eklenecek ({k})")
                isler[i] = yeni
                continue
            for alan, deger in yeni.items():
                onceki = eski.get(alan)
                if alan == "klasor" and onceki:
                    onceki = os.path.abspath(onceki)
                if onceki != deger:
                    farklar.append(f"{i}: {alan} {onceki!r} -> {deger!r}")
                    eski[alan] = deger
        en_buyuk = max([is_no(i) for i in isler] or [0])
        sayac = int(mevcut.get("sayac", 0))
        if sayac < en_buyuk:
            farklar.append(f"sayac: {sayac} -> {en_buyuk}")
            sayac = en_buyuk
        yazildi = False
        if uygula and (farklar or not var_mi) and (farklar or isler):
            _yaz(yol, {**mevcut, "sayac": sayac, "isler": isler})
            yazildi = True
    return {"farklar": farklar, "uyarilar": uyarilar, "yazildi": yazildi}
