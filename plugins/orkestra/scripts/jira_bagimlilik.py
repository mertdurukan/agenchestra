"""Jira görev bağımlılığı: işin klasöründeki `jira_bagimlilik.json` dosyasından öncül grafiği (ADR-0086, I-231 P1).

Dosyayı ana ajan yazar: Atlassian bağlayıcısındaki tek JQL yanıtı (`key in (…)`, alanlar `issuelinks`, `status`) olduğu gibi
`issues` altına konur ve `okuma_saati` (ISO) eklenir. Betik Jira'ya bağlanmaz; yalnız bu dosyayı işler.

Şema gerçek PE yanıtından (27.10.2026): `issues[].fields.issuelinks[]`, `type.name == "Blocks"`; `inwardIssue` bu görevi
bloklayan öncül, `outwardIssue` bu görevin bloklediği görevdir. Bağlantı iki uçta da görünür (aynı `id`); çift sayılmaz.
Kapalı görev `fields.status.statusCategory.key == "done"` ile anlaşılır (durum adları özeldir). `Blocks` dışındaki türler
(`Relates`, `Duplicate`, …) sıra bağı değildir.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta

DOSYA = "jira_bagimlilik.json"
SIRA_TURU = "Blocks"
KAPALI = "done"
ESKI_SAAT = 24  # okuma saati plan hazırlanma saatinden bu kadar saatten eskiyse veri eski sayılır (tahmin; K4c)


def yukle(klasor: str) -> dict | None:
    """İş klasöründeki `jira_bagimlilik.json` → çözümlenmiş grafik; dosya yoksa None (K4a). Bozuk dosya ValueError verir."""
    yol = os.path.join(klasor, DOSYA)
    if not os.path.isfile(yol):
        return None
    try:
        with open(yol, encoding="utf-8") as f:
            veri = json.load(f)
    except (OSError, ValueError) as e:
        raise ValueError(f"{DOSYA} okunamadı: {e}") from e
    return coz(veri)


def _kapali_mi(alanlar: dict | None) -> bool | None:
    """Durum kategorisi `done` mu; durum bilgisi yoksa None."""
    kat = (((alanlar or {}).get("status") or {}).get("statusCategory") or {}).get("key")
    return None if kat is None else kat == KAPALI


def coz(veri: dict) -> dict:
    """Ham yanıt → {okunan, oncul, kapali, okuma_saati}.

    okunan: `issues` içinde kendi kaydı gelen anahtarlar (bağlantıları okunmuş, bağlantısızlık da bu kümede kanıttır);
    oncul: {bloklanan: {öncüller}} yalnız `Blocks`; kapali: durum kategorisi `done` olan anahtarlar (komşu kayıtları dahil)."""
    if not isinstance(veri, dict) or not isinstance(veri.get("issues"), list):
        raise ValueError(f"{DOSYA}: `issues` listesi yok")
    okunan: set[str] = set()
    oncul: dict[str, set[str]] = {}
    kapali: set[str] = set()

    def durum_kaydet(anahtar: str, alanlar: dict | None) -> None:
        k = _kapali_mi(alanlar)
        if k:
            kapali.add(anahtar)

    for kayit in veri["issues"]:
        anahtar = kayit.get("key")
        if not anahtar:
            continue
        okunan.add(anahtar)
        alanlar = kayit.get("fields") or {}
        durum_kaydet(anahtar, alanlar)
        for bag in alanlar.get("issuelinks") or []:
            if ((bag.get("type") or {}).get("name")) != SIRA_TURU:
                continue
            for yon, komsu in (("inwardIssue", bag.get("inwardIssue")), ("outwardIssue", bag.get("outwardIssue"))):
                if not komsu or not komsu.get("key"):
                    continue
                durum_kaydet(komsu["key"], komsu.get("fields"))
                if yon == "inwardIssue":  # komşu bu görevi bloklar
                    oncul.setdefault(anahtar, set()).add(komsu["key"])
                else:  # bu görev komşuyu bloklar
                    oncul.setdefault(komsu["key"], set()).add(anahtar)
    return {"okunan": okunan, "oncul": oncul, "kapali": kapali, "okuma_saati": veri.get("okuma_saati")}


def oncul_kumesi(g: dict, anahtar: str) -> set[str]:
    """Görevin doğrudan öncülleri (açık ve kapalı)."""
    return set(g["oncul"].get(anahtar, ()))


def acik_onculler(g: dict, anahtar: str) -> set[str]:
    """Görevin kapalı olmayan doğrudan öncülleri."""
    return {o for o in oncul_kumesi(g, anahtar) if o not in g["kapali"]}


def okundu_mu(g: dict, anahtar: str) -> bool:
    """Görevin kendi kaydı dosyada var mı (bağlantısı olmayan görev de bu durumda 'okundu' sayılır)."""
    return anahtar in g["okunan"]


def dongu(g: dict) -> list[str]:
    """Açık görevler arasındaki bağımlılıkta döngü varsa döngüdeki anahtarlar (başı sonda tekrar); yoksa []."""
    kenar = {k: {o for o in v if o not in g["kapali"]} for k, v in g["oncul"].items() if k not in g["kapali"]}
    durum: dict[str, int] = {}
    yigin: list[str] = []

    def gez(k: str) -> list[str]:
        durum[k] = 1
        yigin.append(k)
        for o in sorted(kenar.get(k, ())):
            if durum.get(o) == 1:
                return yigin[yigin.index(o):] + [o]
            if o not in durum:
                bulunan = gez(o)
                if bulunan:
                    return bulunan
        yigin.pop()
        durum[k] = 2
        return []

    for k in sorted(kenar):
        if k not in durum:
            d = gez(k)
            if d:
                return d
    return []


def dalgalar(g: dict, anahtarlar: list[str] | set[str]) -> list[list[str]]:
    """Verilen küme içindeki açık öncül ilişkilerinden dalgalar (dalga = en uzun öncül zinciri derinliği); döngüde []."""
    kume = set(anahtarlar)
    if dongu(g):
        return []
    seviye: dict[str, int] = {}

    def hesapla(k: str) -> int:
        if k not in seviye:
            seviye[k] = 1 + max((hesapla(o) for o in acik_onculler(g, k) if o in kume), default=0)
        return seviye[k]

    for k in sorted(kume):
        hesapla(k)
    return [sorted(k for k in kume if seviye[k] == s) for s in range(1, max(seviye.values(), default=0) + 1)]


def eski_mi(g: dict, referans: datetime, saat: int = ESKI_SAAT) -> bool:
    """Okuma saati yok/okunamıyorsa ya da referanstan `saat` saatten eskiyse True (K4c)."""
    ham = g.get("okuma_saati")
    if not ham:
        return True
    try:
        okuma = datetime.fromisoformat(str(ham))
    except ValueError:
        return True
    if okuma.tzinfo is not None:
        okuma = okuma.replace(tzinfo=None)
    return referans - okuma > timedelta(hours=saat)
