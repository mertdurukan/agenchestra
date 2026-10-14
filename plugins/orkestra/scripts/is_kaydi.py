"""Kalıcı 'iş' katmanı: bir iş birden çok sohbete/karta yayılır.

Merkezi dizin: <durum dizini>/isler.json; iş klasöründe is.json.
Kilit ve atomik yazım ork_lib'den gelir.
"""
from __future__ import annotations

import contextlib
import datetime
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
_TODO_BOS = re.compile(r"^\s*[-*]\s*\[ \]\s*$")
_TODO_BITEN =re.compile(r"^\s*[-*]\s*\[[xX]\]\s*(.*)$")
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


def _todo_yol(klasor: str) -> str:
    return os.path.join(klasor, "todo.md")


def _todo_oku(yol: str) -> str:
    with open(yol, encoding="utf-8", newline="") as f:
        return f.read()


def todo_ekle(klasor: str, metin: str) -> str:
    """todo.md sonuna '- [ ] <metin>' ekler (kilit altında, atomik). Dönüş: eklenen madde metni."""
    metin = " ".join(str(metin).split())
    if not metin:
        raise ValueError("madde metni boş")
    yol = _todo_yol(klasor)
    with L.kilit(yol):
        icerik = _todo_oku(yol) if os.path.exists(yol) else "# Yapılacaklar\n\n"
        # şablonun boş yer tutucu maddesi ('- [ ] ') gerçek madde sayılmaz: eklemeden önce atılır
        icerik = "".join(x for x in icerik.splitlines(keepends=True) if not _TODO_BOS.match(x.rstrip("\r\n")))
        if icerik and not icerik.endswith("\n"):
            icerik += "\n"
        L.atomik_yaz(yol, icerik + f"- [ ] {metin}\n")
    return metin


def todo_bitir(klasor: str, secici: str, not_: str | None = None) -> str:
    """Açık maddeyi [x] yapar. secici: 1-tabanlı açık madde sırası ya da tek eşleşen alt dize."""
    yol = _todo_yol(klasor)
    if not os.path.exists(yol):
        raise ValueError("todo.md yok")
    with L.kilit(yol):
        satirlar = _todo_oku(yol).splitlines(keepends=True)
        acik = []  # (satır indeksi, madde metni)
        for i, s in enumerate(satirlar):
            m = _TODO_ACIK.match(s.rstrip("\r\n"))
            if m and m.group(1).strip():
                acik.append((i, m.group(1).strip()))
        secici = str(secici).strip()
        if re.fullmatch(r"\d+", secici):
            n = int(secici)
            if not 1 <= n <= len(acik):
                raise ValueError(f"açık madde sırası aralık dışı: {n} (açık madde: {len(acik)})")
            idx, metin = acik[n - 1]
        else:
            if not secici:
                raise ValueError("seçici boş")
            adaylar = [(i, t) for i, t in acik if secici.lower() in t.lower()]
            if len(adaylar) != 1:
                durum = "eşleşme yok" if not adaylar else f"{len(adaylar)} eşleşme"
                liste = adaylar or acik
                raise ValueError(f"'{secici}': {durum}; adaylar: " + " | ".join(t for _, t in liste))
            idx, metin = adaylar[0]
        satir = satirlar[idx]
        govde = satir.rstrip("\r\n")
        eol = satir[len(govde):]
        govde = re.sub(r"\[ \]", "[x]", govde, count=1)
        ek = f" — {datetime.date.today().isoformat()}: {not_}" if not_ else ""
        satirlar[idx] = govde + ek + eol
        L.atomik_yaz(yol, "".join(satirlar))
    return metin + ek


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
