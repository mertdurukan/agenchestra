"""I-157 P1/P3: kilit zaman aşımı günlüğü süreç adı ve bekleme süresini yazar; bekleyenler FIFO sırayla kilidi alır.
`py -3.13 -m pytest plugins/orkestra/tests/test_kilit_zaman_asimi.py`
"""
import os
import re
import shutil
import sys
import tempfile
import threading
import time
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

    def test_bekleyenler_gelis_sirasiyla_alir(self):
        sira = []

        def calis(i):
            with L.kilit(self.yol):
                sira.append(i)
                time.sleep(0.01)

        with L.kilit(self.yol):
            kolar = []
            for i in range(5):
                t = threading.Thread(target=calis, args=(i,))
                t.start()
                kolar.append(t)
                time.sleep(0.06)   # bilet zaman damgaları ayrışsın
        for t in kolar:
            t.join(5)
        self.assertEqual(sira, [0, 1, 2, 3, 4])

    def test_olu_bilet_kilidi_engellemez(self):
        sira = self.yol + ".sira"
        os.makedirs(sira)
        olu = os.path.join(sira, f"{1:020d}-99999")
        open(olu, "w").close()
        eski = time.time() - 10
        os.utime(olu, (eski, eski))
        with L.kilit(self.yol, bekleme_s=0.5):
            pass

    def test_bilet_zaman_asiminda_ve_alinca_silinir(self):
        with L.kilit(self.yol):
            with self.assertRaises(TimeoutError):
                with L.kilit(self.yol, bekleme_s=0.2):
                    pass
        with L.kilit(self.yol):
            pass
        self.assertEqual(os.listdir(self.yol + ".sira"), [])


if __name__ == "__main__":
    unittest.main()
