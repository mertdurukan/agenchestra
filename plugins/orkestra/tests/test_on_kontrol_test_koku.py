"""G-129: on_kontrol kapsam denetimi test_koku'lu kartta test_alani'ni test köküne göre çözer. Geçici dizinler; ağ/model yok."""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import on_kontrol as OK  # noqa: E402

TEST_YOLU = "plugins/orkestra/tests/test_x.py"


class TestKoku(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = os.path.join(self.tmp.name, "proje")
        self.t = os.path.join(self.tmp.name, "testdepo")
        self.gd = os.path.join(self.p, ".claude", "orkestra", "gorevler")
        os.makedirs(self.gd)
        os.makedirs(os.path.join(self.p, "src"))
        os.makedirs(os.path.join(self.t, "plugins", "orkestra", "tests"))

    def tearDown(self):
        self.tmp.cleanup()

    def kart(self, **ek):
        k = {"id": "G-1", "sinif": "kod", "yazma_alani": ["src/*.py"], "test_alani": [TEST_YOLU]}
        k.update(ek)
        with open(os.path.join(self.gd, "G-1.json"), "w", encoding="utf-8") as f:
            json.dump(k, f)

    def kos(self, ciktilar):
        cikti = io.StringIO()
        with contextlib.redirect_stdout(cikti):
            kod = OK.main(["kontrol", "G-1", "--ciktilar", ciktilar, "--proje", self.p])
        return kod, json.loads(cikti.getvalue())

    @staticmethod
    def kapsam(sonuc):
        return [i for i in sonuc["ihlaller"] if i["tur"] == OK.TUR_KAPSAM]

    # K1
    def test_k1_test_koku_goreli_test_alani_cikti_kapsam_ihlali_vermez(self):
        self.kart(test_koku=self.t)
        _, s = self.kos(TEST_YOLU)
        self.assertEqual(self.kapsam(s), [])

    def test_k1_test_koku_mutlak_cikti_kapsam_ihlali_vermez(self):
        self.kart(test_koku=self.t)
        _, s = self.kos(os.path.join(self.t, TEST_YOLU).replace("\\", "/"))
        self.assertEqual(self.kapsam(s), [])

    def test_k1_test_koku_ve_yazma_alani_ciktisi_birlikte_gecer(self):
        self.kart(test_koku=self.t)
        kod, s = self.kos(TEST_YOLU + ",src/a.py")
        self.assertEqual(self.kapsam(s), [])
        self.assertEqual(kod, 0)

    def test_k1_glob_desenli_test_alani(self):
        self.kart(test_koku=self.t, test_alani=["plugins/orkestra/tests/test_*.py"])
        _, s = self.kos(TEST_YOLU)
        self.assertEqual(self.kapsam(s), [])

    # K2
    def test_k2_alan_disi_cikti_test_koku_varken_ihlal(self):
        self.kart(test_koku=self.t)
        kod, s = self.kos("baska/dosya.py")
        self.assertEqual(len(self.kapsam(s)), 1)
        self.assertIn("baska/dosya.py", self.kapsam(s)[0]["ayrinti"])
        self.assertEqual(kod, 4)

    def test_k2_test_alani_disindaki_test_yolu_ihlal(self):
        self.kart(test_koku=self.t)
        _, s = self.kos("plugins/orkestra/tests/test_baska.py")
        self.assertEqual(len(self.kapsam(s)), 1)

    def test_k2_yalniz_alan_disi_olan_isaretlenir(self):
        self.kart(test_koku=self.t)
        _, s = self.kos(TEST_YOLU + ",yetkisiz.py")
        k = self.kapsam(s)
        self.assertEqual(len(k), 1)
        self.assertIn("yetkisiz.py", k[0]["ayrinti"])

    # K3
    def test_k3_test_kokusuz_test_alani_proje_kokune_gore(self):
        self.kart()
        _, s = self.kos(TEST_YOLU)
        self.assertEqual(self.kapsam(s), [])

    def test_k3_test_kokusuz_test_alani_yazma_alanina_eklenmisse_gecer(self):
        self.kart(yazma_alani=["src/*.py", TEST_YOLU])
        _, s = self.kos(TEST_YOLU)
        self.assertEqual(self.kapsam(s), [])

    def test_k3_test_kokusuz_alan_disi_ihlal(self):
        self.kart()
        _, s = self.kos("baska/dosya.py")
        self.assertEqual(len(self.kapsam(s)), 1)

    def test_k3_test_kokusuz_yazma_alani_cikti_gecer(self):
        self.kart()
        kod, s = self.kos("src/a.py")
        self.assertEqual(self.kapsam(s), [])
        self.assertEqual(kod, 0)


if __name__ == "__main__":
    unittest.main()
