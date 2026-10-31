"""İki eşzamanlı oturum senaryosu (31.10.2026 olayı, ADR-0125): çakışma işe BAŞLARKEN görülür, hiçbir şey engellenmez."""
import json
import os
import subprocess
import sys

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ic_kos  # noqa: E402
import oturum_olcum as O  # noqa: E402

HOOK = os.path.join(KOK, "scripts", "hook.py")
CLI = os.path.join(KOK, "scripts", "orkestra.py")
TEMIZLIK = "aaaaaaaa-0000-0000-0000-000000000001"  # ana ağaçta (main) çalışan dal temizliği oturumu
ENTEGRASYON = "bbbbbbbb-0000-0000-0000-000000000002"  # ayrı worktree'de çalışan birleştirme işi


def _git(cwd, *a):
    subprocess.run(["git", "-C", cwd, "-c", "user.name=t", "-c", "user.email=t@t", *a], check=True, capture_output=True)


def _env(oturum):
    e = dict(os.environ, PYTHONUTF8="1", ORKESTRA_IZIN="0", CLAUDE_CODE_SESSION_ID=oturum)
    e.pop("CLAUDE_PROJECT_DIR", None)
    return e


def _hook(olay, cwd, oturum, **alan):
    girdi = {"session_id": oturum, "cwd": cwd, "hook_event_name": olay, **alan}
    return ic_kos.kos([HOOK, olay], cwd=cwd, env=_env(oturum), input=json.dumps(girdi)).stdout or ""


def _ctx(cikti):
    try:
        return json.loads(cikti)["hookSpecificOutput"]["additionalContext"]
    except (ValueError, KeyError):
        return ""


def test_iki_oturum_cakismayi_baslarken_gorur(tmp_path):
    ana = str(tmp_path / "ana")
    os.makedirs(os.path.join(ana, ".claude", "orkestra", "oturumlar"))
    subprocess.run(["git", "init", "-q", "-b", "main", ana], check=True)
    _git(ana, "commit", "-q", "--allow-empty", "-m", "x")
    wt = os.path.join(ana, ".claude", "worktrees", "wt")  # gerçek yerleşim: oturum worktree'si projenin altında
    _git(ana, "worktree", "add", "-q", "-b", "entegrasyon", wt)

    # 1) Temizlik oturumu ana ağaçta başlar: kimseyi görmez, çıktısında çakışma satırı yok (0 ek karakter)
    assert "Eş zamanlı" not in _ctx(_hook("SessionStart", ana, TEMIZLIK, source="startup"))
    # 2) Entegrasyon oturumu ayrı worktree'de BAŞLAR: temizlik oturumunu işe başlarken görür
    c = _ctx(_hook("SessionStart", wt, ENTEGRASYON, source="startup"))
    assert "Eş zamanlı oturum aaaaaaaa" in c and "ortak yüzeyde" in c
    # 3) Entegrasyon main'e dokunan git komutu çalıştırır: uyarı gelir, engellenmez; ikinci kez gelmez
    g = _hook("PreToolUse", wt, ENTEGRASYON, tool_name="Bash", tool_input={"command": "git merge --ff-only main"})
    assert "git komutu" in _ctx(g) and "permissionDecision" not in g
    assert "git komutu" not in _ctx(_hook("PreToolUse", wt, ENTEGRASYON, tool_name="Bash",
                                          tool_input={"command": "git merge --ff-only main"}))
    # 4) Temizlik oturumu not bırakır; entegrasyon sonraki araç çağrısında VERİ olarak görür
    r = ic_kos.kos([CLI, "oturum", "not", "bbbb", "main'i ff etme, dal silmeyi bekliyorum"], cwd=ana, env=_env(TEMIZLIK))
    assert r.returncode == 0, r.stderr
    c = _ctx(_hook("PreToolUse", wt, ENTEGRASYON, tool_name="Read", tool_input={"file_path": "x"}))
    assert "VERİ" in c and "main'i ff etme" in c
    # 5) Tespitler gölge günlüğe düştü ve rapor sayar
    sd = os.path.join(ana, ".claude", "orkestra")
    rp = O.rapor(sd, 1)
    assert rp["tespit"] >= 2 and "yuzey" in rp["neden"]


def test_gecikme_olcumu_calisir(tmp_path):
    ana = str(tmp_path / "ana")
    os.makedirs(os.path.join(ana, ".claude", "orkestra", "oturumlar"))
    subprocess.run(["git", "init", "-q", "-b", "main", ana], check=True)
    _git(ana, "commit", "-q", "--allow-empty", "-m", "x")
    g = O.gecikme(os.path.join(ana, ".claude", "orkestra"), ana, 100)
    assert g["okuma"]["n"] == 50 and g["yazma"]["n"] == 50
    assert g["okuma"]["p95_ms"] < 500  # gevşek sağlık eşiği; gerçek eşik (p95<20 ms) 1000 çağrılık ölçümle raporlanır
