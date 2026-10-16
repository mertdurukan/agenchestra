"""P5 (I-026): bin/orkestra yorumlayıcı sırası = hook_python ile aynı (ORKESTRA_PYTHON > python3 > python > py -3; WindowsApps atlanır)."""
import os
import shutil
import stat
import subprocess
import sys

import pytest

BIN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin")
SH = shutil.which("sh")

pytestmark = pytest.mark.skipif(SH is None, reason="sh yok")


def sahte(dizin, ad):
    """`<dizin>/<ad>`: çağrıldığında kendi adını ve ilk argümanını basan sh betiği."""
    os.makedirs(dizin, exist_ok=True)
    yol = os.path.join(dizin, ad)
    with open(yol, "w", newline="\n") as f:
        f.write(f'#!/bin/sh\necho "{ad}-calisti"\n')
    os.chmod(yol, os.stat(yol).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return yol


def calistir(path_dizinleri, extra_env=None):
    env = {k: v for k, v in os.environ.items() if k != "ORKESTRA_PYTHON"}
    env["PATH"] = os.pathsep.join(path_dizinleri + [os.path.dirname(SH)])
    env.update(extra_env or {})
    return subprocess.run([SH, os.path.join(BIN, "orkestra"), "--help"], env=env, capture_output=True, text=True)


def test_python3_oncelikli(tmp_path):
    d = str(tmp_path / "a")
    sahte(d, "python3")
    sahte(d, "python")
    assert "python3-calisti" in calistir([d]).stdout


def test_python3_yoksa_python(tmp_path):
    d = str(tmp_path / "a")
    sahte(d, "python")
    sahte(d, "py")
    assert "python-calisti" in calistir([d]).stdout.replace("python3-calisti", "")


def test_windowsapps_stub_atlanir(tmp_path):
    stub = str(tmp_path / "WindowsApps")
    gercek = str(tmp_path / "gercek")
    sahte(stub, "python3")
    sahte(gercek, "python")
    r = calistir([stub, gercek])
    assert "python-calisti" in r.stdout and "python3-calisti" not in r.stdout


def test_ortam_degiskeni_en_oncelikli(tmp_path):
    d = str(tmp_path / "a")
    sahte(d, "python3")
    ozel = sahte(str(tmp_path / "ozel"), "benim-python")
    r = calistir([d], {"ORKESTRA_PYTHON": ozel})
    assert "benim-python-calisti" in r.stdout and "python3-calisti" not in r.stdout


def test_yalniz_py_ile_calisir(tmp_path):
    d = str(tmp_path / "a")
    sahte(d, "py")
    if any(shutil.which(a, path=os.path.dirname(SH)) for a in ("python3", "python")):
        pytest.skip("sh dizininde python var; 'yalnız py' durumu bu makinede kurulamaz")
    assert "py-calisti" in calistir([d]).stdout


def test_hicbiri_yoksa_127(tmp_path):
    if any(shutil.which(a, path=os.path.dirname(SH)) for a in ("python3", "python", "py")):
        pytest.skip("sh dizininde python var")
    r = calistir([str(tmp_path)])
    assert r.returncode == 127 and "bulunamadı" in r.stderr
