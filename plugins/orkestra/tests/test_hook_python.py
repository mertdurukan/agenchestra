"""G-007: kancalar 'python' yerine platforma dayanıklı sarmalayıcıyı çağırır.

Sözleşme (testlerin dayandığı):
  - bin/hook_python.cmd (Windows, CRLF) ve bin/hook_python (POSIX sh, LF).
  - Çağrı: `hook_python <OlayAdı>`; sarmalayıcı kendi konumuna göre ../scripts/hook.py dosyasını bulur
    ve aynı argümanlarla çalıştırır. Yorumlayıcı sırası: python3 -> python -> py -3.
  - stdin ve çıkış kodu aynen geçer.
Yorumlayıcıyı PATH'ten ayırt etmek için sahte (shim) python3/python/py yürütülebilirleri kullanılır;
sahte hook.py argümanları, stdin'i ve hangi shim'in çalıştığını JSON olarak yazar.
"""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parent.parent
BIN = PLUGIN / "bin"
HOOKS_JSON = PLUGIN / "hooks" / "hooks.json"
WIN = os.name == "nt"

SAHTE_HOOK = r'''
import json, os, sys
veri = sys.stdin.buffer.read().decode("utf-8")
print(json.dumps({"argv": sys.argv[1:], "stdin": veri, "shim": os.environ.get("SHIM_NAME", "")}))
sys.exit(int(os.environ.get("HOOK_EXIT", "0")))
'''

PY_SHIM_YARDIMCI = r'''
import os, subprocess, sys
if len(sys.argv) < 2 or sys.argv[1] != "-3":
    sys.exit(97)
os.environ["SHIM_NAME"] = "py"
sys.exit(subprocess.call([sys.executable] + sys.argv[2:]))
'''


# ------------------------------------------------------------------ yardımcılar

def _kur_eklenti(kok: Path, ad: str = "my plugin") -> Path:
    """Boşluklu bir dizinde sahte eklenti düzeni: bin/<sarmalayıcılar> + scripts/hook.py (sahte)."""
    ek = kok / ad
    (ek / "bin").mkdir(parents=True)
    (ek / "scripts").mkdir()
    for ad in ("hook_python.cmd", "hook_python"):
        kaynak = BIN / ad
        assert kaynak.is_file(), f"{kaynak} yok"
        shutil.copyfile(kaynak, ek / "bin" / ad)
    (ek / "scripts" / "hook.py").write_text(SAHTE_HOOK, encoding="utf-8")
    return ek


def _shim_win(dizin: Path, ad: str) -> None:
    exe = sys.executable
    if ad == "py":
        yard = dizin / "_pyshim.py"
        yard.write_text(PY_SHIM_YARDIMCI, encoding="utf-8")
        govde = f'@"{exe}" "{yard}" %*\r\n'
    else:
        govde = f'@set SHIM_NAME={ad}\r\n@"{exe}" %*\r\n'
    (dizin / f"{ad}.cmd").write_bytes(govde.encode("utf-8"))


def _shim_posix(dizin: Path, ad: str) -> None:
    exe = sys.executable.replace("\\", "/")
    if ad == "py":
        govde = f'#!/bin/sh\n[ "$1" = "-3" ] || exit 97\nshift\nSHIM_NAME=py exec "{exe}" "$@"\n'
    else:
        govde = f'#!/bin/sh\nSHIM_NAME={ad} exec "{exe}" "$@"\n'
    p = dizin / ad
    p.write_bytes(govde.encode("utf-8"))
    p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _cmd_calistir(ek: Path, shimler: list[str], arglar: list[str], stdin: str, cikis: int = 0):
    shimdir = ek.parent / "shims"
    shimdir.mkdir(exist_ok=True)
    for s in shimler:
        _shim_win(shimdir, s)
    sistem32 = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")
    env = {"PATH": f"{shimdir};{sistem32}", "SystemRoot": os.environ.get("SystemRoot", r"C:\Windows"),
           "COMSPEC": os.environ.get("COMSPEC", os.path.join(sistem32, "cmd.exe")),
           "PATHEXT": ".COM;.EXE;.BAT;.CMD", "HOOK_EXIT": str(cikis)}
    return subprocess.run([str(ek / "bin" / "hook_python.cmd"), *arglar], input=stdin.encode("utf-8"),
                          capture_output=True, env=env, timeout=60, cwd=str(ek.parent))


def _sh_yolu() -> str | None:
    return shutil.which("sh")


