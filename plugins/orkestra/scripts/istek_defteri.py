"""İstek defteri (ADR-0110, I-291): kullanıcının işe verdiği her bağlantı ve talep kimlikli madde (R1…Rn) olur;
plan ve kapanış kapısı her maddenin planda karşılığı ya da kullanıcı yanıtıyla çıkarıldığı kaydı olup olmadığını yoklar.

Defter işin klasöründeki `istek_defteri.md` dosyasıdır; satır biçimi `- **R<n>:** <metin> — Hedef: <hedef>`.
Madde karşılanmış sayılır: (a) plan.md'de `R<n>` anılır (örn. `**İstek:** R3`) ya da (b) satırda `Çıkarıldı: D<n>` vardır
ve D<n> is.json `kararlar` alanında (kullanıcı yanıtı, hook yazar) kayıtlıdır.
Kapsam yalnız is.json `istek: true` taşıyan sıralı işlerdir. Mod: ayarlar/istek_defteri.json (kapi_mod; ilk sürüm `golge`).
Kapatma: ORKESTRA_ISTEK_DEFTERI_KAPISI=0.
"""
from __future__ import annotations

import json
import os
import re

DOSYA = "istek_defteri.md"
_URL = re.compile(r"https?://[^\s<>()\[\]\"'`]+")
_SATIR = re.compile(r"^[ \t]*[-*][ \t]+\*\*(R\d+):\*\*(.*)$", re.M)
_CIKARILDI = re.compile(r"Çıkarıldı:\s*(D\d+)")
_R = re.compile(r"\bR(\d+)\b")


def kapi_acik() -> bool:
    return os.environ.get("ORKESTRA_ISTEK_DEFTERI_KAPISI") != "0"


def _is_json(klasor: str) -> dict:
    try:
        with open(os.path.join(klasor, "is.json"), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def kapsaminda_mi(klasor: str) -> bool:
    import is_sirasi as SIRA
    return kapi_acik() and SIRA.sirali_mi(klasor) and _is_json(klasor).get("istek") is True


def baglantilar(metin: str) -> list[str]:
    """Metindeki http(s) bağlantıları, ilk görülüş sırasıyla, tekrarsız; sondaki noktalama atılır."""
    gorulen, sonuc = set(), []
    for m in _URL.finditer(metin or ""):
        u = m.group(0).rstrip(".,;:!?")
        if u not in gorulen:
            gorulen.add(u)
            sonuc.append(u)
    return sonuc


def defter_metni(maddeler: list[str]) -> str:
    satirlar = ["# İstek defteri", "", "Her madde planda `R<n>` ile anılır ya da `Çıkarıldı: D<n>` (kullanıcı yanıtı kayıtlı) taşır.", ""]
    satirlar += [f"- **R{i}:** {m} — Hedef: belirlenecek" for i, m in enumerate(maddeler, 1)]
    return "\n".join(satirlar) + "\n"


def olustur(klasor: str, mesaj: str, ek_talepler: list[str] | None = None) -> list[str]:
    """Mesajdaki bağlantıları ve verilen serbest metin taleplerini deftere yazar; madde metinlerini döner."""
    maddeler = baglantilar(mesaj) + [t.strip() for t in (ek_talepler or []) if t.strip()]
    if not maddeler:
        raise ValueError("mesajda bağlantı yok ve serbest metin talebi verilmedi")
    with open(os.path.join(klasor, DOSYA), "w", encoding="utf-8", newline="\n") as f:
        f.write(defter_metni(maddeler))
    return maddeler


def _oku(yol: str):
    try:
        with open(yol, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


def eksikleri(klasor: str) -> list[str]:
    """Karşılanmamış defter maddeleri; defter yoksa tek eksik. Kapsam dışı iş: boş."""
    if not kapsaminda_mi(klasor):
        return []
    defter = _oku(os.path.join(klasor, DOSYA))
    if defter is None:
        return [f"{DOSYA} yok (`orkestra is istek <iş> --mesaj-dosya <dosya>`; ADR-0110)"]
    plan = _oku(os.path.join(klasor, "plan.md")) or ""
    anilan = {f"R{n}" for n in _R.findall(plan)}
    kararlar = _is_json(klasor).get("kararlar")
    kararlar = kararlar if isinstance(kararlar, dict) else {}
    eksik = []
    for m in _SATIR.finditer(defter):
        kimlik, govde = m.group(1), m.group(2)
        if kimlik in anilan:
            continue
        c = _CIKARILDI.search(govde)
        if c and c.group(1) in kararlar:
            continue
        eksik.append(f"{kimlik}: planda anılmıyor ve kullanıcı yanıtıyla çıkarılmış değil: {govde.strip()[:80]}")
    return eksik


def engel(klasor: str, kapi: str = "istek_defteri") -> list[str]:
    """Plan ve kapanış kapısı: `ihlal` modunda eksikleri döner; `golge` modunda kapi_golge kaydı düşer, boş döner."""
    eksik = eksikleri(klasor)
    if not eksik:
        return []
    import kapi_mod as KM
    if KM.mod("istek_defteri", klasor) == "ihlal":
        return eksik
    try:
        KM.kaydet(klasor, kapi, "; ".join(eksik)[:300])
    except Exception:
        pass
    return []
