"""I-071: ajan tipinden süreç türetme — defterde "bilinmiyor" üretilmez."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import ork_lib as L  # noqa: E402


class SurecTuret(unittest.TestCase):
    def test_etiketten_gelen_korunur(self):
        self.assertEqual(L.surec_turet("general-purpose", "denetim"), "denetim")

    def test_bilinen_tipler(self):
        for tip, beklenen in (("general-purpose", "genel-ajan"), ("orkestra:test-yazari", "test-yaz"),
                              ("orkestra:hafiza-bakimcisi", "perspektif"), ("claude-code-guide", "genel-ajan"),
                              ("orkestra:denetci", "denetim"), ("orkestra:isci-t2", "is"), ("Explore", "arastirma"),
                              ("orkestra:arsivci", "arsiv"), ("orkestra:triyaj", "triyaj")):
            self.assertEqual(L.surec_turet(tip), beklenen, tip)

    def test_eslenmemis_tip_adiyla_yazilir(self):
        self.assertEqual(L.surec_turet("baska:ajan"), "diger:baska:ajan")

    def test_tip_yoksa_acik_etiket(self):
        for tip in (None, "", "?"):
            self.assertEqual(L.surec_turet(tip), "tip-okunamadi")

    def test_hicbir_girdi_bilinmiyor_uretmez(self):
        for tip in (None, "?", "x", "general-purpose", "orkestra:isci-t9"):
            self.assertNotEqual(L.surec_turet(tip), "bilinmiyor")


if __name__ == "__main__":
    unittest.main()
