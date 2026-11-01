"""Teslim kuyruğu (I-323 P2): oturumlar işini kuyruğa verir, tek entegrasyon koşucusu toplu tam koşuyu yapar.

Kayıt: `<durum>/kuyruk/teslimler.jsonl` yalnız-ekleme olay günlüğü; her satır bir teslimin o anki tam durumudur, bir
teslimin geçerli durumu son satırıdır. Okuma-denetim-ekleme tek `L.kilit` altında yapılır (oturum kaydıyla aynı düzen:
oturum_farkindalik.py); işletim sistemi kilidi süreç çökünce kendiliğinden bırakılır.

Alanlar: teslim (kimlik), oturum, dal, test (hedefli test sonucu: gecti|kaldi|yok), durum, sira, zaman.
Durumlar ve geçişler:
  bekliyor -> kosuyor -> birlesti
              kosuyor -> karantina
  karantina -> bekliyor   (yalnız `ekle` ile: suçlu oturum düzeltip yeniden teslim eder; kuyruğun sonuna girer)

Tek-koşucu kilidi: `<durum>/kuyruk/kosucu.json` {sahip, pid, t}. Aynı anda tek entegrasyon koşusu; canlı sahibi olan
kilidi ikinci koşucu alamaz. Sahip `kosucu_tazele` ile t'yi yeniler; t BAYAT_S (30 sn) eskiyse kilit bayattır ve
devralınır (koşucu süreci öldü). Model çağırmaz.
"""
from __future__ import annotations

import json
import os
import time

import ork_lib as L

DURUMLAR = ("bekliyor", "kosuyor", "birlesti", "karantina")
GECISLER = {("bekliyor", "kosuyor"), ("kosuyor", "birlesti"), ("kosuyor", "karantina")}
TESTLER = ("gecti", "kaldi", "yok")
BAYAT_S = 30.0
KILIT_BEKLEME_S = 10.0  # eşzamanlı teslimde kuyruk kilidi beklemesi (L.kilit varsayılanı 3 sn)


class KuyrukHatasi(ValueError):
    """Geçersiz teslim ya da geçiş; mesaj kullanıcıya gösterilir."""


def kuyruk_yolu(sd: str) -> str:
    return os.path.join(sd, "kuyruk", "teslimler.jsonl")


def kosucu_yolu(sd: str) -> str:
    return os.path.join(sd, "kuyruk", "kosucu.json")


def _katla(olaylar: list[dict]) -> dict[str, dict]:
    son: dict[str, dict] = {}
    for o in olaylar:
        if isinstance(o, dict) and o.get("teslim"):
            son[str(o["teslim"])] = o
    return son


def _ekle_kilitli(yol: str, kayit: dict) -> dict:
    """Kilit zaten tutuluyorken satır ekler (L.jsonl_ekle kilidi yeniden almaya çalışır, kendini bekler)."""
    kayit = {"v": L.KAYIT_SURUMU, **kayit}
    with open(yol, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(kayit, ensure_ascii=False) + "\n")
    return kayit


def ekle(sd: str, teslim: str, oturum: str, dal: str, test: str = "gecti") -> dict:
    """Teslimi kuyruğa ekler; dönen kayıtta `sira` ve `onunde` (önündeki bekleyen sayısı) vardır.
    Karantinadaki teslim yeniden eklenince bekliyor'a döner ve yeni sıra alır. Hedefli testi kalan teslim kabul edilmez."""
    teslim, dal = (teslim or "").strip(), (dal or "").strip()
    if not teslim or not dal:
        raise KuyrukHatasi("teslim kimliği ve dal gerekli")
    if test not in TESTLER:
        raise KuyrukHatasi(f"hedefli test sonucu {'|'.join(TESTLER)} olmalı: {test}")
    if test == "kaldi":
        raise KuyrukHatasi("hedefli test kaldı: önce düzelt, sonra teslim et")
    yol = kuyruk_yolu(sd)
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    with L.kilit(yol, bekleme_s=KILIT_BEKLEME_S):
        olaylar = L.jsonl_oku(yol)
        son = _katla(olaylar)
        onceki = son.get(teslim)
        if onceki and onceki.get("durum") != "karantina":
            raise KuyrukHatasi(f"teslim zaten kuyrukta: {teslim} ({onceki.get('durum')})")
        sira = max((int(o.get("sira") or 0) for o in olaylar if isinstance(o, dict)), default=0) + 1
        onunde = sum(1 for k in son.values() if k.get("durum") == "bekliyor")
        kayit = _ekle_kilitli(yol, {"teslim": teslim, "oturum": oturum or "-", "dal": dal, "test": test,
                                    "durum": "bekliyor", "sira": sira, "zaman": L.simdi(),
                                    **({"onceki": "karantina"} if onceki else {})})
    return {**kayit, "onunde": onunde}


