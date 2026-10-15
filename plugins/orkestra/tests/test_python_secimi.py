"""G-103: Python yorumlayıcı seçimi (ORKESTRA_PYTHON) ve kur.py pytest denetimi."""
import os
import subprocess
import sys
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
DEPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(SCRIPTS))
import ork_lib as L  # noqa: E402
import kur  # noqa: E402


def test_ortam_degiskeni_oncelikli(monkeypatch):
    monkeypatch.setenv("ORKESTRA_PYTHON", "/x/ozel/python")
    assert L.python_yorumlayici() == "/x/ozel/python"


def test_varsayilan_py313_ya_da_sys_executable(monkeypatch):
    monkeypatch.delenv("ORKESTRA_PYTHON", raising=False)
    with mock.patch.object(L.shutil, "which", return_value=None):
        assert L.python_yorumlayici() == sys.executable
    r = mock.Mock(returncode=0, stdout=sys.executable + "\n")
    with mock.patch.object(L.shutil, "which", return_value="py"), \
            mock.patch.object(L.subprocess, "run", return_value=r):
        assert L.python_yorumlayici() == sys.executable
    r = mock.Mock(returncode=1, stdout="")
    with mock.patch.object(L.shutil, "which", return_value="py"), \
            mock.patch.object(L.subprocess, "run", return_value=r):
        assert L.python_yorumlayici() == sys.executable


def test_kapi_secilen_yorumlayiciyi_alt_sureclere_verir(monkeypatch, tmp_path):
    monkeypatch.setenv("ORKESTRA_PYTHON", sys.executable)
    kod, cikti, _ = L.kabuk_kos(f'"{sys.executable}" -c "import os;print(os.environ[\'ORKESTRA_PYTHON\'])"', str(tmp_path), 60)
    assert kod == 0 and cikti.strip() == sys.executable


def test_kur_pytest_yoksa_uyari_durdurmaz(monkeypatch, capsys):
    monkeypatch.setattr(kur, "pytest_var_mi", lambda y: False)
    assert kur.main() == 0
    assert "UYARI: pytest bulunamadı" in capsys.readouterr().out


def test_kur_pytest_varsa_uyari_yok(monkeypatch, capsys):
    monkeypatch.setattr(kur, "pytest_var_mi", lambda y: True)
    assert kur.main() == 0
    assert "UYARI" not in capsys.readouterr().out


def test_readme_ve_sabit_yol_yok():
    readme = (DEPO / "README.md").read_text(encoding="utf-8")
    assert "ORKESTRA_PYTHON" in readme and "pytest" in readme
    for f in (SCRIPTS / "ork_lib.py", SCRIPTS / "orkestra.py", SCRIPTS / "kur.py"):
        assert "C:/Python315" not in f.read_text(encoding="utf-8")
