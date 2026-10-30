"""`orkestra adr yeni/depo` (ADR-0097)."""
import argparse
import os
import subprocess
import sys

import pytest

KOK = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(KOK, "scripts"))
from komutlar import adr, isler  # noqa: E402


def _depo(yol, adrler=()):
    os.makedirs(os.path.join(yol, "adr"), exist_ok=True)
    subprocess.run(["git", "init", "-q", str(yol)], check=True)
    for ad in adrler:
        open(os.path.join(yol, "adr", ad), "w", encoding="utf-8").write("x")
    return str(yol)


def _args(baslik="Hedef depo Kök ile belirlenir"):
    return argparse.Namespace(is_id="I-1", baslik=baslik)


def test_yeni_dogru_depoya_ve_numarayla(tmp_path, monkeypatch, capsys):
    hedef = _depo(tmp_path / "e", ["ADR-0003-a.md", "ADR-0097-b.md"])
    monkeypatch.setattr(adr, "_hedef", lambda a: hedef)
    adr.cmd_yeni(_args())
    yol = os.path.join(hedef, "adr", "ADR-0098-hedef-depo-kok-ile-belirlenir.md")
    metin = open(yol, encoding="utf-8").read()
    assert os.path.isfile(yol)
    for alan in isler.ADR_ALANLARI:
        assert f"**{alan}:**" in metin
    assert "**İlgili iş:** I-1" in metin
    assert "ADR-0098" in capsys.readouterr().out


def test_iskelet_bos_alanlarla_kapiyi_gecmez(tmp_path, monkeypatch):
    hedef = _depo(tmp_path / "e")
    monkeypatch.setattr(adr, "_hedef", lambda a: hedef)
    adr.cmd_yeni(_args("Deneme"))
    yol = os.path.join(hedef, "adr", "ADR-0001-deneme.md")
    assert isler._adr_alan_eksigi(yol)  # Bağlam, Karar, Seçenekler, Sonuçlar boş


def test_var_olan_dosya_ezilmez(tmp_path, monkeypatch):
    hedef = _depo(tmp_path / "e")
    monkeypatch.setattr(adr, "_hedef", lambda a: hedef)
    monkeypatch.setattr(adr.adr_depo, "sonraki_no", lambda k: 5)
    yol = os.path.join(hedef, "adr", "ADR-0005-deneme.md")
    open(yol, "w", encoding="utf-8").write("ESKI")
    with pytest.raises(SystemExit):
        adr.cmd_yeni(_args("Deneme"))
    assert open(yol, encoding="utf-8").read() == "ESKI"


def test_slug_guvenli():
    assert adr._slug("Şifre/Çıktı: ../x?") == "sifre-cikti-x"
    assert adr._slug("???") == "karar"
