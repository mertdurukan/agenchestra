"""ADR hedef deposu çözümleyicisi (ADR-0097)."""
import os
import subprocess
import sys

KOK = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import adr_depo as D  # noqa: E402


def _depo(yol, adrler=(), uzak=False):
    os.makedirs(os.path.join(yol, "adr"), exist_ok=True)
    subprocess.run(["git", "init", "-q", str(yol)], check=True)
    for ad in adrler:
        open(os.path.join(yol, "adr", ad), "w", encoding="utf-8").write("x")
    if uzak:
        subprocess.run(["git", "-C", str(yol), "remote", "add", "origin", "https://example.invalid/x.git"], check=True)
    return str(yol)


def test_kok_yoksa_yalniz_proje(tmp_path):
    proje = _depo(tmp_path / "p")
    assert [os.path.normcase(k) for k in D.depolar("# plan", str(tmp_path / "p"), proje)] == [os.path.normcase(proje)]


def test_kok_baska_depoysa_one_gelir(tmp_path):
    proje = _depo(tmp_path / "p")
    hedef = _depo(tmp_path / "e")
    plan = f"**Kök:** {hedef}\n"
    sira = D.depolar(plan, str(tmp_path / "p"), proje)
    assert os.path.normcase(sira[0]) == os.path.normcase(hedef).replace("\\", "/") or \
        os.path.normcase(os.path.abspath(sira[0])) == os.path.normcase(os.path.abspath(hedef))
    assert len(sira) == 2


def test_ayni_numara_iki_depoda_hedef_kazanir(tmp_path):
    proje = _depo(tmp_path / "p", ["ADR-0097-a.md"])
    hedef = _depo(tmp_path / "e", ["ADR-0097-b.md"])
    bulunan = D.adr_bul("ADR-0097", D.depolar(f"**Kök:** {hedef}\n", str(tmp_path / "p"), proje))
    assert bulunan.endswith("ADR-0097-b.md")


def test_hedefte_yoksa_projeye_duser(tmp_path):
    proje = _depo(tmp_path / "p", ["ADR-0050-a.md"])
    hedef = _depo(tmp_path / "e")
    assert D.adr_bul("ADR-0050", D.depolar(f"**Kök:** {hedef}\n", str(tmp_path / "p"), proje)).endswith("ADR-0050-a.md")


def test_sonraki_no(tmp_path):
    assert D.sonraki_no(_depo(tmp_path / "bos")) == 1
    assert D.sonraki_no(_depo(tmp_path / "d", ["ADR-0003-x.md", "ADR-0097-y.md", "not.md"])) == 98


def test_uzak_var(tmp_path):
    assert not D.uzak_var(_depo(tmp_path / "a"))
    assert D.uzak_var(_depo(tmp_path / "b", uzak=True))
