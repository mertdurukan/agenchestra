"""ADR-0091 (P5): çalışma özeti tek kaynak; `is anlati` ve `is jira-yorum` aynı özetten, alan adları uyumlu çalışır.

Parçalar ayrı dosyalarda (şablon, kapı, anlatı paketi, A10, Jira yorumu) olduğundan alan adı uyumu burada birlikte sınanır.
"""
import importlib
import json
import os
import sys
import tempfile
import unittest

AD = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(AD, "..", "scripts")
ORKESTRA = os.path.join(SCRIPTS, "orkestra.py")
sys.path.insert(0, AD)
sys.path.insert(0, SCRIPTS)

import ic_kos  # noqa: E402
import is_kaydi as IK  # noqa: E402
import test_is_anlati_cli as AC  # noqa: E402  (kur, TEMIZ fixture'ı)
import test_is_jira_yorum as JYT  # noqa: E402  (PE640, BEKLENEN fixture'ı)
import test_sef_ozeti as SO  # noqa: E402

SINIRLI = AC.TEMIZ + " Bazı doğrulamalar henüz yapılmadı."


def cli(kok, alt, *args):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=kok, PYTHONUTF8="1")
    return ic_kos.kos([ORKESTRA, "is", alt, *args], cwd=kok, env=env)


def _golge_sabit(f):
    """Gölge davranışı sınanır: kapı modunu ayar varsayılanından bağımsız `golge`ye sabitler (ADR-0096)."""
    import functools
    from unittest import mock

    @functools.wraps(f)
    def sar(*a, **k):
        import kapi_mod as KM
        with mock.patch.object(KM, "mod", side_effect=lambda kapi, klasor=None: "golge"):
            return f(*a, **k)
    return sar


class UcTanUca(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.kok = self._t.name
        AC.kur(self.kok, adet=1)
        self.klasor = os.path.join(self.kok, "isler", "001-is-1")

    def tearDown(self):
        self._t.cleanup()

    def ozet(self, metin):
        with open(os.path.join(self.klasor, "calisma_ozeti_20261027.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write(metin)

    def taslak(self, metin):
        yol = os.path.join(self.kok, "taslak.md")
        with open(yol, "w", encoding="utf-8") as f:
            f.write(metin)
        return yol

    def test_ayni_ozetten_anlati_paketi_ve_jira_yorumu(self):
        self.ozet(JYT.PE640)
        p = cli(self.kok, "anlati", "I-001", "--json")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        paket = json.loads(p.stdout)
        self.assertTrue(paket["durum"].startswith("Kısmen. Kod, test ve ölçüm tamam"), paket["durum"])
        self.assertIn("üç kör turda yakalama", paket["nasil_karar"] if isinstance(paket["nasil_karar"], str)
                      else " ".join(paket["nasil_karar"]))
        y = cli(self.kok, "jira-yorum", "I-001")
        self.assertEqual(y.returncode, 0, y.stdout + y.stderr)
        self.assertEqual(y.stdout, JYT.BEKLENEN)

    def test_a10_gercek_komut_yolunda_kismen_sinirsiz_red(self):
        self.ozet(JYT.PE640)
        kotu = cli(self.kok, "anlati", "I-001", "--denetle", self.taslak(AC.TEMIZ))
        self.assertEqual(kotu.returncode, 1, kotu.stdout + kotu.stderr)
        self.assertIn("A10", kotu.stdout + kotu.stderr)
        iyi = cli(self.kok, "anlati", "I-001", "--denetle", self.taslak(SINIRLI))
        self.assertEqual(iyi.returncode, 0, iyi.stdout + iyi.stderr)

    def test_a10_tamam_durumda_sinirsiz_temiz(self):
        self.ozet(JYT.PE640.replace("**Durum:** Kısmen.", "**Durum:** Tamam."))
        p = cli(self.kok, "anlati", "I-001", "--denetle", self.taslak(AC.TEMIZ))
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_eski_bicim_paket_ve_kapi_eskisi_gibi(self):
        eski = SO.YENI + SO.HARITA.replace("\n## Harita", "\n## Harita", 1)
        self.ozet(eski)
        p = cli(self.kok, "anlati", "I-001", "--json")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(json.loads(p.stdout)["durum"], "")
        self.assertEqual(IK.sef_ozeti_eksigi(SO.IKI), [])  # eski etiketli: yeni alan uyarısı yok

    @_golge_sabit

    def test_yeni_bicim_eksik_alan_golgede_uyarir_kapanisi_engellemez(self):
        isler = importlib.import_module("komutlar.isler")
        eksik = SO.YENI_B1.replace("**Durum:** Kısmen.", "**Durum:**") + SO.HARITA
        self.assertTrue(any("Durum" in x for x in IK.sef_ozeti_eksigi(eksik, 1200)))
        self.ozet(eksik)
        self.assertIsNone(isler._sef_ozeti_kapisi(self.klasor, eksik))  # gölge: engellemez
        gunluk = os.path.join(self.kok, ".claude", "orkestra", "gunluk.jsonl")
        self.assertTrue(os.path.isfile(gunluk), "kapi_golge kaydı yazılmadı")
        with open(gunluk, encoding="utf-8") as f:
            self.assertIn("kapi_golge", f.read())


if __name__ == "__main__":
    unittest.main()