def gecis(sd: str, teslim: str, yeni: str, neden: str | None = None) -> dict:
    """bekliyor->kosuyor, kosuyor->birlesti, kosuyor->karantina; başka geçiş KuyrukHatasi."""
    if yeni not in DURUMLAR:
        raise KuyrukHatasi(f"bilinmeyen durum: {yeni}")
    yol = kuyruk_yolu(sd)
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    with L.kilit(yol, bekleme_s=KILIT_BEKLEME_S):
        onceki = _katla(L.jsonl_oku(yol)).get(teslim)
        if not onceki:
            raise KuyrukHatasi(f"teslim kuyrukta yok: {teslim}")
        eski = onceki.get("durum")
        if (eski, yeni) not in GECISLER:
            ipucu = " (yeniden teslim için `kuyruk ekle`)" if (eski, yeni) == ("karantina", "bekliyor") else ""
            raise KuyrukHatasi(f"geçersiz geçiş: {eski} -> {yeni}{ipucu}")
        kayit = {k: v for k, v in onceki.items() if k not in ("v", "onceki", "neden")}
        kayit.update({"durum": yeni, "zaman": L.simdi()})
        if neden:
            kayit["neden"] = neden
        return _ekle_kilitli(yol, kayit)


def liste(sd: str, durum: str | None = None) -> list[dict]:
    """Teslimlerin geçerli durumları, sıra numarasına göre."""
    kayitlar = sorted(_katla(L.jsonl_oku(kuyruk_yolu(sd))).values(), key=lambda k: int(k.get("sira") or 0))
    return [k for k in kayitlar if durum is None or k.get("durum") == durum]


# ---------------------------------------------------------------- tek-koşucu kilidi

def _kosucu_oku(yol: str) -> dict:
    try:
        with open(yol, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def kosucu_al(sd: str, sahip: str, simdi: float | None = None, bayat_s: float = BAYAT_S) -> bool:
    """Tek-koşucu kilidini alır: True. Canlı (t'si bayat_s'den yeni) başka sahip varsa False (ikinci koşu reddedilir).
    Bayat kilit devralınır; aynı sahip yeniden alırsa tazelenir."""
    yol = kosucu_yolu(sd)
    t = time.time() if simdi is None else simdi
    with L.kilit(yol, bekleme_s=KILIT_BEKLEME_S):
        k = _kosucu_oku(yol)
        if k.get("sahip") and k.get("sahip") != sahip and t - float(k.get("t") or 0) < bayat_s:
            return False
        kayit = {"sahip": sahip, "pid": os.getpid(), "t": t, "zaman": L.simdi()}
        if k.get("sahip") and k.get("sahip") != sahip:
            kayit["devralinan"] = k.get("sahip")
        L.atomik_yaz(yol, json.dumps(kayit, ensure_ascii=False))
        return True


def kosucu_tazele(sd: str, sahip: str, simdi: float | None = None) -> bool:
    """Sahip koşu sürerken kilidin t'sini yeniler; kilit başkasındaysa False."""
    yol = kosucu_yolu(sd)
    with L.kilit(yol, bekleme_s=KILIT_BEKLEME_S):
        k = _kosucu_oku(yol)
        if k.get("sahip") != sahip:
            return False
        k["t"] = time.time() if simdi is None else simdi
        L.atomik_yaz(yol, json.dumps(k, ensure_ascii=False))
        return True


def kosucu_birak(sd: str, sahip: str) -> bool:
    """Kilidi bırakır; yalnız sahibi bırakabilir."""
    yol = kosucu_yolu(sd)
    with L.kilit(yol, bekleme_s=KILIT_BEKLEME_S):
        if _kosucu_oku(yol).get("sahip") != sahip:
            return False
        try:
            os.remove(yol)
        except OSError:
            return False
        return True


def kosucu(sd: str) -> dict:
    """Kilit kaydı ({} yoksa); `bayat` alanı hesaplanır."""
    k = _kosucu_oku(kosucu_yolu(sd))
    if k:
        k["bayat"] = time.time() - float(k.get("t") or 0) >= BAYAT_S
    return k
