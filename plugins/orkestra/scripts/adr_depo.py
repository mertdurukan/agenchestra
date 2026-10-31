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


def _en_buyuk(adlar):
    en = 0
    for ad in adlar:
        m = _NO.match(os.path.basename(ad.strip()))
        if m:
            en = max(en, int(m.group(1)))
    return en


def sonraki_no(kok):
    """Deponun en büyük ADR numarasının sonrası (boşsa 1).

    Numara yalnız bu çalışma ağacından değil, depodaki bütün yerel dallardan ve bütün çalışma ağaçlarının
    adr/ klasörlerinden (işlenmemiş dosyalar dahil) türer; paralel dallar aynı numarayı almaz (I-292 kök nedeni).
    """
    en = _en_buyuk(glob.glob(os.path.join(kok, "adr", "ADR-*.md")))
    r = L.git(["for-each-ref", "--format=%(refname)", "refs/heads", "refs/remotes"], kok)
    if r.returncode == 0:
        for ref in r.stdout.split():
            t = L.git(["ls-tree", "--name-only", ref, "adr/"], kok)
            if t.returncode == 0:
                en = max(en, _en_buyuk(t.stdout.splitlines()))
    w = L.git(["worktree", "list", "--porcelain"], kok)
    if w.returncode == 0:
        for satir in w.stdout.splitlines():
            if satir.startswith("worktree "):
                en = max(en, _en_buyuk(glob.glob(os.path.join(satir[9:].strip(), "adr", "ADR-*.md"))))
    return en + 1


def uzak_var(kok):
    """Depoda tanımlı en az bir git uzak adresi var mı (adres okunmaz, yazılmaz)."""
    r = L.git(["remote"], kok)
    return r.returncode == 0 and bool(r.stdout.strip())
