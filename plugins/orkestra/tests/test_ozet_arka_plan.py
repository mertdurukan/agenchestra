"""scripts/ozet.py yaz_arka_plan + isci (I-328 P1): kirli/islenen/kos protokolü, iki yarış penceresi, kilit, geri alma."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import ozet  # noqa: E402


class OzetArkaPlan(unittest.TestCase):
    def setUp(self):
        self.sd = tempfile.mkdtemp(prefix="ork_ozet_ap_")
        self.yol = os.path.join(self.sd, "ozet.json")
        self.cagri = []

    def tearDown(self):
        shutil.rmtree(self.sd, ignore_errors=True)

    def kirli_yaz(self, n):
        with open(self.yol + ".kirli", "w", encoding="utf-8") as f:
            f.write(str(n))

    def islenen(self):
        return ozet._sayac(self.yol + ".islenen")

    def test_isci_kirliyi_isler(self):
        self.kirli_yaz(5)
        with mock.patch.object(ozet, "yaz", side_effect=lambda *a: self.cagri.append(1)):
            ozet.isci(self.sd, self.sd)
        self.assertEqual(len(self.cagri), 1)
        self.assertEqual(self.islenen(), 5)

    def test_temiz_ise_yazmaz(self):
        self.kirli_yaz(5)
        with open(self.yol + ".islenen", "w") as f:
            f.write("5")
        with mock.patch.object(ozet, "yaz", side_effect=lambda *a: self.cagri.append(1)):
            ozet.isci(self.sd, self.sd)
        self.assertEqual(self.cagri, [])

    def test_pencere_a_hesap_ortasinda_tetik(self):
        self.kirli_yaz(1)

        def yavas(*a):
            self.cagri.append(1)
            if len(self.cagri) == 1:
                self.kirli_yaz(2)   # hesap sürerken ikinci tetik

        with mock.patch.object(ozet, "yaz", side_effect=yavas):
            ozet.isci(self.sd, self.sd)
        self.assertEqual(len(self.cagri), 2)
        self.assertEqual(self.islenen(), 2)

    def test_pencere_b_kilit_birakildiktan_sonra_tetik(self):
        self.kirli_yaz(1)
        gercek_kapat = os.close
        durum = {"bumped": False}

        def kapat(fd):
            gercek_kapat(fd)
            if not durum["bumped"]:
                durum["bumped"] = True
                self.kirli_yaz(2)   # kos bırakıldı, bitiş kontrolünden önce tetik

        with mock.patch.object(ozet, "yaz", side_effect=lambda *a: self.cagri.append(1)), \
                mock.patch("os.close", side_effect=kapat):
            ozet.isci(self.sd, self.sd)
        self.assertEqual(len(self.cagri), 2)
        self.assertEqual(self.islenen(), 2)

    def test_kos_doluyken_isci_cikar(self):
        self.kirli_yaz(1)
        fd = ozet._kos_kilidi_al(self.yol)
        self.assertIsNotNone(fd)
        try:
            with mock.patch.object(ozet, "yaz", side_effect=lambda *a: self.cagri.append(1)):
                ozet.isci(self.sd, self.sd)
            self.assertEqual(self.cagri, [])
            self.assertFalse(os.path.exists(self.yol + ".zaman_asimi.log"))   # log yazmayan non-blocking deneme
        finally:
            os.close(fd)

    def test_kos_serbest_birakilir(self):
        fd = ozet._kos_kilidi_al(self.yol)
        os.close(fd)   # işçi ölse de işletim sistemi aynısını yapar
        fd2 = ozet._kos_kilidi_al(self.yol)
        self.assertIsNotNone(fd2)
        os.close(fd2)

    def test_hook_yolu_kirli_yazar_ve_isci_baslatir(self):
        with mock.patch.object(ozet.subprocess, "Popen") as popen:
            ozet.yaz_arka_plan(self.sd, self.sd)
        self.assertGreater(ozet._sayac(self.yol + ".kirli"), 0)
        self.assertEqual(popen.call_count, 1)
        self.assertIn("--isci", popen.call_args[0][0])

    def test_geri_alma_esitzamanli(self):
        with mock.patch.dict(os.environ, {"ORKESTRA_OZET_ESITZAMANLI": "1"}), \
                mock.patch.object(ozet, "yaz", side_effect=lambda *a: self.cagri.append(1)), \
                mock.patch.object(ozet.subprocess, "Popen") as popen:
            ozet.yaz_arka_plan(self.sd, self.sd)
        self.assertEqual(self.cagri, [1])
        popen.assert_not_called()

    def test_baslatma_hatasinda_esitzamanli_yola_duser(self):
        with mock.patch.object(ozet.subprocess, "Popen", side_effect=OSError("yok")), \
                mock.patch.object(ozet, "yaz", side_effect=lambda *a: self.cagri.append(1)):
            ozet.yaz_arka_plan(self.sd, self.sd)
        self.assertEqual(self.cagri, [1])

    def test_gercek_isci_sureci_ozeti_yazar(self):
        self.kirli_yaz(1)
        r = subprocess.run([sys.executable, os.path.join(KOK, "scripts", "ozet.py"), "--isci", self.sd, self.sd],
                           capture_output=True, text=True, timeout=60, env=dict(os.environ, PYTHONUTF8="1"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.islenen(), 1)
        self.assertTrue(os.path.exists(self.yol))
        json.load(open(self.yol, encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
