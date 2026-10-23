"""Tek main için artık dal temizliği (I-201, ADR-0050).

`main`'e tamamen birleşmiş, hiçbir worktree'de açık olmayan ve çağıran oturumun olmayan yerel dallar adaydır.
Mod `ayarlar/dal_temizle.json` (proje ezmesi: durum klasöründe `dal_temizle.json`) `mod` alanındandır:
- golge: adaylar yalnız gunluk.jsonl'a `dal_temizle` olarak yazılır, dal silinmez (varsayılan, P-028).
- ihlal: her aday önce `git bundle` ile yedeklenir, sonra `git branch -d` ile silinir; bundle başarısızsa silinmez.
`main`'e birleşmemiş dala hiçbir modda dokunulmaz. Hiçbir çağrı istisna fırlatmaz. Kapatma: ORKESTRA_DAL_TEMIZLE=0.
"""
from __future__ import annotations

import os
import subprocess
import time

import cfg
import kapi_mod
import ork_lib as L

ANA = "main"


def _git(depo: str, *a: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", depo, *a], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60, **cfg.PENCERESIZ)


def _worktree_dallari(depo: str) -> tuple[str, set[str]]:
    """(ana worktree yolu, worktree'lerde açık dal adları)."""
    r = _git(depo, "worktree", "list", "--porcelain")
    ana, dallar = "", set()
    for blok in r.stdout.split("\n\n"):
        yol = dal = ""
        for satir in blok.splitlines():
            if satir.startswith("worktree "):
                yol = satir[9:]
            elif satir.startswith("branch refs/heads/"):
                dal = satir[18:]
        if yol and not ana:
            ana = yol
        if dal:
            dallar.add(dal)
    return ana, dallar


def adaylar(depo: str, oturum_dali: str = "") -> dict:
    """{'aday': [...], 'birlesmemis': [...]}: worktree'de açık olmayan, oturum dalı ve main dışındaki yerel dallar."""
    _, acik = _worktree_dallari(depo)
    r = _git(depo, "for-each-ref", "--format=%(refname:short)", "refs/heads")
    aday, birlesmemis = [], []
    for dal in r.stdout.split():
        if dal in (ANA, oturum_dali) or dal in acik:
            continue
        ata = _git(depo, "merge-base", "--is-ancestor", dal, ANA).returncode == 0
        (aday if ata else birlesmemis).append(dal)
    return {"aday": aday, "birlesmemis": birlesmemis}


def _yedekle(depo: str, ana_yol: str, dallar: list[str]) -> str:
    """Dalları tek bundle'a alır ve doğrular; yol döner, başarısızsa ''."""
    klasor = os.path.join(ana_yol, "_arsiv", os.path.basename(os.path.normpath(ana_yol)))
    os.makedirs(klasor, exist_ok=True)
    yol = os.path.join(klasor, "dal_yedek_" + time.strftime("%Y%m%d_%H%M%S") + ".bundle")
    refs = ["refs/heads/" + d for d in dallar]
    if _git(depo, "bundle", "create", yol, *refs).returncode != 0:
        return ""
    return yol if _git(depo, "bundle", "verify", yol).returncode == 0 else ""


def temizle(depo: str, oturum_dali: str = "", kip: str = "golge") -> dict:
    """Adayları bulur; kip `ihlal` ise yedekleyip siler. {'kip','aday','silinen','birlesmemis','bundle','hata'}."""
    s = {"kip": kip, "aday": [], "silinen": [], "birlesmemis": [], "bundle": "", "hata": ""}
    try:
        a = adaylar(depo, oturum_dali)
        s["aday"], s["birlesmemis"] = a["aday"], a["birlesmemis"]
        if kip != "ihlal" or not s["aday"]:
            return s
        ana_yol, _ = _worktree_dallari(depo)
        s["bundle"] = _yedekle(depo, ana_yol or depo, s["aday"])
        if not s["bundle"]:
            s["hata"] = "bundle alınamadı; silinmedi"
            return s
        for dal in s["aday"]:
            if _git(depo, "branch", "-d", dal).returncode == 0:
                s["silinen"].append(dal)
    except Exception as e:  # hook'u ve kapanışı asla düşürme
        s["hata"] = str(e)[:200]
    return s


def calistir(cwd: str, oturum_dali: str = "", kaynak: str = "") -> dict | None:
    """Mod ayardan okunur, sonuç günlüğe yazılır. Kapalıysa ya da yapacak bir şey yoksa None."""
    if os.environ.get("ORKESTRA_DAL_TEMIZLE") == "0":
        return None
    try:
        kip = kapi_mod.mod("dal_temizle", cwd)
        if not oturum_dali:
            oturum_dali = _git(cwd, "symbolic-ref", "--short", "-q", "HEAD").stdout.strip()
        s = temizle(cwd, oturum_dali, kip)
        if s["aday"] or s["hata"]:
            sd = L.durum_dizini(cwd)
            if sd:
                L.jsonl_ekle(os.path.join(sd, "gunluk.jsonl"), {"zaman": L.simdi(), "tur": "dal_temizle", "kaynak": kaynak, **s})
        return s
    except Exception:
        return None


def kapanis(cwd: str) -> str:
    """`orkestra is kapat` sonrası: artık dalları temizler (kipe göre) ve oturum dalı main'e birleşmemişse uyarı metni döndürür.
    Oturum dalının kendisi çalışan worktree'de açık olduğundan burada silinemez; worktree kalkınca SessionStart temizliği siler."""
    try:
        calistir(cwd, kaynak="is_kapat")
        dal = _git(cwd, "symbolic-ref", "--short", "-q", "HEAD").stdout.strip()
        if dal and dal != ANA and _git(cwd, "merge-base", "--is-ancestor", dal, ANA).returncode != 0:
            return f"oturum dalı '{dal}' main'e birleşmemiş; birleştirmeden dal temizlenmez (git merge --ff-only {dal} main'de)."
    except Exception:
        pass
    return ""