def _sh_calistir(ek: Path, shimler: list[str], arglar: list[str], stdin: str, cikis: int = 0):
    sh = _sh_yolu()
    shimdir = ek.parent / "shims"
    shimdir.mkdir(exist_ok=True)
    for s in shimler:
        _shim_posix(shimdir, s)
    env = {"PATH": f"{shimdir}{os.pathsep}{os.path.dirname(sh)}", "HOOK_EXIT": str(cikis)}
    for k in ("SystemRoot", "TEMP", "TMP", "HOME"):
        if k in os.environ:
            env[k] = os.environ[k]
    yol = str(ek / "bin" / "hook_python").replace("\\", "/")
    return subprocess.run([sh, yol, *arglar], input=stdin.encode("utf-8"),
                          capture_output=True, env=env, timeout=60, cwd=str(ek.parent))


def _sh_dizininde_python(ad: str) -> bool:
    return shutil.which(ad, path=os.path.dirname(_sh_yolu() or "")) is not None


YOLLAR = []
if WIN:
    YOLLAR.append(pytest.param(_cmd_calistir, id="cmd"))
YOLLAR.append(pytest.param(
    _sh_calistir, id="sh",
    marks=pytest.mark.skipif(_sh_yolu() is None, reason="sh yok: POSIX yolu sınanamaz")))


def _cikti(r) -> dict:
    return json.loads(r.stdout.decode("utf-8").strip().splitlines()[-1])


# ------------------------------------------------------------------ K1: hooks.json

# Ayrı ve kapı önekli girdiler (hook.py'ye gitmez): biçimleri kendi testlerinde sınanır.
AYRI_BETIKLER = ("scripts/oto_commit.py",)  # tests/test_oto_commit.py


def _tum_kancalar() -> list[tuple[str, dict]]:
    veri = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
    out = []
    for olay, gruplar in veri["hooks"].items():
        for g in gruplar:
            for h in g["hooks"]:
                if not any(b in h["command"] for b in AYRI_BETIKLER):
                    out.append((olay, h))
    return out


def test_hooks_json_dogrudan_python_cagiriyor():
    # Kanca başına süreç sayısını düşürmek için sarmalayıcı (sh → sh alt kabukları → python) atlanır:
    # `bash -c` doğrudan `exec python`. Yorumlayıcı sırası: python -> py -3 -> python3 (yalnız PATH'te bulunanlar,
    # `command -v` kabuk yerleşiğidir, ek süreç açmaz).
    kancalar = _tum_kancalar()
    assert len(kancalar) >= 9
    for olay, h in kancalar:
        assert "hook_python" not in h["command"], f"{olay}: sarmalayıcı zincirine geri dönülmemeli"
        assert "scripts/hook.py" in h["command"], f"{olay}: hook.py yolu komutta olmalı"


def test_hooks_json_hicbir_kancada_args_yok():
    # Claude Code args verilince süreci kabuksuz başlatır; Windows'ta uzantısız betik/.cmd çalışmaz.
    for olay, h in _tum_kancalar():
        assert "args" not in h, f"{olay}: 'args' alanı olmamalı (kabuk dizesi kullanılmalı)"


def test_hooks_json_komut_tam_bicimde_ve_olay_adi_dogru():
    sayi = 0
    hook = '"${CLAUDE_PLUGIN_ROOT}/scripts/hook.py"'
    for olay, h in _tum_kancalar():
        sayi += 1
        beklenen = (f'if command -v python >/dev/null 2>&1; then exec python {hook} {olay}; '
                    f'elif command -v py >/dev/null 2>&1; then exec py -3 {hook} {olay}; '
                    f'else exec python3 {hook} {olay}; fi')
        assert h["command"] == beklenen, f"{olay}: beklenen {beklenen!r}, bulunan {h['command']!r}"
        assert h["timeout"] in (10, 30)
    assert sayi >= 9


def test_hooks_json_olay_kumesi_korundu():
    olaylar = set(json.loads(HOOKS_JSON.read_text(encoding="utf-8"))["hooks"])
    assert olaylar == {"SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "SubagentStart",
                       "SubagentStop", "Stop", "SessionEnd", "ConfigChange", "Notification", "PreCompact"}


# ------------------------------------------------------------------ satır sonları

