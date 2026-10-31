"""Proje bilgi grafiği backtest (ADR-0112, I-296): sızıntısız walk-forward recall ve precision; sentetik commit listesiyle koşar."""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import harita_backtest as B  # noqa: E402


class Backtest(unittest.TestCase):
    def setUp(self):
        self.kok = tempfile.mkdtemp()
        for f in ("a.txt", "b.txt", "c.txt", "d.txt"):
            with open(os.path.join(self.kok, f), "w", encoding="utf-8") as fh:
                fh.write("x")

    def tearDown(self):
        shutil.rmtree(self.kok, ignore_errors=True)

    def test_hep_birlikte_degisen_cift_tam_isabet(self):
        cm = [["a.txt", "b.txt"]] * 10
        s = B.olc(self.kok, isinma=0.5, asgari=3, cm=cm)
        self.assertEqual((s["sinama_commit"], s["recall"], s["precision"]), (5, 1.0, 1.0))

    def test_ilk_gorulen_commit_ongorulemez_sizinti_yok(self):
        # sınanan commit'in kendisi öğrenmeye girmez: asgari=3 ile ilk 3 commit öngörüsüz
        cm = [["a.txt", "b.txt"]] * 3
        s = B.olc(self.kok, isinma=0.0, asgari=3, cm=cm)
        self.assertEqual((s["sinama_commit"], s["recall"], s["kapsama"]), (3, 0.0, 0.0))

    def test_ilgisiz_dosya_recall_dusurur(self):
        cm = [["a.txt", "b.txt"]] * 6 + [["a.txt", "c.txt"]] * 2
        s = B.olc(self.kok, isinma=0.75, asgari=3, cm=cm)
        self.assertEqual(s["sinama_commit"], 2)
        self.assertEqual(s["recall"], 0.0)       # c.txt daha önce hiç a.txt ile değişmedi
        self.assertEqual(s["precision"], 0.0)    # a.txt tohumu b.txt'yi öngördü, yanlış

    def test_silinmis_dosya_sayilmaz(self):
        cm = [["a.txt", "yok.txt", "b.txt"]] * 8
        s = B.olc(self.kok, isinma=0.5, asgari=3, cm=cm)
        self.assertEqual((s["recall"], s["precision"]), (1.0, 1.0))

    def test_esik_ornek_yetersizse_gecmez(self):
        s = B.olc(self.kok, isinma=0.5, asgari=3, cm=[["a.txt", "b.txt"]] * 10)
        self.assertFalse(s["yeterli_ornek"])
        self.assertFalse(s["esik_gecti"])


if __name__ == "__main__":
    unittest.main()
