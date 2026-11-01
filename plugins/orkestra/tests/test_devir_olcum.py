"""ADR-0099: devir ölçüm betiği (scripts/devir_olcum.py).
`py -3.13 -m pytest -q plugins/orkestra/tests/test_devir_olcum.py`
"""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import devir_olcum as DO  # noqa: E402


class DevirOlcum(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.t, ignore_errors=True)

    def jsonl(self, ad, satirlar):
        with open(os.path.join(self.t, ad), "w", encoding="utf-8") as f:
            for s in satirlar:
                f.write(json.dumps(s) + "\n")

    def test_n_hesapla_140(self):
        self.assertEqual(int(DO.n_hesapla(0.204, 0.354) + 0.9999), 140)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            DO.main(["--n-hesapla", "--p1", "0.204", "--p2", "0.354"])
        self.assertEqual(json.loads(buf.getvalue())["grup_basina"], 140)

    def test_tur_sinifi(self):
        self.assertEqual(DO.tur_sinifi(["/a/plan.md", "/a/todo.md", "/a/mevcut_durum_1.md"]), "is_belgesi")
        self.assertEqual(DO.tur_sinifi(["/a/x.py", "/a/x.py", "/a/x.py"]), "ayni_dosya")
        self.assertEqual(DO.tur_sinifi(["/a/x.py", "/a/y.py", "/a/z.py"]), "muaf_olmayan")

    def test_taban_transkript(self):
        os.makedirs(os.path.join(self.t, "C--Work-DemoRoot-x"))

        def kullanici():
            return {"type": "user", "message": {"content": "yap"}}

        def asistan(*araclar):
            return {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "name": n, "input": ({"file_path": y} if y else {})} for n, y in araclar]}}
        yazim = [("Write", f"/p/{i}.py") for i in range(3)]
        self.jsonl("C--Work-DemoRoot-x/o.jsonl", [
            kullanici(), asistan(*yazim),
            kullanici(), asistan(*yazim, ("Agent", None)),
            kullanici(), asistan(("Write", "/p/plan.md"), ("Write", "/p/todo.md"), ("Write", "/p/mevcut_durum_1.md"))])
        r = DO.taban(self.t, (2000, 1, 1, 0, 0, 0, 0, 0, 0), "C--Work-DemoRoot")
        self.assertEqual((r["muaf_olmayan_tur"], r["alt_ajanli"], r["alt_ajansiz"]), (2, 1, 1))

    def test_kume_testi(self):
        g = {"kontrol": {f"k{i}": [1, 0, 0, 0, 0] for i in range(10)},
             "hatirlatma": {f"h{i}": [1, 1, 1, 0, 0] for i in range(10)}}
        r = DO.kume_test(g)
        self.assertAlmostEqual(r["fark"], 0.4)
        self.assertLess(r["p"], 0.05)

    def test_kume_bagimliligi_se_arttirir(self):
        bagimli = {"kontrol": {f"k{i}": ([1] * 5 if i < 2 else [0] * 5) for i in range(10)},
                   "hatirlatma": {f"h{i}": ([1] * 5 if i < 5 else [0] * 5) for i in range(10)}}
        r = DO.kume_test(bagimli)
        bagimsiz_se = (0.2 * 0.8 / 50 + 0.5 * 0.5 / 50) ** 0.5
        se = (r["gruplar"]["kontrol"]["var"] + r["gruplar"]["hatirlatma"]["var"]) ** 0.5
        self.assertGreater(se, bagimsiz_se)

    def test_rho_ve_tasarim_etkisi(self):
        ayni = {f"s{i}": ([1] * 4 if i % 2 else [0] * 4) for i in range(10)}
        rho, de = DO.rho_ve_etki(ayni)
        self.assertGreater(rho, 0.9)
        self.assertGreater(de, 3)
        karisik = {f"s{i}": [1, 0, 1, 0] for i in range(10)}
        self.assertEqual(DO.rho_ve_etki(karisik)[0], 0.0)

    def test_deney_olculemedi(self):
        self.jsonl("gunluk.jsonl", [{"tur": "devir_olay", "istek_id": "a-0001", "oturum": "a", "grup": "kontrol"},
                                    {"tur": "devir_olay", "istek_id": "b-0001", "oturum": "b", "grup": "hatirlatma"}])
        self.jsonl("zaman.jsonl", [{"tur": "alt", "istek_id": "b-0001"}])
        r = DO.deney(self.t)
        self.assertEqual(r["gruplar"]["hatirlatma"]["devir"], 1)
        self.assertEqual(r["gruplar"]["kontrol"]["devir"], 0)
        self.assertTrue(r["karar"].startswith("ölçülemedi"))


if __name__ == "__main__":
    unittest.main()
