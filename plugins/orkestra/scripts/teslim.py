"""Teslim kapısı (ADR-0035, P3): kod değişikliği taşıyan işin kapanışında PR, CI sonucu ve inceleme kaydı.

Kapı yalnız şu durumda denetler: `ORKESTRA_TESLIM_KAPISI` kapalı değil, işin git ağacında `origin` uzak deposu var ve iş açıldığından
beri kod dosyası değişmiş. Aksi hâlde muaftır (uzak deposuz projeler, yalnız belge işleri). Mod `ayarlar/teslim.json`:
golge uyarır ve `kapi_golge` kaydı düşer, ihlal `is kapat`ı reddeder (kapi_mod.py).

İnceleme kanıtı: PR'ın GitHub `reviewDecision` değeri APPROVED ya da `orkestra is teslim <iş> --inceleme "<kim/ne>"` kaydı.
`gh` çağrısı `_gh` ile yapılır; testler bunu değiştirir.
"""
from __future__ import annotations

import json
import os
import subprocess

import kapi_mod as KM
import ork_lib as L

KOD_UZANTILARI = {".py", ".js", ".ts", ".tsx", ".jsx", ".sh", ".ps1", ".css", ".html", ".sql", ".tf", ".yml", ".yaml"}
ATLANAN_YOLLAR = ("adr/", ".claude/", "_arsiv/")


def kapi_acik() -> bool:
    return os.environ.get("ORKESTRA_TESLIM_KAPISI") != "0"


def _gh(args: list[str], cwd: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["gh"] + args, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
    except (OSError, subprocess.TimeoutExpired) as e:
        return subprocess.CompletedProcess(args, 1, "", str(e))


def uzak_var_mi(git_kok: str) -> bool:
    return L.git(["remote", "get-url", "origin"], git_kok).returncode == 0


def kod_dosyalari(git_kok: str, klasor: str, baslangic: str | None) -> list[str]:
    """İş açıldığından beri (commit'ler `--since`, çalışma ağacı değişiklikleri) değişen kod dosyaları; iş klasörü, adr/, .claude/ hariç."""
    adlar: set[str] = set()
    if baslangic:
        r = L.git(["log", f"--since={baslangic}", "--name-only", "--format="], git_kok)
        if r.returncode == 0:
            adlar |= {s.strip() for s in r.stdout.splitlines() if s.strip()}
    r = L.git(["status", "--porcelain"], git_kok)
    if r.returncode == 0:
        adlar |= {s[3:].strip().strip('"').split(" -> ")[-1] for s in r.stdout.splitlines() if len(s) > 3}
    try:
        is_goreli = os.path.relpath(os.path.abspath(klasor), git_kok).replace("\\", "/").rstrip("/") + "/"
    except ValueError:
        is_goreli = None
    sonuc = []
    for a in sorted(adlar):
        n = a.replace("\\", "/")
        if n.startswith(ATLANAN_YOLLAR) or (is_goreli and n.startswith(is_goreli)):
            continue
        if os.path.splitext(n)[1].lower() in KOD_UZANTILARI:
            sonuc.append(n)
    return sonuc


def ci_durumu(rollup) -> str:
    """statusCheckRollup → 'yesil' | 'kirmizi' | 'bekliyor' | 'yok'. CheckRun (conclusion/status) ve StatusContext (state) biçimlerini okur."""
    if not isinstance(rollup, list) or not rollup:
        return "yok"
    bekliyor = False
    for k in rollup:
        if not isinstance(k, dict):
            continue
        sonuc = str(k.get("conclusion") or k.get("state") or "").upper()
        durum = str(k.get("status") or "").upper()
        if sonuc in ("FAILURE", "ERROR", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED", "STARTUP_FAILURE"):
            return "kirmizi"
        if sonuc in ("SUCCESS", "NEUTRAL", "SKIPPED"):
            continue
        if sonuc in ("PENDING", "EXPECTED", "") or (durum and durum != "COMPLETED"):
            bekliyor = True
    return "bekliyor" if bekliyor else "yesil"


def pr_oku(pr: str, git_kok: str) -> dict | None:
    """`gh pr view [<pr>] --json …`; PR yoksa ya da gh çalışmazsa None. `pr` boşsa geçerli dalın PR'ı aranır."""
    args = ["pr", "view"] + ([pr] if pr else []) + ["--json", "statusCheckRollup,reviewDecision,state,url"]
    r = _gh(args, git_kok)
    if r.returncode != 0:
        return None
    try:
        v = json.loads(r.stdout)
    except ValueError:
        return None
    return v if isinstance(v, dict) else None


def teslim_eksigi(sd: str, kayit: dict) -> list[str]:
    """Kapanış için teslim eksikleri. Muafsa ya da gölge modundaysa boş liste (gölge: uyarı + kayıt)."""
    if not kapi_acik():
        return []
    klasor = str(kayit.get("klasor") or "")
    git_kok = L.git_koku(klasor) if klasor and os.path.isdir(klasor) else None
    if not git_kok or not uzak_var_mi(git_kok):
        return []
    dosyalar = kod_dosyalari(git_kok, klasor, kayit.get("olusturma"))
    if not dosyalar:
        return []
    t = kayit.get("teslim") if isinstance(kayit.get("teslim"), dict) else {}
    pr = pr_oku(str(t.get("pr") or ""), git_kok)
    eksik = []
    ci = None
    if pr is None:
        eksik.append(f"{len(dosyalar)} kod dosyası değişti ama PR bulunamadı (dalı PR olarak aç; `orkestra is teslim <iş> --pr <bağlantı>`)")
    else:
        ci = ci_durumu(pr.get("statusCheckRollup"))
        if ci == "kirmizi":
            eksik.append("PR'ın CI sonucu başarısız")
        elif ci == "bekliyor":
            eksik.append("PR'ın CI kontrolleri sürüyor")
        elif ci == "yok":
            eksik.append("PR'da CI sonucu yok")
        if pr.get("reviewDecision") != "APPROVED" and not str(t.get("inceleme") or "").strip():
            eksik.append("inceleme kaydı yok (GitHub onayı ya da `orkestra is teslim <iş> --inceleme \"<kim/ne>\"`)")
    try:
        import is_kaydi
        is_kaydi._degistir(sd, kayit["id"], lambda k: k.setdefault("teslim", {}).update(
            {"ci": ci, "pr_url": (pr or {}).get("url") or t.get("pr") or "", "zaman": L.simdi()}))
    except Exception:  # kayıt kapıyı bozmaz
        pass
    return KM.ihlal_ver(klasor, "teslim", eksik)


def kaydet_girdi(sd: str, is_id: str, pr: str = "", inceleme: str = "") -> dict:
    """`orkestra is teslim` / `is kapat --pr --inceleme`: PR bağlantısı ve inceleme notu is.json `teslim` alanına yazılır."""
    import is_kaydi

    def islem(k):
        t = k.setdefault("teslim", {})
        if pr:
            t["pr"] = pr
        if inceleme:
            t["inceleme"] = inceleme

    return is_kaydi._degistir(sd, is_id, islem)
