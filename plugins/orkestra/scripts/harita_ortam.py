"""Sistem haritası `ortamlar` katmanı (I-249; model çağırmaz).

Teknolojiler katmanıyla aynı adaylardan (manifestler) türer: her codebase için manifest, kilit türü, ortam yolu ve veri kaynağı
profili adları. Ortam birimi codebase'dir; proje ve git dışında `<ortam_koku>/<proje>/<codebase>` altında kurulur (Node'da
`node_modules` codebase klasöründe kalır). Sır değeri taşımaz: veri kaynağı yalnız profil adıyla anılır.
Ayar: `ayarlar/ortam.json` (eklenti) + `<durum>/ortam.json` (proje: haric, proje_adi, ortam_koku, veri_kaynaklari, codebase_veri).
"""
from __future__ import annotations

import json
import os

AYAR_YOLU = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ayarlar", "ortam.json")
LOCK_ADLARI = ("uv.lock", "package-lock.json", "poetry.lock")
KATMAN_KIMLIK = "ortam:"


def _json(yol) -> dict:
    try:
        with open(yol, encoding="utf-8") as f:
            veri = json.load(f)
        return veri if isinstance(veri, dict) else {}
    except (OSError, ValueError):
        return {}


def _ayar_yolu() -> str:
    return os.environ.get("ORKESTRA_ORTAM_AYAR") or AYAR_YOLU


def ayar_oku(sd: str | None = None) -> dict:
    """Eklenti ayarı üstüne proje ayarı (`<sd>/ortam.json`); haric listeleri birleşir."""
    a = _json(_ayar_yolu())
    p = _json(os.path.join(sd, "ortam.json")) if sd else {}
    sonuc = dict(a)
    sonuc.update({k: v for k, v in p.items() if k not in ("haric", "mod")})
    sonuc["haric"] = [str(h).strip("/") for h in list(a.get("haric") or []) + list(p.get("haric") or [])]
    sonuc.setdefault("ortam_koku", "~/.venvs")
    sonuc.setdefault("mod", "golge")
    sonuc.setdefault("python_tercih", ["3.13", "3.12", "3.11"])
    sonuc.setdefault("veri_kaynaklari", {})
    sonuc.setdefault("codebase_veri", {})
    return sonuc


def ayar_imzasi(sd: str | None = None) -> str:
    """Ayar dosyaları değişince katman eskir (imzaya girer)."""
    parca = []
    for yol in (_ayar_yolu(), os.path.join(sd, "ortam.json") if sd else None):
        if not yol:
            continue
        try:
            st = os.stat(yol)
            parca.append(f"{os.path.basename(yol)}|{st.st_size}|{st.st_mtime_ns}")
        except OSError:
            parca.append(f"{os.path.basename(yol)}|yok")
    return ";".join(parca)


def ortam_koku(ayar: dict) -> str:
    return os.path.expanduser(os.environ.get("ORKESTRA_ORTAM_KOKU") or ayar.get("ortam_koku") or "~/.venvs")


def proje_adi(kok: str, ayar: dict) -> str:
    ad = ayar.get("proje_adi") or os.path.basename(os.path.abspath(kok)) or "kok"
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in ad)


def aday(rel: str) -> bool:
    """Teknolojiler adaylarına ek olarak kilit dosyaları (imza kilit değişimini de görsün)."""
    import harita as H
    return H._aday_teknoloji(rel) or os.path.basename(rel) in LOCK_ADLARI


def _py_manifest(ad: str) -> bool:
    return (ad.startswith("requirements") and ad.endswith(".txt")) or ad == "pyproject.toml"


def kilit_sec(tur: str, adlar: set[str]) -> tuple[str, str]:
    """(kilit türü, kilit dosyası): uv.lock > requirements.txt > pyproject; Node'da package-lock.json."""
    if tur == "python":
        if "uv.lock" in adlar:
            return "uv", "uv.lock"
        if "requirements.txt" in adlar:
            return "pip", "requirements.txt"
        return "pip-pyproject", "pyproject.toml"
    if "package-lock.json" in adlar:
        return "npm-ci", "package-lock.json"
    return "kilitsiz", "package.json"


def tara(adaylar, kok, sd):
    import harita as H
    import harita_teknoloji as T
    ayar = ayar_oku(sd)
    haric = ayar["haric"]
    esleme, _ = T.projeler([rel for rel, _, _, _ in adaylar])
    gruplar: dict[str, list[str]] = {}
    for rel, proje in esleme.items():
        gruplar.setdefault(proje, []).append(rel)
    koku, pad = ortam_koku(ayar), proje_adi(kok, ayar)
    t = H._Toplayici()
    for proje, dosyalar in sorted(gruplar.items()):
        if any(T._altinda(proje, h) for h in haric):
            continue
        adlar = {os.path.basename(r) for r in dosyalar if os.path.dirname(r) == proje}
        py = sorted(a for a in adlar if _py_manifest(a))
        node = "package.json" in adlar
        if not py and not node:
            continue
        tur = "python" if py else "node"
        kilit_tur, kilit_dosya = kilit_sec(tur, adlar)
        cb = os.path.basename(proje) if proje not in ("", ".") else os.path.basename(os.path.abspath(kok))
        yol = os.path.normpath(os.path.join(koku, pad, cb) if tur == "python" else os.path.join(os.path.abspath(kok), proje, "node_modules"))
        kid = f"{KATMAN_KIMLIK}{proje or '.'}"
        t.ekle(kid, cb, proje or ".", f"{tur} codebase, kilit: {kilit_tur}, ortam: {yol}")
        t.kayit[kid].update(dizin=proje or ".", tur=tur, kilit_turu=kilit_tur, kilit_dosyasi=kilit_dosya, manifestler=py or ["package.json"],
                            ortam_yolu=yol, veri_kaynaklari=sorted(ayar["codebase_veri"].get(proje, [])))
    return t.liste()
