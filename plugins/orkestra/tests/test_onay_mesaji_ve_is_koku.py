"""I-105: içeriksiz onay mesajı 'devam' sayılır; iş klasörü proje kökü olamaz."""
import json
import os
import sys
import tempfile
import unittest

AD = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AD, "..", "scripts"))
import is_kaydi  # noqa: E402
import soru_sinif  # noqa: E402


class OnayMesaji(unittest.TestCase):
    def test_onay_kelimeleri_devam(self):
        for m in ("yap", "kabul", "Yap!", "uygula", "başla", "onaylıyorum", "ne gerekiyorsa yap", "hepsini yap"):
            self.assertEqual(soru_sinif.tur(m), "devam", m)

    def test_gercek_gorev_is_kalir(self):
        for m in ("commitle pushla", "x dosyasını yap", "panelde butonu düzelt"):
            self.assertEqual(soru_sinif.tur(m), "is", m)


class IsKoku(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.proje = os.path.join(self.t.name, "proje")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        os.makedirs(self.sd)
        os.makedirs(os.path.join(self.proje, "Kok"))
        with open(os.path.join(self.sd, "baglam.json"), "w", encoding="utf-8") as f:
            json.dump({"surum": 1, "projeler": ["Kok"]}, f)

    def tearDown(self):
        self.t.cleanup()

    def test_proje_koku_reddedilir(self):
        with self.assertRaises(ValueError):
            is_kaydi.is_ac(self.sd, "x", os.path.join(self.proje, "Kok"))

    def test_numarali_alt_klasor_acilir(self):
        kayit = is_kaydi.is_ac(self.sd, "x", os.path.join(self.proje, "Kok", "001-20261020-x"))
        self.assertTrue(kayit["id"].startswith("I-"))


if __name__ == "__main__":
    unittest.main()
