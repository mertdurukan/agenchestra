"""Geniş test_komutu'nun test_alani'ndaki test dosyalarına daraltılması (L.test_komutu_daralt)."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import ork_lib as L  # noqa: E402


class DaraltTest(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.kok = self._t.name
        os.makedirs(os.path.join(self.kok, "p", "tests"))
        for ad in ("test_a.py", "test_b.py", "yardimci.py"):
            with open(os.path.join(self.kok, "p", "tests", ad), "w", encoding="utf-8") as f:
                f.write("")
        os.environ.pop("ORKESTRA_TEST_DARALT", None)

    def tearDown(self):
        self._t.cleanup()
        os.environ.pop("ORKESTRA_TEST_DARALT", None)

    def test_klasor_dosyalara_iner(self):
        k, n = L.test_komutu_daralt("py -3.13 -m pytest p/tests -q -p no:cacheprovider", self.kok, ["p/tests/test_a.py"])
        self.assertEqual(k, "py -3.13 -m pytest p/tests/test_a.py -q -p no:cacheprovider")
        self.assertIn("1 test dosyasına", n)

    def test_konumsal_yok_sona_eklenir(self):
        k, _ = L.test_komutu_daralt("python -m pytest -q -p no:cacheprovider", self.kok, ["p/tests/test_*.py"])
        self.assertEqual(k, "python -m pytest -q -p no:cacheprovider p/tests/test_a.py p/tests/test_b.py")

    def test_paralel_koşucu(self):
        k, _ = L.test_komutu_daralt("py -3.13 p/scripts/test_paralel.py -n 8 p/tests", self.kok, ["p/tests/test_b.py"])
        self.assertEqual(k, "py -3.13 p/scripts/test_paralel.py -n 8 p/tests/test_b.py")

    def test_dosya_duzeyi_aynen(self):
        c = "python -m pytest p/tests/test_a.py::T::t -q"
        self.assertEqual(L.test_komutu_daralt(c, self.kok, ["p/tests/test_b.py"]), (c, None))

    def test_unittest_aynen(self):
        c = "python -m unittest discover -s p/tests -p test_a.py"
        self.assertEqual(L.test_komutu_daralt(c, self.kok, ["p/tests/test_b.py"]), (c, None))

    def test_test_dosyasi_yoksa_tam_paket_kosmaz(self):
        k, n = L.test_komutu_daralt("python -m pytest p/tests", self.kok, ["p/tests/yardimci.py", "p/tests/test_yok.py"])
        self.assertIsNone(k)
        self.assertTrue(n)

    def test_kapatma_ortam_degiskeni(self):
        os.environ["ORKESTRA_TEST_DARALT"] = "0"
        c = "python -m pytest p/tests"
        self.assertEqual(L.test_komutu_daralt(c, self.kok, ["p/tests/test_a.py"]), (c, None))


if __name__ == "__main__":
    unittest.main()
