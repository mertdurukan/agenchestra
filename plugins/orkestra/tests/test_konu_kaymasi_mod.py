"""I-297 P6: bölme yönergesi brief'in ilk satırında işin modunu taşır; yeni sohbetin `/auto` ilk satırı yalnız o
oturumun bekleyen modunu yazar, öteki işin modu değişmez.
`py -3.13 -m pytest plugins/orkestra/tests/test_konu_kaymasi_mod.py`
"""
import os
import shutil
import sys
import tempfile
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import is_onay  # noqa: E402
import is_yonlendirme as IY  # noqa: E402

ISLER = [{"id": "I-021", "baslik": "Langfuse izleme"}, {"id": "I-022", "baslik": "Fatura raporu"}]


class ModSatiriTest(unittest.TestCase):
    def test_zorunlu_yonerge_auto_satiri(self):
        s = IY.yonlendir(ISLER, "I-021", zorunlu=True, mod="auto")
        self.assertIn("ilk satır `/auto`, sonra", s)
        self.assertLessEqual(len(s), IY.SATIR_SINIR)

    def test_hatirlatma_plan_satiri(self):
        self.assertIn("ilk satır `/plan`, sonra", IY.yonlendir(ISLER, "I-021", mod="plan"))

    def test_mod_yoksa_satir_yok(self):
        self.assertNotIn("ilk satır `/", IY.yonlendir(ISLER, "I-021", zorunlu=True))


class YeniSohbetModTest(unittest.TestCase):
    def setUp(self):
        self.sd = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.sd, ignore_errors=True)

    def test_ilk_satir_auto_yalniz_yeni_oturumun_bekleyen_modunu_yazar(self):
        brief = "/auto\norkestra is ac \"Yeni konu\" --klasor X"
        self.assertEqual(is_onay.mod_mesaji(brief), "auto")
        is_onay.bekleyen_mod_yaz(self.sd, "yeni-oturum", is_onay.mod_mesaji(brief))
        self.assertEqual(is_onay.bekleyen_mod_bak(self.sd, "yeni-oturum"), "auto")
        self.assertIsNone(is_onay.bekleyen_mod_bak(self.sd, "eski-oturum"))


if __name__ == "__main__":
    unittest.main()
