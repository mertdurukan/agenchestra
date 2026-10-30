"""ADR kapısı hedef depoyu (planın **Kök:** deposu) arar (ADR-0097)."""
import os
import subprocess
import sys

KOK = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(KOK, "scripts"))
from komutlar import isler  # noqa: E402

TAM = "\n".join(f"**{a}:** dolu" for a in isler.ADR_ALANLARI) + "\n"
BOS = "\n".join(f"**{a}:**" for a in isler.ADR_ALANLARI) + "\n"


def _depo(yol, adrler=None):
    os.makedirs(os.path.join(yol, "adr"), exist_ok=True)
    subprocess.run(["git", "init", "-q", str(yol)], check=True)
    for ad, icerik in (adrler or {}).items():
        open(os.path.join(yol, "adr", ad), "w", encoding="utf-8").write(icerik)
    return str(yol)


def _is(tmp_path, plan):
    k = tmp_path / "is"
    k.mkdir()
    (k / "plan.md").write_text(plan, encoding="utf-8")
    return str(k)


def test_kok_depodaki_adr_kapiyi_gecirir(tmp_path):
    proje = _depo(tmp_path / "p")
    hedef = _depo(tmp_path / "e", {"ADR-0100-x.md": TAM})
    assert isler._adr_eksigi(_is(tmp_path, f"**Kök:** {hedef}\n**ADR:** ADR-0100\n"), proje) is None


def test_kok_yokken_hedefteki_adr_bulunmaz(tmp_path):
    proje = _depo(tmp_path / "p")
    _depo(tmp_path / "e", {"ADR-0100-x.md": TAM})
    assert "dosya yok" in isler._adr_eksigi(_is(tmp_path, "**ADR:** ADR-0100\n"), proje)


def test_kok_yokken_proje_adr_eski_davranis(tmp_path):
    proje = _depo(tmp_path / "p", {"ADR-0100-x.md": TAM})
    assert isler._adr_eksigi(_is(tmp_path, "**ADR:** ADR-0100\n"), proje) is None


def test_ayni_numara_iki_depoda_yalniz_hedef_gecerli(tmp_path):
    proje = _depo(tmp_path / "p", {"ADR-0097-a.md": TAM})
    hedef = _depo(tmp_path / "e", {"ADR-0097-b.md": BOS})
    sonuc = isler._adr_eksigi(_is(tmp_path, f"**Kök:** {hedef}\n**ADR:** ADR-0097\n"), proje)
    assert sonuc and "zorunlu alanları eksik" in sonuc
