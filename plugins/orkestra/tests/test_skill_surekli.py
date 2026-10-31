import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import araclar_skill as S  # noqa: E402
import skill_surekli as SS  # noqa: E402


@pytest.fixture
def ortam(tmp_path, monkeypatch):
    monkeypatch.delenv("ORKESTRA_SKILL_SUREKLI", raising=False)
    kul = tmp_path / "kul"
    pr = tmp_path / "pr"
    for dizin, ad, govde in ((kul, "birinci", "BIRINCI-GOVDE"), (kul, "ikinci", "IKINCI-GOVDE"), (kul, "ucuncu", "UCUNCU-GOVDE")):
        (dizin / ad).mkdir(parents=True)
        (dizin / ad / "SKILL.md").write_text("---
name: %s
description: d
---
%s
" % (ad, govde), encoding="utf-8")
    pr.mkdir()
    ek = tmp_path / "ek"
    ek.mkdir()
    return dict(proje=str(pr), kullanici_dizin=str(kul), eklenti_dizin=str(ek))


def test_yalniz_surekli_govde_gelir(ortam):
    S.konum_ata("birinci", "surekli", **ortam)
    S.konum_ata("ikinci", "ihtiyacta", **ortam)
    S.konum_ata("ucuncu", "kapali", **ortam)
    m = SS.baglam(**ortam)
    assert "BIRINCI-GOVDE" in m and "name: birinci" not in m
    assert "IKINCI-GOVDE" not in m and "UCUNCU-GOVDE" not in m


def test_surekli_yoksa_bos(ortam):
    assert SS.baglam(**ortam) == ""


def test_kapatma_ortam_degiskeni(ortam, monkeypatch):
    S.konum_ata("birinci", "surekli", **ortam)
    monkeypatch.setenv("ORKESTRA_SKILL_SUREKLI", "0")
    assert SS.baglam(**ortam) == ""


def test_sinir_asilinca_uyari_ve_kisaltma(ortam):
    S.konum_ata("birinci", "surekli", **ortam)
    S.konum_ata("ikinci", "surekli", **ortam)
    m = SS.baglam(sinir=60, **ortam)
    assert "IKINCI-GOVDE" not in m and "ikinci" in m.split("Uyarı")[-1]
    assert len(SS.baglam(**ortam)) < SS.SINIR


def test_dosya_bozuksa_bos(ortam):
    p = os.path.join(ortam["proje"], ".claude", "orkestra")
    os.makedirs(p)
    open(os.path.join(p, "skill_durum.json"), "w").write("{bozuk")
    assert SS.baglam(**ortam) == ""
