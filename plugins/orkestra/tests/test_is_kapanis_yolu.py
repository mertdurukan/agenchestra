"""is_durum: kapandi yolsuz reddedilir, yol/gerekce geçmiş olayına yazılır; diğer durumlar etkilenmez."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import is_kaydi as K  # noqa: E402


class KapanisYoluTest(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.sd = os.path.join(self._t.name, "orkestra")
        os.makedirs(self.sd)
        K.is_ac(self.sd, "t", os.path.join(self._t.name, "isler", "a"))

    def test_yolsuz_kapanis_reddedilir_ve_durum_degismez(self):
        with self.assertRaises(ValueError):
            K.is_durum(self.sd, "I-001", "kapandi")
        self.assertNotEqual(K.is_al(self.sd, "I-001")["durum"], "kapandi")

    def test_gecersiz_yol_reddedilir(self):
        with self.assertRaises(ValueError):
            K.is_durum(self.sd, "I-001", "kapandi", yol="hook")

    def test_yol_olaya_yazilir(self):
        for yol in K.KAPANIS_YOLLARI:
            k = K.is_durum(self.sd, "I-001", "kapandi", yol=yol)
            olay = k["gecmis"][-1]
            self.assertEqual(olay["olay"], "durum:kapandi")
            self.assertEqual(olay["yol"], yol)
            self.assertNotIn("gerekce", olay)

    def test_gerekce_yazilir(self):
        k = K.is_durum(self.sd, "I-001", "kapandi", yol="bakim", gerekce="eski kayıt")
        self.assertEqual(k["gecmis"][-1]["gerekce"], "eski kayıt")

    def test_diger_durumlar_yolsuz_calisir(self):
        k = K.is_durum(self.sd, "I-001", "acik")
        self.assertEqual(k["gecmis"][-1]["olay"], "durum:acik")
        self.assertNotIn("yol", k["gecmis"][-1])


if __name__ == "__main__":
    unittest.main()
