"""Teslim kapısı (ADR-0035, P3): kod değişikliği taşıyan işin kapanışında PR, CI sonucu ve inceleme kaydı.

Kapı yalnız şu durumda denetler: `ORKESTRA_TESLIM_KAPISI` kapalı değil, işin git ağacında ayardaki uzak depo (`uzak_depo`,
varsayılan `origin`; I-433) var ve iş açıldığından beri kod dosyası değişmiş. Aksi hâlde muaftır (uzak deposuz projeler, yalnız belge işleri). Mod `ayarlar/teslim.json`:
golge uyarır ve `kapi_golge` kaydı düşer, ihlal `is kapat`ı reddeder (kapi_mod.py).

İnceleme kanıtı: PR'ın GitHub `reviewDecision` değeri APPROVED ya da `orkestra is teslim <iş> --inceleme "<kim/ne>"` kaydı.
`gh` çağrısı `_gh` ile yapılır; testler bunu değiştirir.
Yerel birleşme (I-433): PR'sız depoda kullanıcı terminalinden `orkestra is kapat <iş> --yerel-birlesme <commit>`; commit ana dalda
(`ana_dal` ayarı, yoksa uzak HEAD, `main`, `master`) ise teslim kaydına `yerel_birlesme` yazılır ve kapı PR yerine onu kabul eder.
PR ya da kullanıcı kararı beklenen işte is.json `bekliyor: <neden>` alanı tutulur (kapanışta silinir).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import cfg  # noqa: E402

import kapi_mod as KM
import ork_lib as L

KOD_UZANTILARI = {".py", ".js", ".ts", ".tsx", ".jsx", ".sh", ".ps1", ".css", ".html", ".sql", ".tf", ".yml", ".yaml"}
ATLANAN_PARCALAR = ("/.claude/", "/_arsiv/")
ATLANAN_YOLLAR = ("adr/", ".claude/", "_arsiv/")


def kapi_acik() -> bool:
    return os.environ.get("ORKESTRA_TESLIM_KAPISI") != "0"


def _gh(args: list[str], cwd: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["gh"] + args, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30, **cfg.PENCERESIZ)
    except (OSError, subprocess.TimeoutExpired) as e:
        return subprocess.CompletedProcess(args, 1, "", str(e))


VARSAYILAN_UZAK = "origin"


def ayar(klasor: str | None = None, kesin: bool = False) -> dict:
    """`ayarlar/teslim.json` + proje ezmesi (`<durum>/teslim.json`, anahtar bazında); bozuk/eksik dosya atlanır.
    `kesin=True`: ezme verilen yolun kendi projesinden okunur, CLAUDE_PROJECT_DIR yok sayılır (I-459: kod başka depoda)."""
    kok = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    yollar = [os.path.join(kok, "ayarlar", "teslim.json")]
    if klasor and kesin:
        sd = os.path.join(L.proje_dizini(klasor, ortami_yoksay=True), ".claude", "orkestra")
    else:
        sd = L.durum_dizini(klasor) if klasor else None
    if sd:
        yollar.append(os.path.join(sd, "teslim.json"))
    d: dict = {}
    for yol in yollar:
        try:
            with open(yol, encoding="utf-8") as f:
                v = json.load(f)
            if isinstance(v, dict):
                d.update(v)
        except (OSError, ValueError):
            pass
    return d


def uzak_adi(klasor: str | None = None, kesin: bool = False) -> str:
    """Teslim kapısının baktığı uzak depo adı (`uzak_depo`; varsayılan `origin`)."""
    ad = str(ayar(klasor, kesin).get("uzak_depo") or "").strip()
    return ad or VARSAYILAN_UZAK


def uzak_var_mi(git_kok: str, ad: str = VARSAYILAN_UZAK) -> bool:
    return bool(ad) and L.git(["remote", "get-url", ad], git_kok).returncode == 0


def ana_dal(git_kok: str, klasor: str | None = None, kesin: bool = False) -> str | None:
    """Ana dal: ayardaki `ana_dal`; yoksa `<uzak>/HEAD`'in gösterdiği dal; yoksa yerelde `main`, `master`,
    `init.defaultBranch` sırasıyla var olan ilk dal. Bulunamazsa None."""
    a = str(ayar(klasor or git_kok, kesin).get("ana_dal") or "").strip()
    if a:
        return a
    uzak = uzak_adi(klasor or git_kok, kesin)
    r = L.git(["symbolic-ref", "--quiet", "--short", f"refs/remotes/{uzak}/HEAD"], git_kok)
    if r.returncode == 0 and r.stdout.strip():
        uzak_dal = r.stdout.strip()  # `<uzak>/<dal>`
        yerel = uzak_dal.split("/", 1)[-1]
        # yerel birleşme henüz itilmemiş olabilir: aynı adlı yerel dal varsa o, yoksa uzak izleme dalı
        return yerel if L.git(["rev-parse", "--verify", "--quiet", f"refs/heads/{yerel}"], git_kok).returncode == 0 else uzak_dal
    adaylar = ["main", "master"]
    r = L.git(["config", "--get", "init.defaultBranch"], git_kok)
    if r.returncode == 0 and r.stdout.strip():
        adaylar.append(r.stdout.strip())
    for d in adaylar:
        if L.git(["rev-parse", "--verify", "--quiet", f"refs/heads/{d}"], git_kok).returncode == 0:
            return d
    return None


def yerel_birlesme_dogrula(git_kok: str, commit: str, klasor: str | None = None,
                           kesin: bool = False) -> tuple[dict | None, str]:
    """Commit ana dalda mı (`git merge-base --is-ancestor`)? (kanıt, '') ya da (None, neden).
    `kesin=True`: ana dal ayarı `klasor`ün kendi projesinden okunur (I-459 `--depo`)."""
    commit = (commit or "").strip()
    if not commit or commit.startswith("-"):
        return None, "commit verilmedi"
    r = L.git(["rev-parse", "--verify", "--quiet", commit + "^{commit}"], git_kok)
    if r.returncode != 0 or not r.stdout.strip():
        return None, f"commit bulunamadı: {commit}"
    sha = r.stdout.strip()
    dal = ana_dal(git_kok, klasor, kesin)
    if not dal:
        return None, "ana dal bulunamadı (ayarlar/teslim.json ya da .claude/orkestra/teslim.json `ana_dal` ile ver)"
    if L.git(["merge-base", "--is-ancestor", sha, dal], git_kok).returncode != 0:
        return None, f"commit {sha[:12]} ana dalda ({dal}) değil"
    return {"commit": sha, "dal": dal, "zaman": L.simdi()}, ""


def bekliyor_neden(kayit: dict | None) -> str:
    """İşin `bekliyor` alanı (PR/kullanıcı kararı bekleniyor); yoksa ''."""
    return str((kayit or {}).get("bekliyor") or "").strip()


def bekliyor_hatirlatma(is_id: str, neden: str) -> str:
    """Todo'su biten ama PR/kullanıcı kararı bekleyen işin hatırlatması: kapanış komutu ya da kapıyı geçme seçeneği
    sunmaz; model kullanıcı kararını bekler (I-433)."""
    return (f"{is_id}: tüm todo maddeleri bitti, iş açık kalır; kullanıcı kararını bekle (PR/inceleme): {neden[:200]}. "
            "Yanıtta yalnız bekleyen kararı ve bağlantısını bildir, başka seçenek önerme; birleştirme/inceleme kararı "
            "kullanıcınındır.")


def bekliyor_yaz(sd: str, is_id: str, neden: str) -> None:
    """is.json `bekliyor` alanını yazar (boş neden siler). Kaydı olmayan iş ya da hata kapıyı bozmaz."""
    try:
        import is_kaydi

        def islem(k):
            if neden:
                k["bekliyor"] = neden[:300]
            else:
                k.pop("bekliyor", None)

        is_kaydi._degistir(sd, is_id, islem)
    except Exception:
        pass


def kod_dosyalari(git_kok: str, klasor: str, baslangic: str | None) -> list[str]:
    """İş açıldığından beri (commit'ler `--since`, çalışma ağacı değişiklikleri) değişen kod dosyaları; iş klasörü, adr/, .claude/ hariç."""
    adlar: set[str] = set()
    if baslangic:
        r = L.git(["-c", "core.quotepath=off", "log", f"--since={baslangic}", "--name-only", "--format="], git_kok)
        if r.returncode == 0:
            adlar |= {s.strip() for s in r.stdout.splitlines() if s.strip()}
    r = L.git(["-c", "core.quotepath=off", "status", "--porcelain", "-uall"], git_kok)
    if r.returncode == 0:
        adlar |= {s[3:].strip().strip('"').split(" -> ")[-1] for s in r.stdout.splitlines() if len(s) > 3}
    try:
        is_goreli = os.path.relpath(os.path.abspath(klasor), git_kok).replace("\\", "/").rstrip("/") + "/"
    except ValueError:
        is_goreli = None
    sonuc = []
    for a in sorted(adlar):
        n = a.replace("\\", "/")
        if n.startswith(ATLANAN_YOLLAR) or any(p in "/" + n for p in ATLANAN_PARCALAR) or (is_goreli and n.startswith(is_goreli)):
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
        if sonuc not in ("SUCCESS", "NEUTRAL", "SKIPPED") or (durum and durum != "COMPLETED"):
            bekliyor = True  # PENDING, EXPECTED, boş ve bilinmeyen sonuçlar yeşil sayılmaz
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
    t = kayit.get("teslim") if isinstance(kayit.get("teslim"), dict) else {}
    yb = t.get("yerel_birlesme") if isinstance(t.get("yerel_birlesme"), dict) else None
    if yb and str(yb.get("depo") or "").strip():
        # I-459: kod başka depoda; kayıt o depoda yeniden doğrulanır. İş deposunun uzağı/kod dosyası belirleyici değil.
        return _depo_birlesme_eksigi(klasor, yb)
    git_kok = L.git_koku(klasor) if klasor and os.path.isdir(klasor) else None
    if not git_kok or not uzak_var_mi(git_kok, uzak_adi(klasor)):
        return []
    dosyalar = kod_dosyalari(git_kok, klasor, kayit.get("olusturma"))
    if not dosyalar:
        return []
    if yb and yerel_birlesme_dogrula(git_kok, str(yb.get("commit") or ""), klasor)[0]:
        return []  # I-433: kullanıcı terminalinde doğrulanmış yerel birleşme PR yerine geçer (kapanışta yeniden doğrulanır)
    pr = pr_oku(str(t.get("pr") or ""), git_kok)
    eksik = []
    gh_yok = pr is None and shutil.which("gh") is None
    ci = None
    if gh_yok:
        eksik.append(f"{len(dosyalar)} kod dosyası değişti ama `gh` kurulu değil, PR doğrulanamadı (`orkestra is teslim <iş> --pr <bağlantı> --inceleme \"<kim/ne>\"` ile kaydet)")
    elif pr is None:
        eksik.append(f"{len(dosyalar)} kod dosyası değişti ama PR bulunamadı (dalı PR olarak aç; `orkestra is teslim <iş> --pr <bağlantı>`)")
    else:
        ci = ci_durumu(pr.get("statusCheckRollup"))
        if str(pr.get("state") or "").upper() == "CLOSED":
            eksik.append("PR birleştirilmeden kapatılmış")
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
    sonuc = KM.ihlal_ver(klasor, "teslim", eksik)
    if sonuc and kayit.get("id"):  # I-433: kapanış PR/inceleme beklediği için reddedildi → iş kullanıcı kararını bekler
        bekliyor_yaz(sd, kayit["id"], "teslim: " + sonuc[0])
    return sonuc


def depo_birlesme_dogrula(depo: str, commit: str) -> tuple[dict | None, str]:
    """I-459 `is kapat --yerel-birlesme <commit> --depo <yol>`: commit kod deposunda, o deponun ayarıyla doğrulanır;
    kanıt deponun git kökünü (`depo`) taşır."""
    kok = L.git_koku(depo) if depo and os.path.isdir(depo) else None
    if not kok:
        return None, f"--depo git deposu değil: {depo}"
    kanit, neden = yerel_birlesme_dogrula(kok, commit, kok, kesin=True)
    if kanit:
        kanit["depo"] = kok
    return kanit, neden


def _depo_birlesme_eksigi(klasor: str, yb: dict) -> list[str]:
    depo = str(yb.get("depo") or "")
    commit = str(yb.get("commit") or "")
    kanit, neden = depo_birlesme_dogrula(depo, commit)
    if kanit:
        return []
    return KM.ihlal_ver(klasor, "teslim", [f"yerel birleşme {commit[:12]} kayıtlı depoda ({depo}) doğrulanamadı: {neden}"])


def kaydet_girdi(sd: str, is_id: str, pr: str = "", inceleme: str = "") -> dict:
    """`orkestra is teslim` / `is kapat --pr --inceleme`: PR bağlantısı ve inceleme notu is.json `teslim` alanına yazılır."""
    import is_kaydi

    def islem(k):
        t = k.setdefault("teslim", {})
        if pr:
            t["pr"] = pr
            k["bekliyor"] = f"PR: {pr}"[:300]  # I-433: PR açıldı → birleştirme/inceleme kullanıcı kararını bekler
        if inceleme:
            t["inceleme"] = inceleme

    return is_kaydi._degistir(sd, is_id, islem)


def yerel_birlesme_kaydet(sd: str, is_id: str, kanit: dict) -> dict:
    """`is kapat --yerel-birlesme`: doğrulanmış kanıt is.json `teslim.yerel_birlesme` alanına yazılır."""
    import is_kaydi

    def islem(k):
        k.setdefault("teslim", {})["yerel_birlesme"] = kanit

    return is_kaydi._degistir(sd, is_id, islem)
