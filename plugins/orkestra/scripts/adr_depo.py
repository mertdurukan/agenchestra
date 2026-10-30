"""ADR hedef deposu (ADR-0097): ADR, planın `**Kök:**` satırının git deposunda yazılır ve aranır.

Kök yoksa ya da aynı depoysa eski davranış (proje kökü + işin klasörünün git ağacı). Numara depo başına ardışıktır.
"""
import glob
import os
import re

import ork_lib as L

_KOK = re.compile(r"^[ \t>*_-]*\*\*Kök:\*\*[ \t]*(\S.*)$", re.M)
_NO = re.compile(r"ADR-(\d{4})-")


def _norm(yol):
    return os.path.normcase(os.path.abspath(yol)).replace("\\", "/")


def kok_deposu(plan_metni):
    """Planın `**Kök:**` satırının git deposu; satır ya da depo yoksa None."""
    m = _KOK.search(plan_metni or "")
    if not m:
        return None
    yol = m.group(1).strip().strip("`")
    if not os.path.isdir(yol):
        return None
    return L.git_koku(yol)


def depolar(plan_metni, klasor, proje_koku):
    """ADR aranacak depo kökleri, öncelik sırasıyla: Kök deposu (varsa), proje kökü, işin klasörünün git ağacı."""
    sira = []
    for k in (kok_deposu(plan_metni), proje_koku,
              L.git_koku(klasor) if klasor and os.path.isdir(klasor) else None):
        if k and _norm(k) not in [_norm(s) for s in sira]:
            sira.append(k)
    return sira


def adr_bul(kimlik, kokler):
    """`ADR-nnnn` dosyası: ilk depodaki eşleşme kazanır (aynı numara iki depoda farklıysa hedef depo önce gelir)."""
    for kok in kokler:
        g = sorted(glob.glob(os.path.join(kok, "adr", kimlik + "-*.md")))
        if g:
            return g[0]
    return None


def sonraki_no(kok):
    """Deponun adr/ klasöründeki en büyük numaranın sonrası (boşsa 1)."""
    en = 0
    for yol in glob.glob(os.path.join(kok, "adr", "ADR-*.md")):
        m = _NO.match(os.path.basename(yol))
        if m:
            en = max(en, int(m.group(1)))
    return en + 1


def uzak_var(kok):
    """Depoda tanımlı en az bir git uzak adresi var mı (adres okunmaz, yazılmaz)."""
    r = L.git(["remote"], kok)
    return r.returncode == 0 and bool(r.stdout.strip())
