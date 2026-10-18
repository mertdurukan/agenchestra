"""Cursor adaptörü (scripts/cursor_hook.py): girdi/çıktı çevirisi, atlama kuralları, hook.py ile uçtan uca.
Girdi örnekleri 16.10 Cursor ölçümünün alanlarını taşır (019 deneme kayıtları): BOM, camelCase olay, workspace_roots."""
import json
import os
import subprocess
import sys

import pytest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import cursor_hook as ch  # noqa: E402


def test_girdi_olay_cwd_arac_ve_cikti_alani():
    g = {"hook_event_name": "preToolUse", "tool_name": "Shell", "tool_input": {"command": "git status"},
         "workspace_roots": ["/C:/Users/PC/proje"], "transcript_path": "c:\\x.jsonl"}
    c = ch.girdi_donustur("preToolUse", g)
    assert c["hook_event_name"] == "PreToolUse"
    assert c["tool_name"] == "Bash"
    assert c["cwd"] in ("C:/Users/PC/proje", os.environ.get("CURSOR_PROJECT_DIR"), os.environ.get("CLAUDE_PROJECT_DIR"))


def test_girdi_tool_output_ve_dize_tool_input():
    c = ch.girdi_donustur("postToolUse", {"tool_name": "Task", "tool_input": "{\"a\": 1}", "tool_output": "{\"b\": 2}"})
    assert c["tool_input"] == {"a": 1}
    assert c["tool_response"] == "{\"b\": 2}"


def test_atla_salt_okuma_ve_ilgisiz_post():
    assert ch.atla("preToolUse", {"tool_name": "Read"})
    assert not ch.atla("preToolUse", {"tool_name": "Shell"})
    assert ch.atla("postToolUse", {"tool_name": "Read"})
    assert not ch.atla("postToolUse", {"tool_name": "Task"})
    assert not ch.atla("sessionStart", {})


def test_cikti_session_ve_prompt():
    claude = {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "BAGLAM"}}
    assert ch.cikti_donustur("sessionStart", claude) == {"additional_context": "BAGLAM"}
    assert ch.cikti_donustur("beforeSubmitPrompt", claude) == {"continue": True, "additional_context": "BAGLAM"}
    assert ch.cikti_donustur("sessionStart", None) == {}


def test_cikti_pretooluse_deny_ask_ve_updated_input(monkeypatch):
    deny = {"hookSpecificOutput": {"permissionDecision": "deny", "permissionDecisionReason": "kapı"}}
    o = ch.cikti_donustur("preToolUse", deny)
    assert o["permission"] == "deny" and o["user_message"] == "kapı"
    ask = {"hookSpecificOutput": {"permissionDecision": "ask", "permissionDecisionReason": "push"}}
    monkeypatch.delenv("ORKESTRA_CURSOR_ASK", raising=False)
    assert ch.cikti_donustur("preToolUse", ask)["permission"] == "deny"  # Cursor ask uygulamıyor: güvenli taraf
    monkeypatch.setenv("ORKESTRA_CURSOR_ASK", "ask")
    assert ch.cikti_donustur("preToolUse", ask)["permission"] == "ask"
    upd = {"hookSpecificOutput": {"permissionDecision": "allow", "updatedInput": {"command": "x"}}}
    assert ch.cikti_donustur("preToolUse", upd)["updated_input"] == {"command": "x"}


def test_cikti_stop_block_followup():
    assert ch.cikti_donustur("stop", {"decision": "block", "reason": "bitirme kapısı"}) == {"followup_message": "bitirme kapısı"}
    assert ch.cikti_donustur("stop", {}) == {}


def _kod(tmp_path, govde):
    f = tmp_path / "hook_stub.py"
    f.write_text(govde, encoding="utf-8")
    return str(f)


def test_calistir_bomlu_girdi_ve_cikis(tmp_path, monkeypatch):
    stub = _kod(tmp_path, "import sys,json\n"
                "g=json.load(sys.stdin)\n"
                "assert sys.argv[1]=='SessionStart' and g['hook_event_name']=='SessionStart'\n"
                "print(json.dumps({'hookSpecificOutput':{'hookEventName':'SessionStart','additionalContext':'ctx:'+g['cwd']}}))\n")
    monkeypatch.setenv("ORKESTRA_CURSOR_HOOK_PY", stub)
    monkeypatch.setenv("CURSOR_PROJECT_DIR", str(tmp_path))
    ham = b"\xef\xbb\xbf" + json.dumps({"hook_event_name": "sessionStart", "workspace_roots": ["x"]}).encode()
    metin, kod, _ = ch.calistir("sessionStart", ham)
    assert kod == 0
    assert json.loads(metin) == {"additional_context": "ctx:" + str(tmp_path)}


def test_calistir_cikis_kodu_2_gecer(tmp_path, monkeypatch):
    stub = _kod(tmp_path, "import sys\nsys.stderr.write('engel')\nsys.exit(2)\n")
    monkeypatch.setenv("ORKESTRA_CURSOR_HOOK_PY", stub)
    _, kod, hata = ch.calistir("preToolUse", json.dumps({"tool_name": "Shell", "tool_input": {}}).encode())
    assert kod == 2 and "engel" in hata


def test_uctan_uca_gercek_hook_py_orkestrasiz_proje(tmp_path, monkeypatch):
    """Gerçek hook.py: orkestra açık olmayan projede sessiz kalmalı (çıktı boş JSON, kod 0)."""
    monkeypatch.delenv("ORKESTRA_CURSOR_HOOK_PY", raising=False)
    monkeypatch.setenv("CURSOR_PROJECT_DIR", str(tmp_path))
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    ham = json.dumps({"hook_event_name": "preToolUse", "tool_name": "Shell", "tool_input": {"command": "echo 1"},
                      "workspace_roots": [str(tmp_path)]}).encode()
    metin, kod, _ = ch.calistir("preToolUse", ham)
    assert kod == 0
    assert json.loads(metin) in ({}, {"permission": "allow"})


def test_komut_satiri_python_c_ile_calisir(tmp_path):
    """hooks/cursor-hooks.json'daki komut kalıbı: python -c ... runpy (ortam değişkeninden yol)."""
    h = json.load(open(os.path.join(KOK, "hooks", "cursor-hooks.json"), encoding="utf-8"))
    komut = h["hooks"]["sessionStart"][0]["command"]
    env = dict(os.environ, CURSOR_PLUGIN_ROOT=KOK, CURSOR_PROJECT_DIR=str(tmp_path), CLAUDE_PROJECT_DIR=str(tmp_path))
    p = subprocess.run(komut, shell=True, input=b"{\"workspace_roots\": []}", capture_output=True, env=env, cwd=str(tmp_path))
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout.decode("utf-8") or "{}") == {} or "additional_context" in p.stdout.decode("utf-8")


def test_user_email_hook_girdisine_gecmez():
    c = ch.girdi_donustur("stop", {"user_email": "a@b.c", "status": "completed"})
    assert "user_email" not in c


def test_stop_alanlari_none_gelince_cokmez():
    assert ch.cikti_donustur("stop", {"decision": "block", "reason": None}) == {"followup_message": ""}
    assert ch.cikti_donustur("stop", {"hookSpecificOutput": None}) == {}
    assert ch.cikti_donustur("stop", [1]) == {}
    c = ch.girdi_donustur("stop", {"workspace_roots": None, "tool_input": None})
    assert c["hook_event_name"] == "Stop"
    assert ch.calistir("stop", b"null") == ("{}", 0, "")
