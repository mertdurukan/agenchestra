"""Dashboard 'Sıfırla': iş kayıtları yedeğe alınıp boşaltılır; sayaç, iş klasörleri ve kartlar yerinde kalır."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import is_kaydi as IK  # noqa: E402


class IslerSifirla(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.sd = os.path.join(self.tmp.name, "orkestra")
        self.k1 = os.path.join(self.tmp.name, "a")
        IK.is_ac(self.sd, "Birinci", self.k1)
        IK.is_ac(self.sd, "Ikinci", os.path.join(self.tmp.name, "b"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_isler_bosalir_yedek_alinir(self):
        r = IK.sifirla(self.sd)
        self.assertEqual(r["silinen"], 2)
        self.assertTrue(os.path.isfile(r["yedek"]))
        self.assertEqual(IK.is_liste(self.sd), [])
        self.assertTrue(IK.sifirlama_zamani(self.sd))

    def test_sayac_ve_klasor_korunur(self):
        IK.sifirla(self.sd)
        self.assertTrue(os.path.isfile(os.path.join(self.k1, "is.json")))
        self.assertEqual(IK.yeni_is_id(self.sd), "I-003")  # eski kimlikler yeniden verilmez

    def test_bos_kayitta_hata_vermez(self):
        sd = os.path.join(self.tmp.name, "bos")
        r = IK.sifirla(sd)
        self.assertEqual((r["silinen"], r["yedek"]), (0, None))


if __name__ == "__main__":
    unittest.main()