def test_cmd_crlf_sh_lf():
    cmd = (BIN / "hook_python.cmd").read_bytes()
    sh = (BIN / "hook_python").read_bytes()
    assert cmd.count(b"\n") > 0 and cmd.count(b"\n") == cmd.count(b"\r\n"), "cmd tamamen CRLF olmalı"
    assert b"\r" not in sh, "sh betiği LF olmalı"
    assert sh.startswith(b"#!"), "sh betiği shebang ile başlamalı"
    assert not sh.startswith(b"\xef\xbb\xbf") and not cmd.startswith(b"\xef\xbb\xbf"), "BOM olmamalı"


# ------------------------------------------------------------------ K2: sarmalayıcı davranışı

@pytest.mark.parametrize("calistir", YOLLAR)
def test_yalniz_python3_varken_calisir(calistir, tmp_path):
    if calistir is _sh_calistir and _sh_dizininde_python("python"):
        pytest.skip("sh dizininde gerçek python var; yalıtım sağlanamaz")
    ek = _kur_eklenti(tmp_path)
    r = calistir(ek, ["python3"], ["SessionStart"], '{"a": 1}')
    assert r.returncode == 0, r.stderr
    o = _cikti(r)
    assert o["shim"] == "python3"
    assert o["argv"] == ["SessionStart"]
    assert o["stdin"] == '{"a": 1}'


@pytest.mark.parametrize("calistir", YOLLAR)
def test_yalniz_python_varken_calisir(calistir, tmp_path):
    if calistir is _sh_calistir and _sh_dizininde_python("python3"):
        pytest.skip("sh dizininde gerçek python3 var; yalıtım sağlanamaz")
    ek = _kur_eklenti(tmp_path)
    r = calistir(ek, ["python"], ["PreToolUse"], '{"tool_name": "Bash"}')
    assert r.returncode == 0, r.stderr
    o = _cikti(r)
    assert o["shim"] == "python"
    assert o["argv"] == ["PreToolUse"]
    assert o["stdin"] == '{"tool_name": "Bash"}'


@pytest.mark.parametrize("calistir", YOLLAR)
def test_ikisi_varsa_python3_tercih_edilir(calistir, tmp_path):
    ek = _kur_eklenti(tmp_path)
    r = calistir(ek, ["python", "python3"], ["Stop"], "{}")
    assert r.returncode == 0, r.stderr
    assert _cikti(r)["shim"] == "python3"


@pytest.mark.parametrize("calistir", YOLLAR)
def test_yalniz_py_launcher_varsa_py_3_ile_calisir(calistir, tmp_path):
    if calistir is _sh_calistir and (_sh_dizininde_python("python") or _sh_dizininde_python("python3")):
        pytest.skip("sh dizininde gerçek python var; yalıtım sağlanamaz")
    ek = _kur_eklenti(tmp_path)
    r = calistir(ek, ["py"], ["SessionEnd"], "{}")
    assert r.returncode == 0, r.stderr
    o = _cikti(r)
    assert o["shim"] == "py"
    assert o["argv"] == ["SessionEnd"]


@pytest.mark.parametrize("calistir", YOLLAR)
@pytest.mark.parametrize("kod", [0, 2, 7])
@pytest.mark.parametrize("shim", ["python3", "python"])
def test_cikis_kodu_aynen_gecer(calistir, shim, kod, tmp_path):
    if calistir is _sh_calistir and _sh_dizininde_python("python" if shim == "python3" else "python3"):
        pytest.skip("yalıtım sağlanamaz")
    ek = _kur_eklenti(tmp_path)
    r = calistir(ek, [shim], ["Stop"], "{}", cikis=kod)
    assert r.returncode == kod, (r.returncode, r.stderr)
    assert _cikti(r)["shim"] == shim


@pytest.mark.parametrize("calistir", YOLLAR)
def test_stdin_cok_satirli_ve_unicode_bozulmadan_gecer(calistir, tmp_path):
    ek = _kur_eklenti(tmp_path)
    veri = '{"p": "çalışma ğüşiöç İ", "satir": "a\\nb"}\n{"ikinci": true}\n'
    r = calistir(ek, ["python3", "python"], ["UserPromptSubmit"], veri)
    assert r.returncode == 0, r.stderr
    assert _cikti(r)["stdin"] == veri


@pytest.mark.parametrize("calistir", YOLLAR)
def test_bos_stdin_gecer(calistir, tmp_path):
    ek = _kur_eklenti(tmp_path)
    r = calistir(ek, ["python3"], ["SessionStart"], "")
    assert r.returncode == 0, r.stderr
    assert _cikti(r)["stdin"] == ""


