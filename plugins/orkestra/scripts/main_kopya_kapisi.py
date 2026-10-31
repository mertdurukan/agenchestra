"""Korunan deponun birincil `main` kopyasına doğrudan yazmayı yakalar (I-302, ADR-0122).

Birincil kopya: `.git` DİZİN olan ve HEAD'i `refs/heads/main` olan çalışma kopyası. Ayrı çalışma ağacında `.git` bir
DOSYADIR; ona yazmak her modda serbesttir. Korunan depo yolları `ayarlar/main_kopya_kapisi.json` `korunan` listesinden gelir
(proje ezmesi: durum klasöründeki `main_kopya_kapisi.json`); kodda depo adı yoktur. Git alt süreci çalıştırılmaz.
Kapatma: ORKESTRA_MAIN_KOPYA_KAPISI=0. Mod (golge | ihlal) `kapi_mod` ile okunur.
"""
from __future__ import annotations

import json
import os

import ork_lib as L

KAPI = "main_kopya_kapisi"


def _ayar_korunan(klasor: str | None = None) -> list[str]:
    """Korunan depo kökleri: eklenti ayarı + proje ezmesi; `~` açılır."""
    kok = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    yollar = [os.path.join(kok, "ayarlar", KAPI + ".json")]
    sd = L.durum_dizini(klasor) if klasor else None
    if sd:
        yollar.append(os.path.join(sd, KAPI + ".json"))
    sonuc: list[str] = []
    for yol in yollar:
        try:
            with open(yol, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            continue
        liste = d.get("korunan") if isinstance(d, dict) else None
        if isinstance(liste, list):
            sonuc += [os.path.expanduser(x) for x in liste if isinstance(x, str) and x.strip()]
    return sonuc


def _git_koku(yol: str) -> str | None:
    """`yol`dan yukarı yürüyerek `.git` içeren ilk klasör (dizin ya da dosya); yoksa None. Yol henüz var olmayabilir."""
    d = os.path.abspath(yol)
    while True:
        if os.path.exists(os.path.join(d, ".git")):
            return d
        ust = os.path.dirname(d)
        if ust == d:
            return None
        d = ust


def _head_main(kok: str) -> bool:
    try:
        with open(os.path.join(kok, ".git", "HEAD"), encoding="utf-8") as f:
            return f.read().strip() == "ref: refs/heads/main"
    except OSError:
        return False


def birincil_kopya(yol: str, korunan: list[str]) -> str | None:
    """`yol` korunan depodaki birincil `main` kopyasındaysa kopyanın kökü; ayrı çalışma ağacı, başka dal ya da
    korunmayan depo için None."""
    if not yol or not korunan:
        return None
    kok = _git_koku(yol)
    if not kok or not os.path.isdir(os.path.join(kok, ".git")):
        return None  # `.git` dosya: ayrı çalışma ağacı
    if not any(L.yol_altinda(kok, k) and L.yol_altinda(k, kok) for k in korunan):
        return None
    return kok if _head_main(kok) else None


def acik_mi() -> bool:
    return os.environ.get("ORKESTRA_MAIN_KOPYA_KAPISI") != "0"


def karar(yol: str, cwd: str | None, oturum: str = "") -> tuple[str, str] | None:
    """Kapının sonucu: None (geç) ya da (mod, mesaj). Kayıt ve ret çağıranındır."""
    if not acik_mi():
        return None
    kok = birincil_kopya(yol, _ayar_korunan(cwd))
    if not kok:
        return None
    import kapi_mod
    m = kapi_mod.mod(KAPI, cwd)
    mesaj = (f"{os.path.abspath(yol)} korunan deponun birincil main kopyasında ({kok}); bu kopya yalnız birleştirme yeridir. "
             f"Değişikliği ayrı çalışma ağacında yap: git -C \"{kok}\" worktree add <yol> -b <dal> main")
    return m, mesaj
