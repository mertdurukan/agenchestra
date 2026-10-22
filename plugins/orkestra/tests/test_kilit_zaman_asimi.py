"""I-157 P1: kilit zaman aşımı günlüğü süreç adı ve bekleme süresini yazar.
`py -3.13 -m pytest plugins/orkestra/tests/test_kilit_zaman_asimi.py`
"""
import os
import re
import shutil
import sys
import tempfile
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import ork_lib as L  # noqa: E402


@unittest.skipUnless(os.name == "nt", "msvcrt yolu: POSIX flock beklemesi zaman aşımsız")
class KilitZamanAsimiGunlugu(unittest.TestCase):
    def setUp(self):
        self.kok = tempfile.mkdtemp(prefix="ork_kz_")
        self.yol = os.path.join(self.kok, ".islem")

    def tearDown(self):
        shutil.rmtree(self.kok, ignore_errors=True)

    def test_gunluk_surec_ve_bekleme_yazar(self):
        with L.kilit(self.yol):
            with self.assertRaises(TimeoutError):
                with L.kilit(self.yol, bekleme_s=0.2):
                    pass
        with open(self.yol + ".zaman_asimi.log", encoding="utf-8") as g:
            satir = g.read().strip().splitlines()[-1]
        self.assertRegex(satir, r"kilit_zaman_asimi pid=\d+ surec=\S+ bekleme_ms=\d+$")
        ms = int(re.search(r"bekleme_ms=(\d+)", satir).group(1))
        self.assertGreaterEqual(ms, 200)
        self.assertLess(ms, 1500)


if __name__ == "__main__":
    unittest.main()
