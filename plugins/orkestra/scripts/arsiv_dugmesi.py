"""Arşiv düğmesi (ADR-0170): oturumda yapılacak başka iş ve konuşulacak konu kalmadığında kapanış kutusu uygulamanın
kendi 'archive' eylemini taşır; kullanıcı basınca uygulama sohbeti arşivler. Model çağrılmaz.

- L3 (PreToolUse): ana ajanın `wrap_up` çağrısı `ask` ve düğme taşımıyor, oturumda açık iş yoksa girdiye
  `ask` (kısa arşiv sorusu) ve `actions=[{"action": "archive"}]` eklenir; uygulama kutuyu ikisi birlikte olunca çizer (`dugme_girdisi`).
- Stop: çalışma turu (plan listesi ya da dosya değişikliği), açık iş yok, kapanış soru değil, turda `wrap_up` yok →
  tur başına bir kez block (`stop_tetik`); `wrap_up` plan listesini kapatır, böylece şerit takılı kalmaz.
- Açık iş: açık kart, onay bekleyen iş, bağlı işte açık todo maddesi.

Ayar: `ayarlar/arsiv_dugmesi.json` (proje ezmesi: durum dizininde `arsiv_dugmesi.json`). `ORKESTRA_ARSIV_DUGMESI=0` kapatır.
"""
from __future__ import annotations

import json
import os

import ork_lib as L

_KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VARSAYILAN_YOL = os.path.join(_KOK, "ayarlar", "arsiv_dugmesi.json")
PROJE_DOSYA = "arsiv_dugmesi.json"
MODLAR = ("ihlal", "golge", "kapali")
_OKUMA_SINIRI = 4_000_000
ARSIV_DUGMESI = {"action": "archive"}
ARSIV_SORUSU = "Sohbet arşivlensin mi?"
_KART_ACIK = ("isleniyor", "denetimde", "reddedildi", "onaylandi")


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


def mod(sd=None) -> str:
    if os.environ.get("ORKESTRA_ARSIV_DUGMESI") == "0":
        return "kapali"
    m = ayar_oku(sd).get("mod", "kapali")
    return m if m in MODLAR else "kapali"


def wrap_up_mi(arac: str) -> bool:
    return str(arac or "").split("__")[-1] == "wrap_up"


def _bagli_is(sd: str, oid):
    d = _json_oku(os.path.join(sd, "oturumlar", f"{oid}.json")) or {}
    return str(d["is"]) if d.get("is") else None


def acik_is(sd: str, oid) -> str:
    """Oturumda açık iş varsa nedenini, yoksa '' döner: açık kart, onay bekleyen iş, bağlı işte açık todo maddesi."""
    try:
        for k in L.kartlar(sd):
            if k.get("oturum") == oid and L.kart_durumu_hesapla(k) in _KART_ACIK:
                return f"açık kart {k.get('id')}"
    except Exception:
        pass
    try:
        import is_kaydi
        import is_onay
        is_id = _bagli_is(sd, oid)
        kayit = is_kaydi.is_al(sd, is_id) if is_id else None
        if kayit and kayit.get("durum") != "kapandi":
            if is_onay.bekliyor_mu(kayit):
                return f"iş {is_id} onay bekliyor"
            klasor = str(kayit.get("klasor") or "")
            acik = is_kaydi.todo_ozet(klasor)["acik_maddeler"] if klasor else []
            if acik:
                return f"iş {is_id} todo'sunda {len(acik)} açık madde"
    except Exception:
        pass
    return ""


def dugme_girdisi(arac: str, girdi: dict, sd: str, oid, agent_id=None):
    """`wrap_up` girdisi düğmesiz ve soru taşımıyor, oturumda açık iş yoksa arşiv düğmeli kopyayı döner; aksi halde None."""
    if agent_id or not oid or not wrap_up_mi(arac) or mod(sd) == "kapali":
        return None
    girdi = girdi or {}
    if str(girdi.get("ask") or "").strip() or girdi.get("actions"):
        return None
    if acik_is(sd, oid):
        return None
    yeni = dict(girdi)
    # Uygulama kutuyu yalnız `ask` + `actions` birlikte varsa çizer (canlı deneme 05.11.2026); ask'siz düğme çizilmez.
    yeni["ask"] = str(ayar_oku(sd).get("ask") or ARSIV_SORUSU)
    yeni["actions"] = [dict(ARSIV_DUGMESI)]
    return yeni


