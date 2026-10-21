"""I-139 P5 (bce F54): araclar/changelog.py - türe göre gruplama, otomatik commit atlama, deterministik çıktı."""
import importlib.util
import os
import shutil
import subprocess
import tempfile
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEPO = os.path.dirname(os.path.dirname(KOK))
_spec = importlib.util.spec_from_file_location("changelog", os.path.join(DEPO, "araclar", "changelog.py"))
CL = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(CL)


def _git(depo, *a):
    subprocess.run(["git", "-C", depo, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *a],
                   check=True, capture_output=True)


class Changelog(unittest.TestCase):
    def setUp(self):
        self.depo = tempfile.mkdtemp(prefix="ork_cl_")
        _git(self.depo, "init", "-q")
        for i, baslik in enumerate(["feat(a): özellik bir", "Otomatik commit: x.md", "fix: hata düzeltildi",
                                    "Otomatik commit: y.md", "docs(b): belge"]):
            with open(os.path.join(self.depo, f"f{i}.txt"), "w") as f:
                f.write(str(i))
            _git(self.depo, "add", "-A")
            _git(self.depo, "commit", "-q", "-m", baslik)

    def tearDown(self):
        shutil.rmtree(self.depo, ignore_errors=True)

    def test_uc_satir_ve_gruplu(self):
        metin = CL.uret(CL.git_log(self.depo))
        satirlar = [s for s in metin.splitlines() if s.startswith("- ")]
        self.assertEqual(len(satirlar), 3, metin)
        self.assertFalse([s for s in satirlar if "Otomatik commit" in s])
        basliklar = [s for s in metin.splitlines() if s.startswith("## ")]
        self.assertEqual(basliklar, ["## Özellikler", "## Düzeltmeler", "## Belgeler"])
        self.assertIn("- a: özellik bir (", metin)

    def test_bicimsiz_baslik_diger_gruba_duser(self):
        g = CL.grupla([("abc1234", "Serbest başlık"), ("def5678", "feat!: kırıcı")])
        self.assertEqual(g["Diğer"], ["Serbest başlık (abc1234)"])
        self.assertEqual(g["Özellikler"], ["kırıcı (def5678)"])

    def test_cikti_deterministik_ve_dosya_yazar(self):
        a = CL.uret(CL.git_log(self.depo))
        b = CL.uret(CL.git_log(self.depo))
        self.assertEqual(a, b)
        self.assertEqual(CL.main(["--depo", self.depo]), 0)
        with open(os.path.join(self.depo, "CHANGELOG.md"), encoding="utf-8") as f:
            self.assertEqual(f.read(), a)

    def test_depoda_changelog_uretilmis(self):
        yol = os.path.join(DEPO, "CHANGELOG.md")
        self.assertTrue(os.path.isfile(yol), "CHANGELOG.md üretilmemiş: python araclar/changelog.py")
        with open(yol, encoding="utf-8") as f:
            metin = f.read()
        self.assertTrue(metin.startswith("# Değişiklik günlüğü"))
        self.assertNotIn("- Otomatik commit", metin)


if __name__ == "__main__":
    unittest.main()