@pytest.mark.parametrize("calistir", YOLLAR)
def test_yorumlayici_yoksa_hook_calismaz(calistir, tmp_path):
    if calistir is _sh_calistir and (_sh_dizininde_python("python") or _sh_dizininde_python("python3")):
        pytest.skip("sh dizininde gerçek python var; yalıtım sağlanamaz")
    ek = _kur_eklenti(tmp_path)
    r = calistir(ek, [], ["SessionStart"], "{}")
    assert b'"argv"' not in r.stdout
    assert r.returncode != 0
    assert r.stderr.strip(), "yorumlayıcı bulunamadığı stderr'e yazılmalı"


# ------------------------------------------------------------------ K3: gerçek kanca, gerçek hook.py

@pytest.mark.skipif(not WIN, reason="gerçek kanca kanıtı bu makinede (Windows .cmd) alınır")
def test_gercek_sessionstart_sarmalayici_ile_calisir(tmp_path):
    """.claude/orkestra açık olmayan dizinde SessionStart sessizce geçer: çıkış 0."""
    env = dict(os.environ)
    env["CLAUDE_PLUGIN_ROOT"] = str(PLUGIN)
    env.pop("CLAUDE_PROJECT_DIR", None)
    r = subprocess.run([str(BIN / "hook_python.cmd"), "SessionStart"],
                       input=json.dumps({"hook_event_name": "SessionStart", "cwd": str(tmp_path),
                                         "session_id": "g007"}).encode("utf-8"),
                       capture_output=True, env=env, timeout=60, cwd=str(tmp_path))
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
    assert b"Traceback" not in r.stderr


@pytest.mark.skipif(_sh_yolu() is None, reason="sh yok")
def test_gercek_sessionstart_sh_ile_calisir(tmp_path):
    if shutil.which("python3") is None and shutil.which("python") is None and shutil.which("py") is None:
        pytest.skip("yorumlayıcı yok")
    env = dict(os.environ)
    env["CLAUDE_PLUGIN_ROOT"] = str(PLUGIN)
    env.pop("CLAUDE_PROJECT_DIR", None)
    r = subprocess.run([_sh_yolu(), str(BIN / "hook_python").replace("\\", "/"), "SessionStart"],
                       input=json.dumps({"hook_event_name": "SessionStart", "cwd": str(tmp_path),
                                         "session_id": "g007"}).encode("utf-8"),
                       capture_output=True, env=env, timeout=60, cwd=str(tmp_path))
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
    assert b"Traceback" not in r.stderr


# ------------------------------------------------------------------ K4: kabuk dizesi (args'sız) davranışı

@pytest.mark.skipif(_sh_yolu() is None, reason="sh yok: kabuk dizesi sınanamaz")
@pytest.mark.parametrize("kod", [0, 3])
@pytest.mark.parametrize("olay,komut", [(o, h["command"]) for o, h in _tum_kancalar()])
def test_kabuk_dizesi_stdin_ve_cikis_kodunu_korur(olay, komut, kod, tmp_path):
    if _sh_dizininde_python("python") or _sh_dizininde_python("python3"):
        pytest.skip("sh dizininde gerçek python var; yalıtım sağlanamaz")
    ek = _kur_eklenti(tmp_path, "plugin")  # boşluksuz kök: değişken kabuk dizesine olduğu gibi açılır
    kok = str(ek).replace("\\", "/")
    dize = komut.replace("${CLAUDE_PLUGIN_ROOT}", kok)
    assert "${" not in dize
    shimdir = ek.parent / "shims"
    shimdir.mkdir(exist_ok=True)
    _shim_posix(shimdir, "python3")
    sh = _sh_yolu()
    env = {"PATH": f"{shimdir}{os.pathsep}{os.path.dirname(sh)}", "HOOK_EXIT": str(kod)}
    for k in ("SystemRoot", "TEMP", "TMP", "HOME"):
        if k in os.environ:
            env[k] = os.environ[k]
    veri = '{"p": "çalışma ğ", "olay": "' + olay + '"}\n'
    r = subprocess.run([sh, "-c", dize], input=veri.encode("utf-8"), capture_output=True,
                       env=env, timeout=60, cwd=str(ek.parent))
    assert r.returncode == kod, (r.returncode, r.stderr)
    o = _cikti(r)
    assert o["argv"] == [olay]
    assert o["stdin"] == veri
    assert o["shim"] == "python3"
