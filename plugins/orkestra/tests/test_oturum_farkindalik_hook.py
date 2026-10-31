"""Hook düzeyinde çakışma farkındalığı (ADR-0122): engellemez, çakışmasızken sessiz."""
import json
import os
import subprocess
import sys

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ic_kos  # noqa: E402
import oturum_farkindalik as F  # noqa: E402

HOOK = os.path.join(KOK, "scripts", "hook.py")
A = "aaaaaaaa-1111-2222-3333-444444444444"
B = "bbbbbbbb-1111-2222-3333-444444444444"


def _proje(tmp_path):
    p = str(tmp_path / "proje")
    os.makedirs(os.path.join(p, ".claude", "orkestra", "oturumlar"))
    subprocess.run(["git", "init", "-q", "-b", "main", p], check=True)
    subprocess.run(["git", "-C", p, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty",
                    "-m", "x"], check=True)
    return p


def _hook(olay, cwd, oturum, **alan):
    env = dict(os.environ, PYTHONUTF8="1")
    env.pop("CLAUDE_PROJECT_DIR", None)
    env["ORKESTRA_IZIN"] = "0"
    girdi = {"session_id": oturum, "cwd": cwd, "hook_event_name": olay, **alan}
    r = ic_kos.kos([HOOK, olay], cwd=cwd, env=env, input=json.dumps(girdi))
    return r.stdout or ""


def test_git_komutunda_komsu_gorunur_engellenmez_bir_kez(tmp_path):
    p = _proje(tmp_path)
    sd = os.path.join(p, ".claude", "orkestra")
    assert F.kaydet(sd, A, p, dosya=os.path.join(p, "x.py"), is_id="I-306")
    c = _hook("PreToolUse", p, B, tool_name="Bash", tool_input={"command": "git rebase main"})
    assert "aaaaaaaa" in c and "deny" not in c and "permissionDecision" not in c
    c2 = _hook("PreToolUse", p, B, tool_name="Bash", tool_input={"command": "git rebase main"})
    assert "aaaaaaaa" not in c2  # oturum başına bir kez


def test_cakismasiz_durumda_sifir_karakter(tmp_path):
    p = _proje(tmp_path)
    c = _hook("PreToolUse", p, B, tool_name="Bash", tool_input={"command": "git rebase main"})
    assert "Eş zamanlı" not in c


def test_alt_ajan_ve_okuma_araci_uyari_almaz(tmp_path):
    p = _proje(tmp_path)
    sd = os.path.join(p, ".claude", "orkestra")
    F.kaydet(sd, A, p)
    c = _hook("PreToolUse", p, B, tool_name="Read", tool_input={"file_path": os.path.join(p, "x.py")})
    assert "Eş zamanlı" not in c
    c = _hook("PreToolUse", p, B, tool_name="Bash", tool_input={"command": "git rebase main"}, agent_id="alt1")
    assert "Eş zamanlı" not in c