def _gercek_kullanici_mesaji(o: dict) -> bool:
    if o.get("type") != "user" or o.get("isSidechain") or o.get("isMeta"):
        return False
    icerik = (o.get("message") or {}).get("content")
    if isinstance(icerik, str):
        return bool(icerik.strip())
    return any(isinstance(b, dict) and b.get("type") == "text" for b in icerik or [])


def tur_cagrilari(transkript) -> list[tuple[str, dict]]:
    """Son gerçek kullanıcı mesajından sonra ana ajanın araç çağrıları: [(ad, girdi)]. Okunamazsa boş."""
    if not transkript:
        return []
    try:
        with open(transkript, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - _OKUMA_SINIRI))
            satirlar = f.read().splitlines()
    except Exception:
        return []
    cagrilar: list[tuple[str, dict]] = []
    for ham in satirlar:
        try:
            o = json.loads(ham)
        except Exception:
            continue
        if not isinstance(o, dict):
            continue
        if _gercek_kullanici_mesaji(o):
            cagrilar = []
            continue
        if o.get("type") != "assistant" or o.get("isSidechain"):
            continue
        icerik = (o.get("message") or {}).get("content")
        for b in icerik if isinstance(icerik, list) else []:
            if isinstance(b, dict) and b.get("type") == "tool_use":
                girdi = b.get("input") if isinstance(b.get("input"), dict) else {}
                cagrilar.append((str(b.get("name") or ""), girdi))
    return cagrilar


def arac_adi(sd=None) -> str:
    """Kapanış kutusu aracının adı (ayar `arac`); modüle araç adı gömülmez."""
    return str(ayar_oku(sd).get("arac") or "")


def stop_karar(transkript, yanit, sd: str, oid, inp: dict | None = None) -> tuple[str, str]:
    """(ihlal nedeni, atlanma nedeni). Aday ihlal var ama kapanış aracı oturumda yoksa ('', 'arac_yok'): araç yoksa
    istek düşer, düz metin kapanış kabul edilir (ADR-0180). Araç varsa ya da bilinmiyorsa eski sonuç döner."""
    tetik = _stop_tetik(transkript, yanit, sd, oid, inp)
    if not tetik:
        return "", ""
    try:
        import arac_listesi
        ad = arac_adi(sd)
        if ad and arac_listesi.var_mi(transkript, ad) is False:
            return "", "arac_yok"
    except Exception:
        pass
    return tetik, ""


def stop_tetik(transkript, yanit, sd: str, oid, inp: dict | None = None) -> str:
    """Stop'ta ihlal nedeni ('' = ihlal yok); kapanış aracı oturumda yoksa da ''."""
    return stop_karar(transkript, yanit, sd, oid, inp)[0]


def _stop_tetik(transkript, yanit, sd: str, oid, inp: dict | None = None) -> str:
    """Araç varlığına bakmadan ihlal nedeni: çalışma turu, açık iş yok, kapanış teklif/soru değil, `wrap_up` çağrılmadı."""
    inp = inp or {}
    if mod(sd) == "kapali" or inp.get("agent_id") or inp.get("background_tasks"):
        return ""
    ayar = ayar_oku(sd)
    cagrilar = tur_cagrilari(transkript)
    if not cagrilar or any(wrap_up_mi(ad) for ad, _ in cagrilar):
        return ""
    plan = tuple(ayar.get("plan_araclari") or ())
    degisiklik = tuple(ayar.get("degisiklik_araclari") or ())
    tetik = ""
    for ad, _ in cagrilar:
        if plan and ad.endswith(plan):
            tetik = "plan_acik"
            break
        if ad in degisiklik:
            tetik = "degisiklik"
    if not tetik or acik_is(sd, oid):
        return ""
    if any(ad.endswith("AskUserQuestion") for ad, _ in cagrilar):
        return ""
    try:
        import secim_ekrani_hatirlatma as SH
        if SH.teklif_sonu(yanit, sd):
            return ""
    except Exception:
        pass
    return tetik


def hatirlatma_metni(sd=None) -> str:
    return str(ayar_oku(sd).get("hatirlatma") or "")
