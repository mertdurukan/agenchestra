"""Sürekli açık skill gövdelerini SessionStart bağlamına yükler (ADR-0113, I-294).

Yalnız skill_durum.json'daki `surekli` adlar ve açık (kapalı olmayan) skill'ler eklenir. ORKESTRA_SKILL_SUREKLI=0 kapatır.
"""
import os

import araclar_skill as AS

SINIR = 20000  # toplam karakter; aşılırsa kısaltılır ve uyarı satırı eklenir


def _govde(yol: str) -> str:
    with open(yol, encoding="utf-8") as f:
        t = f.read()
    if t.startswith("---"):
        son = t.find("\n---", 3)
        if son != -1:
            t = t[son + 4:]
    return t.strip()


def baglam(proje: str, kullanici_dizin=None, eklenti_dizin=None, sinir: int = SINIR) -> str:
    if os.environ.get("ORKESTRA_SKILL_SUREKLI") == "0":
        return ""
    adlar = sorted(AS.surekli_oku(proje))
    if not adlar:
        return ""
    acik = {s["ad"] for s in AS.liste(proje, kullanici_dizin, eklenti_dizin) if s["konum"] == "surekli"}
    parcalar, atlanan = [], []
    toplam = 0
    for ad in adlar:
        if ad not in acik:
            continue
        yol = AS.govde_yolu(ad, proje, kullanici_dizin, eklenti_dizin)
        if not yol:
            continue
        try:
            metin = f"[Sürekli açık skill: {ad}]\n{_govde(yol)}"
        except OSError:
            continue
        if toplam + len(metin) > sinir:
            kalan = sinir - toplam
            if kalan > 200 and not parcalar:
                parcalar.append(metin[:kalan])
                toplam = sinir
            atlanan.append(ad)
            continue
        parcalar.append(metin)
        toplam += len(metin)
    if atlanan:
        parcalar.append(f"[Uyarı: sürekli açık skill bağlam sınırı ({sinir} karakter) aşıldı; kısaltıldı/atlandı: {', '.join(atlanan)}]")
    return "\n\n".join(parcalar)
