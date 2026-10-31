"""Açık karar kapısı (ADR-0112, I-291): mevcut durum §5'teki `**Karar gerekir (D<n>):**` maddesi, kullanıcı yanıtı
kaydedilmeden plan yazılamaz.

Yanıt yalnız is.json `kararlar` alanından sayılır; bu alanı yalnız PostToolUse hook'u yazar (ana ajanın AskUserQuestion
çağrısında soru metni `[D<n>]` etiketini taşıyorsa ve kullanıcı yanıtladıysa). Plan ya da mevcut durum metnine yazılan
"Yanıtlandı" satırı sayılmaz. Kapsam yalnız is.json `karar: true` taşıyan sıralı işlerdir (eski işler muaf).
Kapatma: ORKESTRA_KARAR_KAPISI=0. Mod: ayarlar/karar_kapisi.json (kapi_mod).
"""
from __future__ import annotations

import json
import os
import re

ALAN = "kararlar"
_MADDE = re.compile(r"^[ \t]*[-*][ \t]+\*\*Karar gerekir(?:[ \t]*\((D\d+)\))?:\*\*(.*)$", re.M)
_ETIKET = re.compile(r"\[(D\d+)\]")


def kapi_acik() -> bool:
    return os.environ.get("ORKESTRA_KARAR_KAPISI") != "0"


def kapsaminda_mi(klasor: str) -> bool:
    """İş sıralı ve is.json `karar: true` taşıyor."""
    import is_sirasi as SIRA
    if not kapi_acik() or not SIRA.sirali_mi(klasor):
        return False
    return _is_json(klasor).get("karar") is True


def _is_json(klasor: str) -> dict:
    try:
        with open(os.path.join(klasor, "is.json"), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def maddeler(metin: str) -> list[tuple]:
    """(kimlik ya da None, metin) listesi; yorum satırları (<!-- -->) sayılmaz."""
    sade = re.sub(r"<!--.*?-->", "", metin or "", flags=re.S)
    return [(m.group(1), m.group(2).strip()) for m in _MADDE.finditer(sade)]


def eksikleri(klasor: str) -> list[str]:
    """Boş liste = açık karar yok ya da hepsi kullanıcı yanıtıyla kayıtlı."""
    import is_sirasi as SIRA
    yol = SIRA.mevcut_durum_yolu(klasor)
    if yol is None:
        return []
    metin = SIRA._oku(yol) or ""
    kayitli = _is_json(klasor).get(ALAN)
    kayitli = kayitli if isinstance(kayitli, dict) else {}
    eksik = []
    for kimlik, ozet in maddeler(metin):
        kisa = ozet[:60]
        if kimlik is None:
            eksik.append(f"mevcut durum: `Karar gerekir` maddesinin kimliği yok (`**Karar gerekir (D<n>):**`): {kisa}")
        elif kimlik not in kayitli:
            eksik.append(f"mevcut durum: {kimlik} için kullanıcı yanıtı kayıtlı değil; AskUserQuestion sorusunda `[{kimlik}]` etiketi "
                         f"olmalı ve kullanıcı yanıtlamalı (ADR-0112): {kisa}")
    return eksik


def engel(klasor: str) -> list[str]:
    """Plan kapısı: kapsamdaysa ve mod `ihlal` ise eksikler; `golge` modunda kapi_golge kaydı düşer, boş döner."""
    if not kapsaminda_mi(klasor):
        return []
    eksik = eksikleri(klasor)
    if not eksik:
        return []
    import kapi_mod as KM
    if KM.mod("karar_kapisi", klasor) == "ihlal":
        return eksik
    try:
        KM.kaydet(klasor, "karar_kapisi", "; ".join(eksik)[:300])
    except Exception:
        pass
    return []


def ekran_kararlari(tool_input, tool_response) -> list[tuple]:
    """AskUserQuestion çağrısındaki `[D<n>]` etiketli, yanıtlanmış sorular: (kimlik, yanıt etiketi) listesi."""
    import is_onay
    sonuc = []
    sorular = (tool_input or {}).get("questions") if isinstance(tool_input, dict) else None
    if not isinstance(sorular, list):
        return sonuc
    for s in sorular:
        if not isinstance(s, dict):
            continue
        soru = str(s.get("question") or "")
        m = _ETIKET.search(soru)
        if not m:
            continue
        yanit = is_onay.ekran_yaniti(tool_response, soru)
        if yanit:
            sonuc.append((m.group(1), "; ".join(yanit)[:200]))
    return sonuc


def kaydet(sd: str, is_id: str, kararlar: list[tuple]) -> None:
    """Kullanıcı yanıtlarını is.json `kararlar` alanına yazar (yalnız hook çağırır; ajan komutu yoktur)."""
    if not kararlar:
        return
    import is_kaydi
    import ork_lib as L

    def islem(k):
        d = k.setdefault(ALAN, {})
        for kimlik, etiket in kararlar:
            d[kimlik] = {"yanit": etiket, "zaman": L.simdi()}
        k.setdefault("gecmis", []).append({"zaman": L.simdi(), "olay": "karar:" + ",".join(k_ for k_, _ in kararlar)})

    is_kaydi._degistir(sd, is_id, islem)
