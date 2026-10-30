"""Doktor: ADR deposunda git uzak deposu yoksa uyarır (ADR-0097)."""
import os
import subprocess
import sys

KOK = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import doktor as D  # noqa: E402


def _depo(yol, adr=True, uzak=False):
    os.makedirs(os.path.join(yol, "adr"), exist_ok=True)
    subprocess.run(["git", "init", "-q", str(yol)], check=True)
    if adr:
        open(os.path.join(yol, "adr", "ADR-0001-x.md"), "w", encoding="utf-8").write("x")
    if uzak:
        subprocess.run(["git", "-C", str(yol), "remote", "add", "origin", "https://example.invalid/gizli-yol.git"], check=True)
    return str(yol)


def test_uzaksiz_depo_uyari_yalniz_yol_ve_sayi(tmp_path):
    s = D.adr_yedek_sonucu([_depo(tmp_path / "a")])
    assert s.durum == "uyari" and "1 dosya" in s.mesaj
    assert "example.invalid" not in s.mesaj


def test_uzakli_depo_gecer(tmp_path):
    assert D.adr_yedek_sonucu([_depo(tmp_path / "a", uzak=True)]).durum == "gecti"


def test_adr_yoksa_atlanir(tmp_path):
    assert D.adr_yedek_sonucu([_depo(tmp_path / "a", adr=False)]).durum == "atlandi"


def test_kayitli_kontrol(tmp_path):
    assert "adr_yedek" in [k.id for k in D.KONTROLLER]
