"""Bilgi grafiği uçtan uca (ADR-0118, I-296): bu depoda statik kenarlar + kartlar kurulur, özgün senaryo ("yeni skill ekle")
skill'in panel aç/kapa yüzeyini ve ona bağlı statik kenarı bulur. Model çağırmaz; kartlar fixtures/ altındadır."""
import os
import shutil
import sys
import tempfile
import unittest

AD = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AD, "..", "scripts"))
import harita_istek as I  # noqa: E402
import harita_kenar as K  # noqa: E402

KOK = os.path.abspath(os.path.join(AD, "..", "..", ".."))  # depo kökü (yüzey yolları depo köküne göredir)


class UctanUca(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.graf = tempfile.mkdtemp()
        shutil.copytree(os.path.join(AD, "fixtures", "bilgi_grafigi_kartlar"), os.path.join(cls.graf, "kartlar"))
        K.yaz(K.statik_kenarlar(KOK), os.path.join(cls.graf, "kenarlar.jsonl"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.graf, ignore_errors=True)

    def test_yeni_skill_istegi_panel_yuzeyini_ve_bagli_kenari_bulur(self):
        s = I.etki("yeni bir skill ekle", self.graf)
        self.assertTrue(s["eslesti"])
        self.assertIn("skill", s["konular"])
        yollar = {y["yol"] for y in s["yuzeyler"]}
        self.assertIn("plugins/orkestra/scripts/araclar_skill.py", yollar)
        self.assertIn("plugins/orkestra/scripts/panel.py", yollar)
        kenarlar = {(k["kaynak"], k["hedef"]) for k in s["komsular"]}
        self.assertTrue(any("panel.py" in a and "araclar_skill" in b for a, b in kenarlar), kenarlar)

    def test_ilgisiz_istek_eslesmez(self):
        self.assertFalse(I.etki("hava durumu nasıl", self.graf)["eslesti"])

    def test_yuzey_yollari_depoda_var(self):
        for y in I.etki("skill ekle", self.graf)["yuzeyler"]:
            if "*" not in y["yol"]:
                self.assertTrue(os.path.exists(os.path.join(KOK, y["yol"])), y["yol"])


if __name__ == "__main__":
    unittest.main()
